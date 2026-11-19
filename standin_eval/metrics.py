#!/usr/bin/env python3
"""STAND-IN policy-side metrics for live control-loop runs. Nothing is measured here.

Every number is read from files a run already wrote: Roshan's result.json and trace.jsonl,
and the endpoint's server.log when the run folder has one. One JSON per run plus a table.

    python standin_eval/metrics.py                      # every shared/logs/live_* folder
    python standin_eval/metrics.py <run folder> ...     # only these

Game-level metrics (winner, win rate, value killed or lost, income) are not computed here.
They come from Brian's bar-harness. Output is a local test fixture, not a result of any team.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

LOGS = Path(__file__).resolve().parents[2] / "shared" / "logs"


def percentile(values, percent):
    """Nearest rank: the smallest value with at least `percent` % of the values at or below it."""
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)], 3) if ordered else None


def run_metrics(folder):
    result = json.loads((folder / "result.json").read_text())           # Roshan's episode result
    events = [json.loads(line) for line in (folder / "trace.jsonl").open(encoding="utf-8")]
    launch = json.loads((folder / "standin.json").read_text())          # label, written by run_live.sh

    def of_kind(kind):
        return [event for event in events if event["kind"] == kind]

    # A policy_response event exists only for a reply that was on time and passed validation.
    responses = of_kind("policy_response")
    predicts = [event for event in responses if event["response"]["op"] == "predict"]
    # policy_call_seconds: from the supervisor reading the request to the reply being published.
    times_ms = [event["policy_call_seconds"] * 1000 for event in predicts]
    started = of_kind("policy_call_started")

    # The one call that was still open when the episode failed, if any (timeout, error, crash).
    failed = result["failed_policy_call"]
    failed_by_status = {result["episode_status"]: 1} if failed else {}

    # Glue rules are applied inside the endpoint, so their counts come from its log.
    # Rules 1 to 4 are logged as "INFO glue <rule>:", rule 5 as "WARNING policy error on".
    glue = None
    server_log = folder / "server.log"
    if server_log.exists():
        text = server_log.read_text(encoding="utf-8", errors="replace")
        glue = dict(Counter(re.findall(r" INFO glue (\w+):", text)))
        glue["rule5_error_reply"] = len(re.findall(r" WARNING policy error on ", text))

    deltas = result["pending_frame_deltas"]     # frames the sim advanced while each reply was pending
    return {
        "source": "standin", "label": launch["label"], "match_id": result["match_id"],
        "loop_args": launch["loop_args"], "run_folder": folder.name,
        "episode_status": result["episode_status"], "case": result["case"],
        "case_passed": result["case_passed"], "reason": result["reason"],
        "decisions": {"resets_answered": len(responses) - len(predicts),
                      "predicts_answered": len(predicts),
                      "calls_started": len(started), "calls_answered": len(responses)},
        "action_kinds": dict(Counter(event["response"]["action"]["kind"] for event in predicts)),
        "orders_submitted": len(of_kind("order_submitted")),
        "engine_callbacks_tied_to_a_decision": sum(
            event.get("decision_id") is not None for event in of_kind("engine_command_callback")),
        "glue_rules_fired": glue,               # None = this run folder has no server.log
        "predict_round_trip_ms": {"count": len(times_ms), "p50": percentile(times_ms, 50),
                                  "p95": percentile(times_ms, 95), "p99": percentile(times_ms, 99),
                                  "max": percentile(times_ms, 100)},
        "policy_budget_seconds": started[0]["budget_seconds"] if started else None,
        "failed_calls_by_status": failed_by_status, "failed_policy_call": failed,
        "pending_frame_advance": {"responses": len(deltas), "max": max(deltas, default=None),
                                  "responses_with_advance": sum(delta > 0 for delta in deltas)},
        "timing_mode": result["timing_mode"], "timing_errors": result["timing_errors"],
        "sim_frames": result["last_engine_frame"], "wall_seconds": round(result["wall_seconds"], 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="*", type=Path, help="run folders (default: all live_*)")
    args = parser.parse_args()
    folders = args.folders or sorted(LOGS.glob("live_*"))

    print("STAND-IN policy-side metrics, read from existing run files. Not a result of any team.")
    header = ("label", "match", "status", "passed", "predicts", "noop", "order", "p50_ms",
              "p95_ms", "p99_ms", "failed_call", "glue", "pend_max", "frames", "wall_s")
    print(" | ".join(header))
    for folder in folders:
        metrics = run_metrics(folder)
        out = LOGS / f"metrics_{metrics['label']}_{metrics['match_id'][:8]}.json"
        out.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
        times = metrics["predict_round_trip_ms"]
        row = (metrics["label"], metrics["match_id"][:8], metrics["episode_status"],
               metrics["case_passed"], metrics["decisions"]["predicts_answered"],
               metrics["action_kinds"].get("noop", 0), metrics["action_kinds"].get("order", 0),
               times["p50"], times["p95"], times["p99"],
               metrics["failed_calls_by_status"] or "-", metrics["glue_rules_fired"],
               metrics["pending_frame_advance"]["max"], metrics["sim_frames"],
               metrics["wall_seconds"])
        print(" | ".join(str(value) for value in row))


if __name__ == "__main__":
    main()
