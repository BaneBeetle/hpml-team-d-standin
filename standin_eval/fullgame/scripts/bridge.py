#!/usr/bin/env python3
"""STAND-IN bridge for one full game: widget requests -> Roshan's PolicyWorker -> reply file.

    python3 scripts/bridge.py <run folder>        (started and stopped by scripts/run_game.py)

It does the policy half of Roshan's engine.run_episode and nothing else: read the widget's
request lines, send each through PolicyWorker with the stand-in endpoint factory, check his
response budget, publish the reply with his atomic_json. It does not start or stop the game.
When the policy fails (timeout, error, crash) it stops answering: no retry, no substitute
action. The game then runs on to its cap with the team idle, and the status is recorded.

Unit type numbers: a checkpoint whose folder has unit_defs.json was trained on data from
another game version, where the same units have other numbers. For such a checkpoint the
bridge rewrites the numbers by unit name, in the observation before the policy sees it and
in a build order before the game gets it (see load_translation). Nothing else is rewritten.

Writes into the run folder: policy_trace.jsonl (one line per decision and per small widget
event) and policy_summary.json. Local test fixture, not a result of any team.
"""

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

FULLGAME = Path(__file__).resolve().parents[1]
TEAM_D = FULLGAME.parents[1]
SHARED = TEAM_D.parent / "shared"
sys.path.insert(0, str(TEAM_D / "scripts"))         # control_loop (Roshan's code)
sys.path.insert(0, str(SHARED))                     # endpoint_adapter (Team C stand-in)
sys.path.insert(0, str(TEAM_D / "standin_eval"))    # dry_loop helpers (Phase 1)
from control_loop.engine import EpisodeFailure, deadline_failure
from control_loop.mailbox import atomic_json
from control_loop.policy_worker import PolicyWorker, PolicyWorkerError
from control_loop.protocol import ProtocolError, validate_config, validate_request
from dry_loop import get_json, percentile
import endpoint_adapter

POLL_SECONDS = 0.005


def read_new(path, offset):
    """Bytes appended to the request file since byte `offset`.

    The file is reopened on every call: the run folder is on the Windows mount, where a
    long-lived read handle failed once with OSError 61 (Phase 2). A failed read counts as
    "nothing new yet"; the same bytes are read again on the next call.
    """
    try:
        with open(path, "rb") as stream:
            stream.seek(offset)
            return stream.read()
    except OSError:
        return b""


def load_translation(run_dir):
    """Two number tables for a checkpoint trained on another game version, or None.

    to_data: this game's unit type number -> the number the same unit has in the data's game.
    to_game: the reverse. A unit is "the same" when its name is the same in both tables.
    The checkpoint folder's unit_defs.json is the data's table (put there by train_standin.py);
    the run folder's unit_defs.json is this game's table (written by standin_control.lua).
    """
    info = json.loads((run_dir / "policy_info.json").read_text())
    if not info.get("checkpoint"):
        return None
    # The checkpoint path is a Windows path (C:/...); this script runs in WSL (/mnt/c/...).
    checkpoint = info["checkpoint"].replace("\\", "/")
    checkpoint = re.sub(r"^([A-Za-z]):", lambda drive: "/mnt/" + drive[1].lower(), checkpoint)
    data_file = Path(checkpoint).parent / "unit_defs.json"
    if not data_file.exists():
        return None
    data = json.loads(data_file.read_text())
    game = json.loads((run_dir / "unit_defs.json").read_text())
    data_number = {name: int(number) for number, name in data["unit_defs"].items()}
    game_number = {name: int(number) for number, name in game.items()}
    shared = set(data_number) & set(game_number)
    return {"to_data": {game_number[name]: data_number[name] for name in shared},
            "to_game": {data_number[name]: game_number[name] for name in shared},
            "summary": {"data_game": data["game"], "unit_types_in_data_game": len(data_number),
                        "unit_types_in_this_game": len(game_number), "names_in_both": len(shared)}}


