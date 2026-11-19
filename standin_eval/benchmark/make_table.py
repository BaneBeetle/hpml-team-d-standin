#!/usr/bin/env python3
"""STAND-IN: the rows of run_benchmark.py -> one comparison table (Markdown).

    python standin_eval/benchmark/make_table.py                # suite pilot-v1
    python standin_eval/benchmark/make_table.py --suite-name pilot-v1

Reads shared/status/benchmark/<suite name>/<label>.jsonl (one file per policy) and writes
table.md beside them: every episode, then one line per policy and opponent, then how long the
games took. Only counts, means and ranges; nothing is judged here. Local test fixture.
"""

import argparse
import json
from pathlib import Path
from statistics import mean

SHARED = Path(__file__).resolve().parents[3] / "shared"


def show(value, digits=1):
    """A number for a table cell; '-' when there is none."""
    if value is None:
        return "-"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def spread(values, digits=1):
    """'mean (lowest to highest)' of the values that exist."""
    values = [value for value in values if value is not None]
    if not values:
        return "-"
    return f"{mean(values):.{digits}f} ({min(values):.{digits}f} to {max(values):.{digits}f})"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite-name", default="pilot-v1")
    args = parser.parse_args()
    folder = SHARED / "status" / "benchmark" / args.suite_name
    rows = [json.loads(line) for path in sorted(folder.glob("*.jsonl")) for line in path.read_text().splitlines()]
    for row in rows:                # rows of the built-in AI reference have no policy numbers
        for key in ("policy_status", "predicts_answered", "noop_share", "orders", "orders_dropped_by_widget",
                    "orders_without_callback_share", "predict_ms_p50", "predict_ms_p95"):
            row.setdefault(key, None)
    played = [row for row in rows if row["outcome"] != "runner_error"]

    lines = [f"# Benchmark {args.suite_name}: stand-in pilot table", "",
             "Local test fixture (source: standin). Settings of every game: its run folder's run_settings.json.",
             "", "## Every episode", "",
             "| Policy | Episode | Outcome | Game min | Wall s | Policy status | Predicts | No-order share | "
             "Orders | Dropped by widget | Without engine callback | p50 / p95 ms | Killed / lost value | "
             "Max metal income | Run folder |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        if row["outcome"] == "runner_error":
            lines.append(f"| {row['label']} | {row['episode']} | runner_error: {row['error'][:80]} |" + " - |" * 12)
            continue
        lines.append(
            f"| {row['label']} | {row['episode']} | {row['outcome']} | {show(row['game_minutes'])} | "
            f"{show(row['wall_seconds'], 0)} | {show(row['policy_status'])} | {show(row['predicts_answered'])} | "
            f"{show(row['noop_share'], 3)} | {show(row['orders'])} | {show(row['orders_dropped_by_widget'])} | "
            f"{show(row['orders_without_callback_share'], 3)} | {show(row['predict_ms_p50'])} / "
            f"{show(row['predict_ms_p95'])} | {row['killed_value']} / {row['lost_value']} | "
            f"{show(row['max_metal_income'])} | {row['run']} |")

    lines += ["", "## Per policy and opponent", "",
              "Cells with three numbers are: mean (lowest to highest) over the episodes.", "",
              "Win rate = games won / games played; a game that reached the cap without a winner is not a win.", "",
              "| Policy | Opponent | Episodes | Win rate | Win / loss / cap | Policy stopped early | Game min | "
              "No-order share | Orders without engine callback | p95 ms |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    groups = {}                                 # (policy label, opponent) -> rows, in first-seen order
    for row in played:
        groups.setdefault((row["label"], row["opponent"]), []).append(row)
    for (label, opponent), group in groups.items():
        outcomes = [row["outcome"] for row in group]
        # a built-in AI row has no policy status (None): there is no policy that could stop
        stopped = sum(row["policy_status"] not in ("answered_until_stopped", None) for row in group)
        lines.append(
            f"| {label} | {opponent} | {len(group)} | {outcomes.count('win')} of {len(group)} | "
            f"{outcomes.count('win')} / {outcomes.count('loss')} / "
            f"{outcomes.count('cap')} | {stopped} | {spread([row['game_minutes'] for row in group])} | "
            f"{spread([row['noop_share'] for row in group], 3)} | "
            f"{spread([row['orders_without_callback_share'] for row in group], 3)} | "
            f"{spread([row['predict_ms_p95'] for row in group])} |")

    # How long it takes. Games were played one at a time, so games per hour = games / total wall time.
    wall = [row["wall_seconds"] for row in played]
    if wall:
        lines += ["", "## Time", "",
                  f"- Episodes played: {len(played)} (runner errors: {len(rows) - len(played)}).",
                  f"- Wall time per game, engine start to exit: {spread(wall, 0)} seconds.",
                  f"- One game at a time: {len(played) / sum(wall) * 3600:.1f} games per hour "
                  f"({sum(wall) / 60:.1f} minutes for {len(played)} games; the server start and the image "
                  "check before each game are not in this time).",
                  f"- Game time played: {sum(row['game_minutes'] for row in played):.0f} minutes."]
    (folder / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
