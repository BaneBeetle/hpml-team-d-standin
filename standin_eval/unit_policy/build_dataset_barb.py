#!/usr/bin/env python3
"""STAND-IN: orders the BARb AI gave in our own recorded games -> arrays for the unit policy.

    python standin_eval/unit_policy/build_dataset_barb.py --name unit-barb-v1 --validation 2 --test 2

Input: standin_eval/fullgame/runs/record_*/recorded_orders.jsonl (BARb vs BARb games on
bar-harness's game version, written by widgets/standin_recorder.lua). One row there = one
team's observation at the start of a 15-frame window plus the orders its units got in that
window. Output: shared/data/<name>/<game>.npz in the layout of build_dataset.py, so train.py
reads it unchanged, plus manifest.json and unit_defs.json (this game version's unit types).

Per window, a unit gives one example at most: its FIRST order of the window that the model
can give (queue edits and left-out commands are passed over), because later ones were given
in a state the observation does not show. Whole games go to one split: the
last --validation recordings (by folder name) are validation, the --test ones before them
test, the rest train. Local test data; nothing here is a result of any team.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import random
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from common import A

sys.path.insert(0, str(common.TEAM_D / "standin_eval" / "standin_model"))
from make_pairs import command_name        # command id -> Team A's command names

RUNS = common.TEAM_D / "standin_eval" / "fullgame" / "runs"


def convert(job):
    """One recorded game -> one .npz. Runs in a worker process. Returns counts for the manifest."""
    folder, split, out_dir, per_window, seed = job
    rng = random.Random(seed)
    skipped = {"unsupported order form": 0, "recipient not in the state": 0, "target not in the state": 0,
               "command never chosen in a game": 0, "not the unit's first order of the window": 0}
    examples = {name: [] for name in ("state", "unit", "command_id", "append", "target", "dx", "dz",
                                      "facing", "radius", "options")}
    keys, unit_blocks, resources, offsets, rows = [], [], [], [0], 0
    start_of, homes = {}, []        # team -> (x, z) of its first own unit; one home per stored state
    # Only the teams played by BARb with its default profile are learned from. Some recordings
    # have SimpleAI or BARb "easy" on team 1 (the benchmark's reference games).
    teams = json.loads((folder / "run_settings.json").read_text())["teams"]
    learn_from = {team["team"] for team in teams if team["ai_short_name"] == "BARb" and not team["ai_profile"]}
    skipped["windows of a team that is not default BARb"] = 0
    with open(folder / "recorded_orders.jsonl", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:                           # a line the game did not finish writing
                skipped["unreadable line"] = skipped.get("unreadable line", 0) + 1
                continue
            if int(row["view_team"]) not in learn_from:
                skipped["windows of a team that is not default BARb"] += 1
                continue
            rows += 1
            team = int(row["view_team"])
            if team not in start_of:                     # the first window: the team's commander
                own = [u for u in row["state"]["units"] if u["teamID"] == team]
                if own:
                    start_of[team] = (own[0]["position"][0], own[0]["position"][2])
            # Old recordings kept one order per window ("action"); new ones keep the list.
            orders = row.get("actions") or [row["action"]]
            # unit id -> its first order of the window that the model can give. BARb often
            # sends a queue edit first (REMOVE of a WAIT) and the real order right after it.
            first = {}
            for order in orders:
                unit_id, command_id = int(order["unit_ids"][0]), int(order["command_id"])
                params = order["params"] if isinstance(order["params"], list) else []    # empty arrives as {}
                action = {"command_id": command_id, "command_name": command_name(command_id),
                          "params": params, "options": int(order["options"])}
                if common.blocked(command_id):
                    skipped["command never chosen in a game"] += 1
                elif common.type_of(action) is None:
                    skipped["unsupported order form"] += 1
                elif unit_id in first:
                    skipped["not the unit's first order of the window"] += 1
                else:
                    first[unit_id] = action
            chosen = list(first.items())
            if len(chosen) > per_window:
                chosen = rng.sample(chosen, per_window)
            arrays, row_of = None, None
            for unit_id, action in chosen:
                command_id, params = action["command_id"], action["params"]
                type_key, form, _ = common.type_of(action)
                if arrays is None:                       # the state is stored once, at its first example
                    arrays = common.featurize(row["state"], row["view_team"], row["state_frame"], list(first))
                    row_of = {int(uid): number for number, uid in enumerate(arrays["unit_id"])}
                if unit_id not in row_of:
                    skipped["recipient not in the state"] += 1
                    continue
                target = row_of.get(int(params[0]), -1) if form == "unit" else -1
                if form == "unit" and target < 0:
                    skipped["target not in the state"] += 1
                    continue
                numbers = arrays["numbers"][row_of[unit_id]]
                append = bool(action["options"] & common.SHIFT) and numbers[8] > 0     # as in build_dataset.py
                x, z = (numbers[6], numbers[7]) if append else (numbers[0], numbers[1])
                located = form in ("pos", "area", "build")
                keys.append(type_key)
                examples["state"].append(len(resources))
                examples["unit"].append(row_of[unit_id])
                examples["command_id"].append(command_id)
                examples["append"].append(int(append))
                examples["target"].append(target)
                examples["dx"].append(common.offset_class(params[0] - x) if located else -1)
                examples["dz"].append(common.offset_class(params[2] - z) if located else -1)
                examples["facing"].append(int(params[3]) if form == "build" else -1)
                examples["radius"].append(A.radius_bin(params[3]) if form == "area" else -1)
                examples["options"].append(action["options"])
            if arrays is not None and examples["state"] and examples["state"][-1] == len(resources):
                unit_blocks.append(arrays)               # at least one example uses this state
                resources.append(arrays["resources"])
                homes.append(start_of.get(team, (0.0, 0.0)))
                offsets.append(offsets[-1] + len(arrays["unit_id"]))

    np.savez_compressed(
        out_dir / f"{folder.name}.npz", type_key=np.array(keys),
        **{name: np.array(values, np.int32) for name, values in examples.items()},
        offsets=np.array(offsets, np.int64), resources=np.array(resources, np.float32),
        home=np.array(homes, np.float32),               # per state: where that team started
        **{name: np.concatenate([block[name] for block in unit_blocks])
           for name in ("unit_id", "def_id", "queue_command", "tail_command", "numbers")})
    return {"replay_id": folder.name, "split": split, "windows": rows, "examples": len(keys),
            "states": len(resources), "units_stored": int(offsets[-1]), "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="folder to create under shared/data")
    parser.add_argument("--validation", type=int, default=2, help="how many recordings are validation")
    parser.add_argument("--test", type=int, default=2)
    parser.add_argument("--per-window", type=int, default=16, help="most examples from one team's window")
    parser.add_argument("--min-frames", type=int, default=9000, help="skip recordings shorter than this")
    parser.add_argument("--all-orders-only", action="store_true",
                        help="leave out old recordings that kept one order per window")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    games, info = [], None
    for folder in sorted(RUNS.glob("record_*")):
        stats = json.loads((folder / "teamstats.json").read_text(encoding="utf-8", errors="replace"))
        if stats.get("status") not in ("game_over", "timeout") or stats["written_frame"] < args.min_frames:
            continue
        with open(folder / "recorded_orders.jsonl", encoding="utf-8") as stream:
            has_all = '"actions":' in stream.readline()
        if has_all or not args.all_orders_only:
            games.append(folder)
            info = stats
    held_out = args.validation + args.test
    splits = (["train"] * (len(games) - held_out) + ["test"] * args.test + ["validation"] * args.validation)
    out_dir = common.SHARED / "data" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(folder, split, out_dir, args.per_window, index)
            for index, (folder, split) in enumerate(zip(games, splits))]
    done = []
    with ProcessPoolExecutor(args.workers) as pool:
        for result in pool.map(convert, jobs):
            done.append(result)
            print(json.dumps(result), flush=True)

    # This game version's unit type table (number -> name), in the form the full-game bridge
    # reads from a checkpoint folder. Taken from the newest policy game's run folder.
    newest = sorted(RUNS.glob("game_*/unit_defs.json"))[-1]
    (out_dir / "unit_defs.json").write_text(json.dumps(
        {"source": "standin", "game": info["game"], "taken_from": newest.parent.name,
         "unit_defs": json.loads(newest.read_text())}), encoding="utf-8")
    manifest = {"source": "standin",
                "note": "Orders given by the BARb AI in local BARb vs BARb games, recorded by "
                        "standin_recorder.lua. Local test data. Not Team A's dataset.",
                "game": info["game"], "map": info["map"], "per_window_cap": args.per_window,
                "unit_cap": common.UNIT_CAP, "split": "by whole game", "matches": done}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