def to_data_numbers(request, to_data, counts):
    """A copy of the request with unit type numbers as the data's game has them.
    A unit whose name the data's game does not have gets 0, which the model reads as unknown."""
    request = copy.deepcopy(request)
    for unit in request["observation"]["units"] or []:      # an empty unit list arrives as {}
        if "defID" in unit:
            counts["units_seen"] += 1
            counts["units_without_a_match"] += int(unit["defID"]) not in to_data
            unit["defID"] = to_data.get(int(unit["defID"]), 0)
        for queued in unit.get("queue") or []:              # a queued build order is minus a unit number
            if queued.get("id", 0) < 0:
                queued["id"] = -to_data.get(int(-queued["id"]), 0)
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    run_dir = parser.parse_args().run_dir.resolve()
    config = validate_config(json.loads((run_dir / "control_config.json").read_text()))
    url = endpoint_adapter.DEFAULT_URL
    health = get_json(url + "/health")                  # stops here if no server is running
    glue_before = get_json(url + "/stats")["glue_rules_fired"]

    worker = PolicyWorker(factory=endpoint_adapter.make_policy)
    mailbox_dir = Path(tempfile.mkdtemp(prefix="standin_policy_"))   # worker mailbox, Linux side
    worker.start(mailbox_dir)
    started = time.monotonic()
    status, reason = "answered_until_stopped", ""
    offset, buffer, pending = 0, b"", None
    times_ms, deltas, kinds, events_seen = [], [], Counter(), Counter()
    biggest_request, most_units, last_frame = 0, 0, 0
    translation, translation_loaded, counts = None, False, Counter()
    own_units = Counter()
    trace = (run_dir / "policy_trace.jsonl").open("w", encoding="utf-8")

    def record(row):
        trace.write(json.dumps(row) + "\n")
        trace.flush()

    try:
        while not (run_dir / "bridge_stop").exists():       # run_game.py creates it after the game
            if not worker.ready():                           # raises if the worker died
                time.sleep(POLL_SECONDS)
                continue
            fresh = read_new(run_dir / "policy_requests.jsonl", offset)
            offset += len(fresh)
            buffer += fresh
            while b"\n" in buffer:                           # complete lines only
                line, buffer = buffer.split(b"\n", 1)
                event = json.loads(line)
                events_seen[event["kind"]] += 1
                last_frame = max(last_frame, event.get("engine_frame", 0))
                if event["kind"] == "policy_request":
                    if pending is not None:
                        raise ProtocolError("Second policy request before completing the first")
                    accepted = time.monotonic()              # the budget clock starts here
                    request = validate_request(event["request"])
                    pending = {"request": request, "accepted": accepted,
                               "deadline": accepted + config["policy_timeout_seconds"]}
                    biggest_request = max(biggest_request, len(line))
                    most_units = max(most_units, len(request["observation"]["units"]))
                    # The controlled team's finished units by type number, as of this request.
                    own_units = Counter(int(unit["defID"]) for unit in request["observation"]["units"] or []
                                        if unit["teamID"] == request["team_id"] and unit["buildProgress"] >= 1)
                    if not translation_loaded:               # here, not at start: the widget writes
                        translation = load_translation(run_dir)      # this game's table when it loads
                        translation_loaded = True
                    if translation:
                        worker.submit(to_data_numbers(event["request"], translation["to_data"], counts))
                    else:
                        worker.submit(event["request"])      # the raw request, as in the live loop
                else:
                    if event["kind"] == "policy_response_received":
                        deltas.append(event["engine_frame"] - event["pending_from_frame"])
                        event.pop("response")                # already in the decision row
                    record(event)                            # small widget events, kept as they are
            if pending is not None:
                reply = worker.poll()                        # validated by PolicyWorker
                failure = deadline_failure(time.monotonic(), started, config, pending)
                if failure:                                  # a reply at or after the deadline is dropped
                    raise EpisodeFailure(*failure)
                if reply is not None:
                    action = reply.get("action", {})
                    if translation and action.get("kind") == "order" and action["command_id"] < 0:
                        number = translation["to_game"].get(-action["command_id"])
                        counts["build_orders"] += 1
                        if number is None:                   # that unit does not exist in this game
                            counts["build_orders_without_a_match"] += 1
                            reply["action"] = action = {"kind": "noop"}
                        else:
                            action["command_id"] = -number
                    atomic_json(run_dir / "policy_response.json", reply)
                    elapsed_ms = (time.monotonic() - pending["accepted"]) * 1000
                    worker.complete()
                    kinds[action.get("kind", "reset")] += 1
                    if reply["op"] == "predict":
                        times_ms.append(round(elapsed_ms, 3))
                    record({"kind": "decision", "op": reply["op"], "decision_id": reply["decision_id"],
                            "source_frame": reply["source_frame"], "round_trip_ms": round(elapsed_ms, 3),
                            "units_observed": len(pending["request"]["observation"]["units"]),
                            "action": action})
                    pending = None
            time.sleep(POLL_SECONDS)
    except (EpisodeFailure, PolicyWorkerError) as error:
        status, reason = error.status, str(error)
    except (ProtocolError, json.JSONDecodeError, KeyError) as error:
        status, reason = "protocol_error", f"{type(error).__name__}: {error}"
    finally:
        ended = time.monotonic()
        cleanup_errors = worker.close()
        trace.close()

    failed_call = None
    if pending is not None and status != "answered_until_stopped":
        request = pending["request"]
        failed_call = {"op": request["op"], "decision_id": request["decision_id"],
                       "source_frame": request["source_frame"],
                       "elapsed_seconds": round(ended - pending["accepted"], 3),
                       "budget_seconds": config["policy_timeout_seconds"]}
    glue_after = get_json(url + "/stats")["glue_rules_fired"]
    names = {}                                          # this game's unit type table, from the widget
    if (run_dir / "unit_defs.json").exists():
        names = json.loads((run_dir / "unit_defs.json").read_text())
    summary = {
        "source": "standin", "policy_status": status, "reason": reason, "endpoint": health,
        "decisions": {"resets_answered": kinds["reset"], "predicts_answered": len(times_ms),
                      "requests_seen": events_seen["policy_request"],
                      "open_when_stopped": pending is not None},
        "action_kinds": {kind: kinds[kind] for kind in ("noop", "order")},
        # None when the checkpoint folder has no unit_defs.json (no translation was done).
        "unit_type_translation": dict(translation["summary"], **counts) if translation else None,
        # Finished units of the controlled team at the last decision, by unit type name.
        "own_units_at_last_decision": {names.get(str(number), str(number)): count
                                       for number, count in sorted(own_units.items())},
        "orders_submitted": events_seen["order_submitted"],
        "orders_dropped_by_widget": events_seen["order_dropped"],
        "engine_callbacks_tied_to_a_decision": events_seen["engine_command_callback"],
        # The server counts since it started; the difference is this game's share.
        "glue_rules_fired": {rule: glue_after[rule] - glue_before.get(rule, 0) for rule in glue_after},
        "predict_round_trip_ms": {"count": len(times_ms), "p50": percentile(times_ms, 50),
                                  "p95": percentile(times_ms, 95), "p99": percentile(times_ms, 99),
                                  "max": percentile(times_ms, 100)},
        "policy_budget_seconds": config["policy_timeout_seconds"],
        "failed_calls_by_status": {status: 1} if failed_call else {}, "failed_policy_call": failed_call,
        "pending_frame_advance": {"responses": len(deltas), "p50": percentile(deltas, 50),
                                  "p95": percentile(deltas, 95), "max": max(deltas, default=None),
                                  "responses_with_advance": sum(delta > 0 for delta in deltas)},
        "timing_mode": config["timing_mode"], "decision_interval_frames": config["decision_interval_frames"],
        "largest_request_bytes": biggest_request, "most_units_in_an_observation": most_units,
        "last_event_frame": last_frame, "bridge_wall_seconds": round(ended - started, 3),
        "widget_events": dict(events_seen), "cleanup_errors": cleanup_errors,
    }
    (run_dir / "policy_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    shutil.rmtree(mailbox_dir, ignore_errors=True)
    print(f"bridge: {status} {reason}".rstrip())


if __name__ == "__main__":      # required: PolicyWorker spawns a child that re-imports this file
    main()
