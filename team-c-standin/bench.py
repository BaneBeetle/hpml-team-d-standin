#!/usr/bin/env python3
"""STAND-IN round-trip timing of the stand-in endpoint. Local CPU. Not a Team C result.

Starts its own server on a free port, sends 500 predict requests through
shared/endpoint_adapter.py one at a time, prints the numbers and stops the server.

Run from the repository root:  python standin_infer/bench.py --policy scripted
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT.parent / "shared"
sys.path.insert(0, str(SHARED))
import endpoint_adapter

DATA = SHARED / "data" / "state_command_pairs.jsonl"
TRACES = sorted((ROOT / "evidence" / "policy_timeouts").glob("*/trace.jsonl"))
EXAMPLE = ROOT / "examples" / "control_loop" / "predict_request.json"
LOG_DIR = ROOT / "output" / "standin_infer"     # git-ignored
BUDGET_MS = 3000                                # policy_timeout_seconds in configs/control_loop.json


def build_requests(count):
    """`count` predict requests: every recorded fixture request, then real DATA-01 states."""
    example = json.loads(EXAMPLE.read_text())
    pieces = []     # (observation, catalog) pairs
    # 1. The predict requests Roshan's control loop actually sent (they carry their own catalog).
    for trace in TRACES:
        for line in trace.open(encoding="utf-8"):
            event = json.loads(line)
            if event.get("kind") == "policy_request" and event["request"]["op"] == "predict":
                pieces.append((event["request"]["observation"], event["request"]["catalog"]))
    pieces = pieces[:count]
    from_traces = len(pieces)
    # 2. Fill up with real match states, evenly spaced so early, middle and late game all appear.
    #    They have no catalog of their own, so they reuse the one from Roshan's example request.
    with DATA.open(encoding="utf-8") as stream:
        lines = stream.readlines()
    missing = count - len(pieces)
    for index in range(missing):
        row = json.loads(lines[index * len(lines) // missing])
        pieces.append((row["state"], example["catalog"]))
    # Wrap every piece in one envelope shape, as one match with increasing decision ids.
    requests = [dict(example, match_id="standin-bench", decision_id=number,
                     source_frame=45 + 15 * number, scheduled_frame=45 + 15 * number,
                     team_id=observation["teamID"], observation=observation, catalog=catalog)
                for number, (observation, catalog) in enumerate(pieces, start=1)]
    return requests, from_traces


def percentile(sorted_values, percent):
    """Nearest-rank percentile: the smallest value with at least `percent` % of values at or below it."""
    return sorted_values[max(0, math.ceil(percent / 100 * len(sorted_values)) - 1)]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))    # port 0 = let the OS choose
        return probe.getsockname()[1]


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # no system proxy
    with opener.open(url, timeout=2) as reply:
        return json.loads(reply.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=("scripted", "model", "noop"), required=True)
    parser.add_argument("--count", type=int, default=500)
    args = parser.parse_args()

    requests, from_traces = build_requests(args.count)
    url = f"http://127.0.0.1:{free_port()}"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"server-{args.policy}.log"
    with log_path.open("w") as log_file:
        server = subprocess.Popen(
            [sys.executable, str(ROOT / "standin_infer" / "server.py"),
             "--policy", args.policy, "--port", url.rsplit(":", 1)[1]],
            stderr=log_file)
        try:
            # Wait until the server answers /health (the model policy has to load torch first).
            deadline = time.monotonic() + 120
            while True:
                try:
                    get_json(url + "/health")
                    break
                except OSError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Server did not start, see {log_path}")
                    time.sleep(0.1)

            policy = endpoint_adapter.EndpointPolicy(url)
            round_trips_ms, outcomes, errors = [], Counter(), Counter()
            team = None
            started = time.perf_counter()
            for request in requests:
                if request["team_id"] != team:
                    # The scripted policy refuses a predict whose identity was not reset first.
                    # The data has two teams, so reset when the team changes. Resets are not timed.
                    team = request["team_id"]
                    policy.reset(dict(request, op="reset", decision_id=0))
                before = time.perf_counter()
                reply = policy.predict(request)
                round_trips_ms.append((time.perf_counter() - before) * 1000)
                if reply["status"] == "ok":
                    outcomes[reply["action"]["kind"]] += 1
                else:
                    outcomes["error"] += 1
                    errors[reply["error"]] += 1
            total_seconds = time.perf_counter() - started
            fired = get_json(url + "/stats")["glue_rules_fired"]
        finally:
            server.terminate()      # never leave the server running
            server.wait(timeout=10)

    round_trips_ms.sort()
    print(f"STAND-IN bench, local CPU, policy={args.policy}. Not a Team C result.")
    print(f"requests: {len(requests)} predict, one at a time, one client "
          f"({from_traces} from control-loop traces, {len(requests) - from_traces} from DATA-01 states)")
    for percent in (50, 95, 99):
        print(f"round trip p{percent}: {percentile(round_trips_ms, percent):.2f} ms")
    print(f"round trip max: {round_trips_ms[-1]:.2f} ms")
    print(f"requests per second: {len(requests) / total_seconds:.1f}")
    print(f"over the {BUDGET_MS} ms policy budget: "
          f"{sum(value > BUDGET_MS for value in round_trips_ms)} of {len(requests)}")
    print(f"replies by kind: {dict(outcomes)}")
    for message, times in errors.items():
        print(f"  error x{times}: {message}")
    print(f"glue rules fired: {fired}")
    print(f"server log: {log_path}")


if __name__ == "__main__":
    main()
