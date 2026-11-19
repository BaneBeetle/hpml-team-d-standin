#!/usr/bin/env python3
"""STAND-IN: play a fixed set of games with one unit-policy checkpoint and record the numbers.

    python standin_eval/unit_policy/evaluate.py --name unit-v1a
    python standin_eval/unit_policy/evaluate.py --name unit-v1a --temperature 0.7 --games null:10:1 simple:20:1

Each game is "opponent:cap minutes:seed" and is played with fullgame/run_fullgame.ps1 (map
Supreme Isthmus v2.1, team 0 Armada, the widget's build placement on). One line per game is
appended to shared/status/unit_policy_results.jsonl: the settings, the result, team 0's
economy at the last stats sample and its finished units. The numbers are copied from the
run folder's files; nothing is judged here. Local test fixture.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

FULLGAME = common.TEAM_D / "standin_eval" / "fullgame"
RESULTS = common.SHARED / "status" / "unit_policy_results.jsonl"
DEFAULT_GAMES = ["null:10:1", "null:10:2", "simple:20:1", "simple:20:2", "barb-easy:20:1"]


def play(name, opponent, minutes, seed, temperature):
    """One game. Returns the run folder."""
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(FULLGAME / "run_fullgame.ps1"),
               "-Checkpoint", str(common.SHARED / "ckpt" / name / "unit_policy.pt"),
               "-PolicyServer", str(Path(__file__).resolve().parent / "unit_server.py"),
               "-SampleSeed", str(seed), "-Temperature", str(temperature), "-PlaceBuilds",
               "-Opponent", opponent, "-CapMinutes", str(minutes)]
    output = subprocess.run(command, capture_output=True, text=True, timeout=900).stdout   # 15 minutes at most
    found = re.search(r"run folder: (runs/game_\w+)", output)
    if not found:
        raise RuntimeError("No run folder in the output:\n" + output[-2000:])
    return FULLGAME / found.group(1)


def read(run_dir, name, opponent, minutes, seed, temperature):
    """The numbers of one finished game, from its run folder."""
    stats = json.loads((run_dir / "teamstats.json").read_text())
    policy = json.loads((run_dir / "policy_summary.json").read_text())
    report = (run_dir / "report.txt").read_text()
    result = re.search(r"Result : (.*)", report).group(1)
    last = stats["samples"][-1]
    ours, theirs = last["teams"][0], last["teams"][1]
    units = policy["own_units_at_last_decision"]
    return {"source": "standin", "checkpoint": name, "opponent": opponent, "cap_minutes": minutes,
            "seed": seed, "temperature": temperature, "run": run_dir.name, "result": result,
            "last_sample_seconds": last["seconds"],
            "metal_income": round(ours["metalIncome"], 1), "energy_income": round(ours["energyIncome"], 1),
            "metal_spots": ours["metalSpots"], "killed_value": round(ours["killedValue"]),
            "lost_value": round(ours["lostValue"]),
            "opponent_metal_income": round(theirs["metalIncome"], 1),
            "finished_units": sum(units.values()), "units": units,
            "orders": policy["orders_submitted"], "orders_dropped": policy["orders_dropped_by_widget"],
            "noops": policy["action_kinds"]["noop"], "policy_status": policy["policy_status"],
            "predict_ms_p95": policy["predict_round_trip_ms"]["p95"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="checkpoint folder under shared/ckpt")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--games", nargs="+", default=DEFAULT_GAMES)
    parser.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE",
                        help="server settings, e.g. STANDIN_QUEUE_DEPTH=1 (see unit_server.py)")
    args = parser.parse_args()
    server_settings = dict(pair.split("=", 1) for pair in args.set)
    os.environ.update(server_settings)          # the server is started from here and inherits them
    for game in args.games:
        opponent, minutes, seed = game.split(":")
        run_dir = play(args.name, opponent, float(minutes), int(seed), args.temperature)
        row = read(run_dir, args.name, opponent, float(minutes), int(seed), args.temperature)
        row["server_settings"] = server_settings
        with RESULTS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        short = dict(row, units=len(row["units"]))
        print(json.dumps(short), flush=True)


if __name__ == "__main__":
    main()
