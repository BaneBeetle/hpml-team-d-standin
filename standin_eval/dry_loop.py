#!/usr/bin/env python3
"""STAND-IN dry loop: saved requests -> Roshan's PolicyWorker -> the stand-in endpoint. No engine.

The worker, its mailbox files and the deadline check are Roshan's code, unchanged. Only the
engine is missing: instead of a game writing requests, this script reads saved ones.
The endpoint must already be running (team-c: python standin_infer/server.py --policy ...).

    python standin_eval/dry_loop.py --label scripted --source traces
    python standin_eval/dry_loop.py --label model --source data --count 200

Output is a local test fixture, not a result of any team.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]          # the repository root (team-d/)
SHARED = ROOT.parent / "shared"
sys.path.insert(0, str(ROOT / "scripts"))           # for control_loop (Roshan's code)
sys.path.insert(0, str(SHARED))                     # for endpoint_adapter (Team C stand-in)
from control_loop.engine import EpisodeFailure, deadline_failure
from control_loop.policy_worker import PolicyWorker, PolicyWorkerError
from control_loop.protocol import ProtocolError, validate_config, validate_request, validate_response
import endpoint_adapter

TRACES = sorted((ROOT / "evidence" / "policy_timeouts").glob("*/trace.jsonl"))
DATA = SHARED / "data" / "state_command_pairs.jsonl"
EXAMPLE = ROOT / "examples" / "control_loop" / "predict_request.json"
CONFIG = ROOT / "configs" / "control_loop.json"
WORKER_DIR = ROOT / "output" / "standin_eval"       # git-ignored; PolicyWorker puts its mailbox here
POLL_SECONDS = 0.01                                 # the same sleep as the loop in engine.run_episode


def trace_episodes():
    """One episode per saved trace: the requests exactly as the widget wrote them (Lua floats),
    plus the replies Roshan's run recorded, keyed by decision id, to compare against."""
    episodes = []
    for path in TRACES:
        events = [json.loads(line) for line in path.open(encoding="utf-8")]
        requests = [event["request"] for event in events if event["kind"] == "policy_request"]
        recorded = {event["decision_id"]: event["response"]
                    for event in events if event["kind"] == "policy_response"}
        episodes.append({"name": "trace " + path.parent.name[:8], "requests": requests,
                         "recorded": recorded})
    return episodes


