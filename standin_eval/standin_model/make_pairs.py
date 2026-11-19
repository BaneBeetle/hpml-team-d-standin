#!/usr/bin/env python3
"""STAND-IN: recorded BARb orders -> the pair file format Team B's b03_report.py reads.

    python standin_eval/standin_model/make_pairs.py --name standin-barb \
        --val-games record_A record_B --test-games record_C record_D

Input:  standin_eval/fullgame/runs/record_*/recorded_orders.jsonl (widgets/standin_recorder.lua).
Output: shared/data/<name>/state_command_pairs.jsonl and manifest.json.

Every recorded game goes into one split as a whole: the games named with --val-games and
--test-games, and all other finished recordings as train. Local test data, not Team A's dataset.
"""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

TEAM_D = Path(__file__).resolve().parents[2]
SHARED = TEAM_D.parent / "shared"
RUNS = TEAM_D / "standin_eval" / "fullgame" / "runs"
sys.path.insert(0, str(TEAM_D / "scripts"))
from parse_bar_demo import NAMES    # Team A's command id -> name table, unchanged


def command_name(command_id):
    """The naming Team A's decoder uses, so Team B's type names look like theirs."""
    if command_id < 0:
        return "BUILD_UNITDEF_" + str(-command_id)
    return NAMES.get(command_id, "CUSTOM_" + str(command_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="folder name under shared/data")
    parser.add_argument("--val-games", nargs="+", required=True, help="record_* folder names used for validation")
    parser.add_argument("--test-games", nargs="+", required=True, help="record_* folder names used for test")
    parser.add_argument("--per-game", type=int, default=1500,
                        help="at most this many rows per game, picked at random (keeps the file loadable)")
    parser.add_argument("--min-frames", type=int, default=9000,
                        help="skip recordings shorter than this many frames (e.g. short trial runs)")
    args = parser.parse_args()

    games = []
    for folder in sorted(RUNS.glob("record_*")):
        stats = json.loads((folder / "teamstats.json").read_text(encoding="utf-8", errors="replace"))
        if stats.get("status") in ("game_over", "timeout") and stats["written_frame"] >= args.min_frames:
            games.append((folder, stats))
    names = {folder.name for folder, _ in games}
    missing = [name for name in args.val_games + args.test_games if name not in names]
    if missing or set(args.val_games) & set(args.test_games):
        sys.exit(f"val/test games must be distinct finished recordings; not found: {missing}")

    out_dir = SHARED / "data" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "state_command_pairs.jsonl"
    summary, packet = [], 0
    with out_path.open("w", encoding="utf-8") as out:
        for index, (folder, stats) in enumerate(games):
            split = "train"
            if folder.name in args.val_games:
                split = "val"
            if folder.name in args.test_games:
                split = "test"
            with (folder / "recorded_orders.jsonl").open(encoding="utf-8") as stream:
                lines = stream.readlines()
            recorded = len(lines)
            random.seed(index)                      # the same rows every time this is run
            if len(lines) > args.per_game:
                lines = random.sample(lines, args.per_game)
            for line in lines:
                row = json.loads(line)
                order = row["action"]
                command_id = int(order["command_id"])
                packet += 1
                # The keys Team B's code reads. "split" and "game" are stand-in additions:
                # train_standin.py splits on "split" instead of the minute within one match.
                action = {"command_id": command_id, "command_name": command_name(command_id),
                          "unit_ids": [int(unit) for unit in order["unit_ids"]],
                          "params": order["params"] if isinstance(order["params"], list) else [],
                          "options": int(order["options"]), "pairwise": False,
                          "frame": int(order["frame"]), "packet_index": packet,
                          "split": split, "game": folder.name}
                out.write(json.dumps({"state_frame": int(row["state_frame"]), "state_phase": "GameFrame",
                                      "action_frame": int(order["frame"]), "player_id": int(row["player_id"]),
                                      "view_team": int(row["view_team"]), "state": row["state"],
                                      "action": action}) + "\n")
            summary.append({"game": folder.name, "split": split, "status": stats["status"],
                            "frames": stats["written_frame"], "rows_recorded": recorded,
                            "rows_written": len(lines)})

    manifest = {
        "source": "standin",
        "note": "Orders given by the BARb AI in local BARb vs BARb games, recorded by "
                "standin_recorder.lua. Local test data for a stand-in model. Not Team A's dataset.",
        "map": games[0][1]["map"], "game": games[0][1]["game"], "engine": games[0][1]["engine"],
        "sampling": "one order per team per 15-frame window, chosen at random among that window's orders; "
                    f"at most {args.per_game} rows per game",
        "split": "by whole game", "games": summary,
        "rows": {split: sum(g["rows_written"] for g in summary if g["split"] == split)
                 for split in ("train", "val", "test")},
        "file": out_path.name, "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("map", "rows", "sha256")}))
    for game in summary:
        print(game)
    print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
