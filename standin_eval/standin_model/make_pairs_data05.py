#!/usr/bin/env python3
"""STAND-IN: Team A's 20-match release -> the pair file layout Team B's b03_report.py reads.

    python standin_eval/standin_model/make_pairs_data05.py --name data05-native-v1

Input:  shared/data/data05-native/<replay id>/, restored with Team A's scripts/restore_data05.py,
        and Team A's validated_manifest.csv (replay id, split and map of every match).
Output: shared/data/<name>/state_command_pairs.jsonl and manifest.json.

Team A's pair rows point at their state with "state_ref": [view_team, state_frame]. Team B's
script wants the state inside the row (the DATA-01 layout). This script reads the states with
Team A's own reader and puts each one into its row. The orders and states are not changed.
Three labels are added to each row's "action" for train_standin.py: "split" (Team A's split of
the whole match), "game" (replay id) and "map". A converted copy for a local test, not a dataset.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import random
import sys

TEAM_D = Path(__file__).resolve().parents[2]
BASE = TEAM_D.parent
TEAM_A = BASE / "team-a-data"                       # local checkout of origin/team-a, nothing edited
RESTORED = BASE / "shared" / "data" / "data05-native"
MANIFEST = TEAM_A / "evidence" / "data-05" / "native-v1" / "validated_manifest.csv"
sys.path.insert(0, str(TEAM_A / "scripts"))
from state_stream import iter_states                # Team A's reader, unchanged

SPLIT_NAMES = {"train": "train", "validation": "val", "test": "test"}    # Team B's code says "val"


def convert(job):
    """One match: pick packets, collect their states, write the rows to <replay id>.part."""
    index, match, out_dir, per_match = job
    folder = RESTORED / match["replay_id"]
    with (folder / "paired" / "state_command_pairs.jsonl").open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    # Sample whole packets, not rows: Team B merges the rows of one packet into one order.
    packets = sorted({row["action"]["packet_index"] for row in rows})
    random.seed(index)                              # the same packets every time this is run
    if len(packets) > per_match:
        packets = random.sample(packets, per_match)
    packets = set(packets)
    kept = [row for row in rows if row["action"]["packet_index"] in packets]     # file order kept

    wanted = {tuple(row["state_ref"]) for row in kept}
    states = {}
    for snapshot in iter_states(folder / "data" / "bar_state_frames.native.bin"):
        key = (int(snapshot["viewTeam"]), int(snapshot["frame"]))
        if key in wanted:
            states[key] = json.dumps(snapshot["state"])     # as text at once: the reader reuses its dicts
            if len(states) == len(wanted):
                break

    part = out_dir / (match["replay_id"] + ".part")
    with part.open("w", encoding="utf-8") as out:
        for row in kept:
            state = states[tuple(row.pop("state_ref"))]
            row["action"].update(split=SPLIT_NAMES[match["split"]], game=match["replay_id"],
                                 map=match["map_name"])
            out.write(json.dumps(row)[:-1] + ',"state":' + state + "}\n")
    return {"game": match["replay_id"], "split": SPLIT_NAMES[match["split"]], "map": match["map_name"],
            "frames": int(match["frames"]), "rows_in_release": len(rows), "packets_kept": len(packets),
            "rows_written": len(kept), "states_sha256": match["states_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="folder name under shared/data")
    parser.add_argument("--per-match", type=int, default=1000,
                        help="at most this many order packets per match, picked at random "
                             "(Team B's loader holds every row's state in memory)")
    parser.add_argument("--workers", type=int, default=6, help="matches converted at the same time")
    args = parser.parse_args()

    with MANIFEST.open(encoding="utf-8", newline="") as stream:
        matches = list(csv.DictReader(stream))
    out_dir = BASE / "shared" / "data" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(index, match, out_dir, args.per_match) for index, match in enumerate(matches)]
    with ProcessPoolExecutor(args.workers) as pool:
        summary = list(pool.map(convert, jobs))     # results come back in manifest order

    out_path = out_dir / "state_command_pairs.jsonl"
    digest = hashlib.sha256()
    with out_path.open("wb") as out:
        for game in summary:
            part = out_dir / (game["game"] + ".part")
            data = part.read_bytes()
            out.write(data)
            digest.update(data)
            part.unlink()

    train_maps = sorted({game["map"] for game in summary if game["split"] == "train"})
    manifest = {
        "source": "standin",
        "note": "Converted copy of Team A's DATA-05 native-v1 release (human duels) for a local "
                "stand-in training test. Team A's data, re-laid-out; not a dataset of its own.",
        "from": "Na00s/hpml origin/team-a evidence/data-05/native-v1 (validated_manifest.csv)",
        "game": matches[0]["game_version"], "engine": "Recoil 2026.07.04",
        "map": f"{len(train_maps)} maps in train (see maps)", "maps": train_maps,
        "sampling": f"at most {args.per_match} order packets per match, chosen at random (seed = "
                    "position in the manifest); every row of a chosen packet is kept",
        "split": "by whole match, Team A's own split", "games": summary,
        "rows": {split: sum(g["rows_written"] for g in summary if g["split"] == split)
                 for split in ("train", "val", "test")},
        "file": out_path.name, "sha256": digest.hexdigest(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["rows"]), manifest["sha256"])
    for game in summary:
        print(game["game"][:8], game["split"], game["map"], game["rows_in_release"], game["rows_written"])
    print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
