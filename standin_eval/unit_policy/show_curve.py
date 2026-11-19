#!/usr/bin/env python3
"""STAND-IN: print a training log (or a finished train.json) as one short line per measurement.

    python standin_eval/unit_policy/show_curve.py unit-v2a
"""

import json
import sys

import common

name = sys.argv[1]
folder = common.SHARED / "ckpt"
if (folder / name / "train.json").exists():
    rows = json.loads((folder / name / "train.json").read_text())["curve"]
else:       # still training: read the log (PowerShell writes it as UTF-16)
    raw = (folder / f"{name}.log").read_bytes()
    text = raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8", "ignore")
    rows = [json.loads(line) for line in text.splitlines() if line.startswith('{"step"')]
print("step   play   type  acc  | builds: type  acc    dx    dz | all: dx    dz  target  seconds")
for row in rows:
    v = row["validation"]
    v.setdefault("play", v["type"] + v["target"] + v["dx"] + v["dz"])      # logs from before "play"
    print(f"{row['step']:5d} {v['play']:6.2f} {v['type']:6.3f} {v['type_accuracy']:.3f} |"
          f" {v['build_type']:12.3f} {v['build_type_accuracy']:.3f} {v['build_dx']:5.2f} {v['build_dz']:5.2f} |"
          f" {v['dx']:7.2f} {v['dz']:5.2f} {v['target']:6.3f}  {row.get('seconds', 0)}")
