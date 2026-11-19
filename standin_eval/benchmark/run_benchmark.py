#!/usr/bin/env python3
"""STAND-IN: play every episode of a benchmark suite with one policy; keep one row per episode.

    python standin_eval/benchmark/run_benchmark.py --label scripted --policy scripted
    python standin_eval/benchmark/run_benchmark.py --label unit-v2b --checkpoint unit-v2b
    python standin_eval/benchmark/run_benchmark.py --label standin-human-v1 --policy b03 --checkpoint standin-human-v1
    python standin_eval/benchmark/run_benchmark.py --label builtin-barb --policy builtin-barb    # reference

The suite (pilot_suite.json) is the pinned list of games. Each episode is one game played by
fullgame/run_fullgame.ps1 with a replay saved. Rows go to
shared/status/benchmark/<suite name>/<label>.jsonl. Running the same command again plays only
the episodes that have no row yet (so a stopped run can be continued); --again replays all.
A game that could not be played still gets a row (outcome "runner_error"). The numbers are
copied from the run folder's files; nothing is judged here. Local test fixture.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
TEAM_D = HERE.parents[1]
SHARED = TEAM_D.parent / "shared"
FULLGAME = TEAM_D / "standin_eval" / "fullgame"
UNIT_SERVER = TEAM_D / "standin_eval" / "unit_policy" / "unit_server.py"


def play(episode, suite, args):
    """One game. Returns its run folder. Raises if the game did not produce one within the limit below."""
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(FULLGAME / "run_fullgame.ps1"),
               "-Opponent", episode["opponent"], "-CapMinutes", str(episode["cap_minutes"])]
    if suite["save_replay"]:
        command.append("-SaveReplay")
    if suite["place_builds"]:
        command.append("-PlaceBuilds")
    if args.policy == "builtin-barb":
        # Reference: the built-in BARb AI plays team 0 itself. This is run_game.py's recording
        # run (BARb in team 0's slot, no policy, no bridge), started the way run_fullgame.ps1 starts a game.
        linux = "/mnt/" + str(FULLGAME)[0].lower() + str(FULLGAME)[2:].replace(chr(92), "/")
        command = ["wsl", "-d", "Ubuntu-24.04", "--cd", linux, "--", "bash", "-c",
                   "~/bar-data/venv/bin/python scripts/run_game.py --record --save-replay --games 1 "
                   f"--cap-minutes {episode['cap_minutes']} --opponent {episode['opponent']}"]
    elif args.policy == "scripted":
        command += ["-Policy", "scripted"]
    elif args.policy == "b03":
        # A checkpoint in Team B's B03 format (h1_best.pt), served by Team C's stand-in server,
        # sampled with the repeat number as seed. The model is given the suite's map name.
        command += ["-Checkpoint", str(SHARED / "ckpt" / args.checkpoint / "h1_best.pt"),
                    "-MapName", suite["map"], "-Sample", "-SampleSeed", str(episode["repeat"])]
    else:       # a unit-policy checkpoint; the repeat number is its sampling seed
        command += ["-Checkpoint", str(SHARED / "ckpt" / args.checkpoint / "unit_policy.pt"),
                    "-PolicyServer", str(UNIT_SERVER), "-SampleSeed", str(episode["repeat"]),
                    "-Temperature", str(args.temperature),
                    "-KeepRequests"]      # keep every request, so a call that failed can be replayed later
    # wall-clock limit for one game: 20 minutes for a 20 minute cap, 30 for a 40 minute cap
    limit = 600 + 30 * episode["cap_minutes"]
    output = subprocess.run(command, capture_output=True, text=True, timeout=limit).stdout
    found = re.search(r"run folder: (runs/(?:game|record)_\w+)", output)
    if not found:
        raise RuntimeError("no run folder in the output: " + output[-500:])
    run_dir = FULLGAME / found.group(1)
    log = UNIT_SERVER.parent / "server_requests.log"        # the unit server's line per predict call
    if args.policy == "checkpoint" and log.exists():
        shutil.copy2(log, run_dir / "server_requests.log")
    return run_dir


def read(run_dir):
    """The numbers of one finished game, from its run folder."""
    report = (run_dir / "report.txt").read_text()
    result = re.search(r"Result : (.*)", report).group(1)
    winner = re.search(r"Winner : (.*)", report).group(1)
    if result.startswith("game over"):
        outcome = "win" if winner.startswith("team 0") else "loss" if winner.startswith("team 1") else "draw"
    else:
        outcome = "cap" if result.startswith("TIMEOUT") else "incomplete"
    stats = json.loads((run_dir / "teamstats.json").read_text())
    wall = json.loads((run_dir / "wall.json").read_text())
    ours = [sample["teams"][0] for sample in stats["samples"]]
    replays = sorted((run_dir / "demos").glob("*.sdfz")) if (run_dir / "demos").exists() else []
    row = {
        "run": run_dir.name, "outcome": outcome, "result": result, "winner": winner,
        "game_frames": stats["written_frame"], "game_minutes": round(stats["written_frame"] / 1800, 2),
        "wall_seconds": round(wall["ended_unix"] - wall["started_unix"], 1),
        # Outcome-specific numbers from the team stats samples (team 0 = the policy).
        "killed_value": round(ours[-1]["killedValue"]), "lost_value": round(ours[-1]["lostValue"]),
        "max_metal_income": round(max(s["metalIncome"] for s in ours), 1),
        "max_energy_income": round(max(s["energyIncome"] for s in ours), 1),
        "max_metal_spots": max(s["metalSpots"] for s in ours),
        "replay": f"{run_dir.name}/demos/{replays[0].name}" if replays else None,
    }
    if not (run_dir / "policy_summary.json").exists():      # the built-in AI reference: no policy numbers
        return row
    policy = json.loads((run_dir / "policy_summary.json").read_text())
    predicts = policy["decisions"]["predicts_answered"]
    orders = policy["action_kinds"].get("order", 0)
    callbacks = policy["engine_callbacks_tied_to_a_decision"]
    row.update({
        "policy_status": policy["policy_status"], "failed_policy_call": policy["failed_policy_call"],
        # The policy's replies: how many, how many were "no order", how long they took.
        "predicts_answered": predicts, "noops": policy["action_kinds"].get("noop", 0),
        "noop_share": round(policy["action_kinds"].get("noop", 0) / max(predicts, 1), 3),
        "predict_ms_p50": policy["predict_round_trip_ms"]["p50"],
        "predict_ms_p95": policy["predict_round_trip_ms"]["p95"],
        # Orders: replied by the policy, passed on by the widget, dropped by the widget, and how
        # many led to a command callback from the engine. The last share is our "failed order" number.
        "orders": orders, "orders_submitted": policy["orders_submitted"],
        "orders_dropped_by_widget": policy["orders_dropped_by_widget"],
        "engine_callbacks": callbacks,
        "orders_without_callback_share": round(1 - callbacks / orders, 3) if orders else None,
        "finished_units_at_last_decision": sum(policy["own_units_at_last_decision"].values()),
        # Tries that got no answer and were sent again on a new connection (shared/endpoint_adapter.py
        # writes one line per failed try into the run's bridge.log).
        "adapter_failed_tries": (run_dir / "bridge.log").read_text(errors="replace").count("endpoint_adapter: try"),
    })
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, default=HERE / "pilot_suite.json")
    parser.add_argument("--label", required=True, help="name of this policy in the results (file name)")
    parser.add_argument("--policy", choices=["scripted", "checkpoint", "b03", "builtin-barb"], default="checkpoint")
    parser.add_argument("--checkpoint", help="checkpoint folder under shared/ckpt (unit policy, or B03 format with --policy b03)")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--again", action="store_true", help="replay episodes that already have a row")
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text())
    out = SHARED / "status" / "benchmark" / suite["name"] / f"{args.label}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists() and not args.again:
        done = {json.loads(line)["episode"] for line in out.read_text().splitlines()}
    for episode in suite["episodes"]:
        if episode["id"] in done:
            continue
        row = {"source": "standin", "suite": suite["name"], "label": args.label, "episode": episode["id"],
               "opponent": episode["opponent"], "cap_minutes": episode["cap_minutes"], "repeat": episode["repeat"],
               "policy": args.policy, "checkpoint": args.checkpoint,
               "temperature": args.temperature if args.policy == "checkpoint" else None,
               "played_unix": round(time.time()),
               # settings the policy server reads from the environment (see unit_server.py), as set
               # by whoever started this run, e.g. STANDIN_ARMY_CHECKPOINT
               "server_environment": {name: value for name, value in os.environ.items() if name.startswith("STANDIN_")}}
        try:
            row.update(read(play(episode, suite, args)))
        except Exception as error:                      # crash, timeout, missing file: keep it as a row
            row.update(outcome="runner_error", error=f"{type(error).__name__}: {error}"[:500])
        with out.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps({key: row.get(key) for key in ("label", "episode", "outcome", "game_minutes",
                                                         "wall_seconds", "policy_status", "orders")}), flush=True)


if __name__ == "__main__":
    main()
