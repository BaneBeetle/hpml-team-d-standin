#!/usr/bin/env python3
"""STAND-IN: per full game, count the policy's order replies by command id and its recipients.

    python standin_eval/standin_model/order_counts.py                 # every fullgame/runs/game_*
    python standin_eval/standin_model/order_counts.py <run folder> ...

Reads only files a game already wrote: policy_trace.jsonl (bridge.py), policy_info.json,
teamstats.json. It counts; it does not judge. Local test fixture.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / "fullgame" / "runs"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="*", type=Path)
    folders = parser.parse_args().folders or sorted(RUNS.glob("game_*"))
    for folder in folders:
        info = json.loads((folder / "policy_info.json").read_text(encoding="utf-8-sig"))
        stats = json.loads((folder / "teamstats.json").read_text(encoding="utf-8", errors="replace"))
        rows = [json.loads(line) for line in (folder / "policy_trace.jsonl").open(encoding="utf-8")]
        orders = [row["action"] for row in rows
                  if row["kind"] == "decision" and row["action"].get("kind") == "order"]
        by_command = Counter(order["command_id"] for order in orders)
        recipients = {order["unit_id"] for order in orders}
        if stats["status"] == "game_over":
            result = f"game over, winners {stats['game_over']['winning_teams']}, frame {stats['game_over']['frame']}"
        else:
            result = f"{stats['status']}, frame {stats.get('written_frame')}"
        checkpoint = Path(info["checkpoint"]).parent.name if info.get("checkpoint") else "-"
        print(f"{folder.name} | policy {info['policy']} | checkpoint {checkpoint} | "
              f"sampled {info.get('sampled', False)} | {result}")
        print(f"    order replies {len(orders)} | command ids {len(by_command)} | "
              f"distinct recipients {len(recipients)} | "
              f"submitted {sum(row['kind'] == 'order_submitted' for row in rows)} | "
              f"dropped by widget {sum(row['kind'] == 'order_dropped' for row in rows)}")
        print("    by command id: " + ", ".join(f"{command}: {count}" for command, count in by_command.most_common()))


if __name__ == "__main__":
    main()