def data_episodes(count):
    """Real DATA-01 states wrapped in the request envelope, one episode per viewing team.

    The rows have no envelope and no catalog. validate_request requires a catalog, so every
    request reuses the one from Roshan's example request. It is a placeholder: its unit ids
    are not in this match.
    """
    catalog = json.loads(EXAMPLE.read_text())["catalog"]
    with DATA.open(encoding="utf-8") as stream:
        lines = stream.readlines()
    # `count` rows evenly spaced through the file, so early, middle and late game all appear.
    rows = [json.loads(lines[index * len(lines) // count]) for index in range(count)]
    episodes = []
    for team in sorted({row["view_team"] for row in rows}):
        mine = [row for row in rows if row["view_team"] == team]

        def envelope(op, decision_id, row):
            return {"protocol_version": 1, "op": op, "match_id": f"data01-team{team}",
                    "generation": 0, "player_id": row["player_id"], "team_id": team,
                    "decision_id": decision_id, "source_frame": row["state_frame"],
                    "scheduled_frame": row["state_frame"],
                    "observation_phase": "DATA-01 replay state", "observation": row["state"],
                    "catalog": catalog}

        # PolicyWorker refuses a predict before a reset, so the first state is also sent as the reset.
        requests = [envelope("reset", 0, mine[0])]
        requests += [envelope("predict", number, row) for number, row in enumerate(mine, start=1)]
        episodes.append({"name": f"data01 team {team}", "requests": requests, "recorded": {}})
    return episodes


def run_episode(episode, config):
    """Send one episode's requests through a fresh PolicyWorker, one at a time.

    This follows engine.run_episode: submit, poll every 10 ms, check the deadline after each
    poll, and stop the episode at the first failure. Nothing is retried or replaced.
    """
    worker = PolicyWorker(factory=endpoint_adapter.make_policy)
    started = time.monotonic()
    decisions, status, reason, pending = [], "all_answered", "", None
    try:
        worker.start(WORKER_DIR)
        while not worker.ready():
            failure = deadline_failure(time.monotonic(), started, config, awaiting_startup=True)
            if failure:
                raise EpisodeFailure(*failure)
            time.sleep(POLL_SECONDS)
        for request in episode["requests"]:
            accepted = time.monotonic()     # the budget clock starts here, before the request is sent
            pending = {"request": validate_request(request), "accepted": accepted,
                       "deadline": accepted + config["policy_timeout_seconds"]}
            worker.submit(request)          # the raw request, as in the live loop
            while True:
                reply = worker.poll()       # None until the worker has written its reply file
                failure = deadline_failure(time.monotonic(), started, config, pending)
                if failure:                 # a reply that arrives at or after the deadline is dropped
                    raise EpisodeFailure(*failure)
                if reply is not None:
                    break
                time.sleep(POLL_SECONDS)
            elapsed_ms = (time.monotonic() - accepted) * 1000
            validate_response(request, reply)   # poll() already did this; repeated here on purpose
            worker.complete()
            expected = episode["recorded"].get(pending["request"]["decision_id"])
            decisions.append(decision_row(pending, elapsed_ms, "ok",
                                          kind=reply.get("action", {}).get("kind"),
                                          same=None if expected is None else reply == expected))
            pending = None
    except (EpisodeFailure, PolicyWorkerError) as error:
        status, reason = error.status, str(error)
    except ProtocolError as error:              # engine.run_episode maps this the same way
        status, reason = "protocol_error", str(error)
    finally:
        ended = time.monotonic()                # taken before close(), which can take up to ~2 s
        cleanup_errors = worker.close()
    if pending is not None:                     # the call that was open when the episode failed
        elapsed_ms = (ended - pending["accepted"]) * 1000
        decisions.append(decision_row(pending, elapsed_ms, status))
    return {"name": episode["name"], "status": status, "reason": reason,
            "requests_available": len(episode["requests"]), "decisions": decisions,
            "worker_id": worker.worker_id, "cleanup_errors": cleanup_errors}


def decision_row(pending, elapsed_ms, status, kind=None, same=None):
    request = pending["request"]
    return {"op": request["op"], "decision_id": request["decision_id"],
            "source_frame": request["source_frame"], "round_trip_ms": round(elapsed_ms, 3),
            "action_kind": kind, "status": status, "same_as_recorded": same}


def percentile(values, percent):
    """Nearest rank: the smallest value with at least `percent` % of the values at or below it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)] if ordered else None


def summarize(episode):
    """One table row per episode. Timings cover answered predict calls only."""
    rows = episode["decisions"]
    times = [row["round_trip_ms"] for row in rows if row["op"] == "predict" and row["status"] == "ok"]
    compared = [row["same_as_recorded"] for row in rows if row["same_as_recorded"] is not None]
    return {"episode": episode["name"], "status": episode["status"],
            "sent": len(rows), "of": episode["requests_available"],
            "noop": sum(row["action_kind"] == "noop" for row in rows),
            "order": sum(row["action_kind"] == "order" for row in rows),
            "same_as_recorded": f"{sum(compared)}/{len(compared)}" if compared else "-",
            "p50_ms": percentile(times, 50), "p95_ms": percentile(times, 95),
            "p99_ms": percentile(times, 99), "max_ms": max(times) if times else None}


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # no system proxy
    with opener.open(url, timeout=2) as reply:
        return json.loads(reply.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="name of this run, used in the log file name")
    parser.add_argument("--source", choices=("traces", "data"), required=True)
    parser.add_argument("--count", type=int, default=200, help="how many DATA-01 states (--source data)")
    parser.add_argument("--episodes", type=int, help="only run the first N episodes")
    parser.add_argument("--url", default=endpoint_adapter.DEFAULT_URL)
    args = parser.parse_args()

    config = validate_config(json.loads(CONFIG.read_text()))   # Roshan's budgets, unchanged
    os.environ["STANDIN_POLICY_URL"] = args.url    # the worker process inherits this and reads it
    health = get_json(args.url + "/health")        # fails here if no server is running
    episodes = trace_episodes() if args.source == "traces" else data_episodes(args.count)
    results = [run_episode(episode, config) for episode in episodes[:args.episodes]]
    summary = [summarize(result) for result in results]

    run = {"source": "standin", "label": args.label, "request_source": args.source,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "endpoint": health,
           "endpoint_glue_rules_fired": get_json(args.url + "/stats")["glue_rules_fired"],
           "policy_timeout_seconds": config["policy_timeout_seconds"], "poll_seconds": POLL_SECONDS,
           "summary": summary, "episodes": results}
    log_path = SHARED / "logs" / f"dry_{args.label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    log_path.write_text(json.dumps(run, indent=1), encoding="utf-8")

    print(f"STAND-IN dry loop, label={args.label}, endpoint policy={health['policy']}, "
          f"budget={config['policy_timeout_seconds']} s. Not a result of any team.")
    columns = list(summary[0])
    print(" | ".join(columns))
    for row in summary:
        print(" | ".join(str(row[column]) for column in columns))
    for result in results:
        if result["status"] != "all_answered":
            print(f"{result['name']}: {result['status']}: {result['reason']}")
    print(f"glue rules fired at the endpoint: {run['endpoint_glue_rules_fired']}")
    print(f"log: {log_path}")


if __name__ == "__main__":      # required: PolicyWorker spawns a child that re-imports this file
    main()
