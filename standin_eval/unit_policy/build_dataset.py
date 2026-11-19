#!/usr/bin/env python3
"""STAND-IN: Team A's restored human matches -> compact arrays for the unit policy.

    python standin_eval/unit_policy/build_dataset.py --name unit-v1 --per-match 15000

One training example = one recorded order seen from one unit that received it:
(the player's state one frame before, which unit, what the order was). For every match it
writes shared/data/<name>/<replay_id>.npz. The state itself is stored once per
(team, frame) as arrays (common.featurize), not as JSON, so all 20 matches fit in memory.
--per-match caps the examples taken from one match (a random sample, seeded), so the few
very long matches do not outweigh the others. Nothing here is a result of any team.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import json
from pathlib import Path
import random
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from common import A

RESTORED = common.SHARED / "data" / "data05-native"                 # made by Team A's restore script
TEAM_A = common.SHARED.parent / "team-a-data"                       # checkout of origin/team-a
sys.path.insert(0, str(TEAM_A / "scripts"))
MANIFEST = TEAM_A / "evidence" / "data-05" / "native-v1" / "validated_manifest.csv"
RECIPIENTS_PER_ORDER = 3         # a group order gives one example for at most this many of its units


def convert(job):
    """One match -> one .npz. Runs in a worker process. Returns counts for the manifest."""
    replay_id, split, map_name, out_dir, per_match, seed = job
    from state_stream import iter_states                             # Team A's reader
    folder = RESTORED / replay_id
    rng = random.Random(seed)
    rows = [json.loads(line) for line in open(folder / "paired" / "state_command_pairs.jsonl", encoding="utf-8")]
    skipped = {"unsupported order form": 0, "recipient not in the state": 0, "target not in the state": 0,
               "command never chosen in a game": 0}
    wanted = []                                  # (state key, unit id, row)
    for row in rows:
        if common.blocked(row["action"]["command_id"]):
            skipped["command never chosen in a game"] += 1
            continue
        if common.type_of(row["action"]) is None:
            skipped["unsupported order form"] += 1
            continue
        ids = row["action"]["unit_ids"]
        for unit_id in rng.sample(ids, min(len(ids), RECIPIENTS_PER_ORDER)):
            wanted.append(((int(row["state_ref"][0]), int(row["state_ref"][1])), unit_id, row))
    if len(wanted) > per_match:
        wanted = rng.sample(wanted, per_match)
    needed = {}                                  # state key -> unit ids that must survive the cap
    for key, unit_id, _ in wanted:
        needed.setdefault(key, set()).add(unit_id)

    states, unit_blocks = {}, []                 # state key -> (number, row of each unit id)
    resources, offsets = [], [0]
    for record in iter_states(folder / "data" / "bar_state_frames.native.bin"):
        key = (int(record["viewTeam"]), int(record["frame"]))
        if key not in needed:
            continue
        arrays = common.featurize(record["state"], record["viewTeam"], record["frame"], needed[key])
        states[key] = (len(resources), {int(uid): row for row, uid in enumerate(arrays["unit_id"])})
        unit_blocks.append(arrays)
        resources.append(arrays["resources"])
        offsets.append(offsets[-1] + len(arrays["unit_id"]))

    examples = {name: [] for name in ("state", "unit", "command_id", "append", "target", "dx", "dz",
                                          "facing", "radius", "options")}
    keys = []
    for key, unit_id, row in wanted:
        action = row["action"]
        type_key, form, _ = common.type_of(action)
        if key not in states or unit_id not in states[key][1]:
            skipped["recipient not in the state"] += 1
            continue
        number, row_of = states[key]
        unit_row, params = row_of[unit_id], action["params"]
        target = row_of.get(int(params[0]), -1) if form == "unit" else -1
        if form == "unit" and target < 0:
            skipped["target not in the state"] += 1
            continue
        numbers = unit_blocks[number]["numbers"][unit_row]
        # An order appended to a queue (shift held, queue has a position) is placed relative to
        # the queue's last position; any other order relative to the unit itself.
        append = bool(action["options"] & common.SHIFT) and numbers[8] > 0
        x, z = (numbers[6], numbers[7]) if append else (numbers[0], numbers[1])
        located = form in ("pos", "area", "build")
        keys.append(type_key)
        examples["state"].append(number)
        examples["unit"].append(unit_row)
        examples["command_id"].append(action["command_id"])
        examples["append"].append(int(append))
        examples["target"].append(target)
        examples["dx"].append(common.offset_class(params[0] - x) if located else -1)
        examples["dz"].append(common.offset_class(params[2] - z) if located else -1)
        examples["facing"].append(int(params[3]) if form == "build" else -1)
        examples["radius"].append(A.radius_bin(params[3]) if form == "area" else -1)
        examples["options"].append(action["options"])

    np.savez_compressed(
        out_dir / f"{replay_id}.npz", type_key=np.array(keys),
        **{name: np.array(values, np.int32) for name, values in examples.items()},
        offsets=np.array(offsets, np.int64), resources=np.array(resources, np.float32),
        **{name: np.concatenate([block[name] for block in unit_blocks])
           for name in ("unit_id", "def_id", "queue_command", "tail_command", "numbers")})
    return {"replay_id": replay_id, "split": split, "map": map_name, "order_rows": len(rows),
            "examples": len(keys), "states": len(resources), "units_stored": int(offsets[-1]),
            "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="folder to create under shared/data")
    parser.add_argument("--per-match", type=int, default=15000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    out_dir = common.SHARED / "data" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    matches = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    jobs = [(m["replay_id"], m["split"], m["map_name"], out_dir, args.per_match, index)
            for index, m in enumerate(matches)]
    with ProcessPoolExecutor(args.workers) as pool:
        done = []
        for result in pool.map(convert, jobs):
            done.append(result)
            print(json.dumps(result), flush=True)
    manifest = {"source": "standin",
                "note": "Local test data made from Team A's DATA-05 native-v1 release. Not a result of any team.",
                "game": matches[0]["game_version"], "per_match_cap": args.per_match,
                "recipients_per_order": RECIPIENTS_PER_ORDER, "unit_cap": common.UNIT_CAP,
                "split": "by whole match (Team A's split)", "matches": done}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
