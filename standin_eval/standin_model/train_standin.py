#!/usr/bin/env python3
"""STAND-IN: train Team B's B03 model on the stand-in pairs, with Team B's own script.

    python standin_eval/standin_model/train_standin.py --data standin-barb --name standin-barb-v1 \
        --steps 3000 --eval-every 100 --seeds 0 --device cuda

Everything after --data and --name is passed to scripts/b03_report.py `train` unchanged
(same model, loss, optimizer and checkpoint format). That script has two things fixed in its
code that this data needs different, so they are replaced here at run time. The file itself
is not edited:
  - DATA: it names the DATA-01 match and "Great Divide V1"; the map name is a model input.
  - split_of: it splits one match by game minute; here every game is one split as a whole,
    read from the "split" label make_pairs.py wrote into each row.
For data from several maps (make_pairs_data05.py, Team A's matches) two more things:
  - the map vocabulary is every train map, and each order is encoded with its own match's
    map (the "map" label in the row) instead of the one name in DATA;
  - --unit-defs FILE is copied next to the checkpoint as unit_defs.json: the unit type table
    of the game version the data came from, which the full-game bridge needs.
The checkpoint is a local stand-in fixture, not Team B's work.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

TEAM_D = Path(__file__).resolve().parents[2]
SHARED = TEAM_D.parent / "shared"
sys.path.insert(0, str(TEAM_D / "scripts"))
sys.path.insert(0, str(TEAM_D))
# torch.use_deterministic_algorithms (set by b03_report) needs this on CUDA; harmless on CPU.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import b03_report                       # Team B's script, imported as a module
from bar_policy import training as T    # Team B's training helpers


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="folder under shared/data made by make_pairs.py")
    parser.add_argument("--name", required=True, help="checkpoint folder to create under shared/ckpt")
    parser.add_argument("--unit-defs", type=Path, help="unit type table of the data's game version")
    args, train_args = parser.parse_known_args()     # train_args go to Team B's script as they are

    data_dir = SHARED / "data" / args.data
    manifest = json.loads((data_dir / "manifest.json").read_text())
    pairs = data_dir / manifest["file"]
    out_dir = SHARED / "ckpt" / args.name

    # The two replacements described at the top.
    b03_report.DATA = {"dataset": args.data, "source": "standin", "map": manifest["map"],
                       "game": manifest["game"], "file": manifest["file"]}
    b03_report.split_of = lambda order: order["action"]["split"]
    b03_report.data_version = lambda _: dict(b03_report.DATA, sha256=T.file_sha256(pairs),
                                             split="by whole game (see the data manifest)")
    if "maps" in manifest:                           # several maps: the two map replacements
        features = b03_report.F.FeatureSpec          # Team B's class
        fit, encode = features.fit.__func__, features.encode
        features.fit = classmethod(
            lambda cls, rows, unit_cap=128, map_names=(): fit(cls, rows, unit_cap, manifest["maps"]))
        features.encode = lambda self, row, **options: encode(
            self, row, **dict(options, map_name=row["action"]["map"]))

    argv = ["train", str(pairs), "--out", str(out_dir / "train.json"),
            "--ckpt", str(out_dir / "h1_best.pt")] + train_args
    print("b03_report.py " + " ".join(argv), flush=True)
    b03_report.main(argv)
    if args.unit_defs:
        shutil.copy2(args.unit_defs, out_dir / "unit_defs.json")


if __name__ == "__main__":
    main()
