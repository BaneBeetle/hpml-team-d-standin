#!/usr/bin/env python3
"""STAND-IN: train the unit policy on the arrays made by build_dataset.py.

    python standin_eval/unit_policy/train.py --data unit-v2 --name unit-v2a --steps 6000

Train matches are fitted, validation matches pick the checkpoint (lowest validation loss,
measured every --eval-every steps). Writes shared/ckpt/<name>/: unit_policy.pt (weights and
everything the server needs), train.json (settings and the loss curve), unit_defs.json (the
data game's unit type table, which the full-game bridge needs). A local test fixture.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from model import UnitPolicy

EXAMPLE_FIELDS = ("state", "unit", "command_id", "append", "target", "dx", "dz", "facing", "radius", "options")
UNIT_FIELDS = ("def_id", "queue_command", "tail_command", "numbers")
HEADS = ("type", "target", "dx", "dz", "facing", "radius", "options")


def load(data_dir, matches):
    """Join the matches' files into one set of arrays; states and units are renumbered to fit."""
    parts = {name: [] for name in EXAMPLE_FIELDS + UNIT_FIELDS + ("type_key", "resources", "offsets")}
    states = units = 0
    for match in matches:
        with np.load(data_dir / f"{match['replay_id']}.npz") as file:
            for name in parts:
                values = file[name]
                if name == "state":
                    values = values + states
                if name == "offsets":
                    values = values[:-1] + units          # where each state's units start
                parts[name].append(values)
            states += len(file["resources"])
            units += len(file["def_id"])
    data = {name: np.concatenate(values) for name, values in parts.items()}
    data["offsets"] = np.append(data["offsets"], units)
    return data


def numbered(values, keys):
    """Raw ids -> vocabulary numbers. `keys` is the sorted list of ids seen in training;
    number 0 means "not seen in training"."""
    keys = np.array(keys)
    position = np.searchsorted(keys, values).clip(max=len(keys) - 1)
    return np.where(keys[position] == values, position + 1, 0).astype(np.int32)


def to_tensors(data, vocab, device):
    """Arrays -> tensors on the device, with vocabulary numbers. Examples whose order type is
    not in the type vocabulary are dropped."""
    type_number = {key: number for number, key in enumerate(vocab["types"])}
    keep = np.array([key in type_number for key in data["type_key"].tolist()])
    out = {name: torch.tensor(data[name][keep], device=device, dtype=torch.long)
           for name in EXAMPLE_FIELDS if name != "command_id"}
    out["type"] = torch.tensor([type_number[key] for key in data["type_key"][keep].tolist()], device=device)
    out["def_id"] = torch.tensor(numbered(data["def_id"], vocab["defs"]), device=device)
    for name in ("queue_command", "tail_command"):
        out[name] = torch.tensor(numbered(data[name], vocab["commands"]), device=device)
    out["numbers"] = torch.tensor(data["numbers"], device=device)
    out["resources"] = torch.tensor(data["resources"], device=device)
    out["offsets"] = torch.tensor(data["offsets"], device=device)
    return out


def batch_of(tensors, index, flip=False):
    """The examples `index` as one padded batch (see UnitPolicy.encode for the fields).

    flip: mirror each example east-west and/or north-south at random. Positions are relative,
    so a mirrored state is as valid as the recorded one; the offset classes and a building's
    facing are mirrored with it.
    """
    state = tensors["state"][index]
    start = tensors["offsets"][state]
    length = tensors["offsets"][state + 1] - start
    position = torch.arange(int(length.max()), device=index.device)
    rows = (start[:, None] + position).clamp(max=len(tensors["def_id"]) - 1)
    batch = {name: tensors[name][rows] for name in ("def_id", "queue_command", "tail_command")}
    batch["mask"] = position < length[:, None]
    batch["resources"] = tensors["resources"][state]
    for name in ("unit", "append", "type", "target", "dx", "dz", "facing", "radius", "options"):
        batch[name] = tensors[name][index]
    numbers = tensors["numbers"][rows]                              # [B,K,9], see common.UNIT_NUMBERS
    acting = numbers[torch.arange(len(index), device=index.device), batch["unit"]]
    reference = torch.where(batch["append"][:, None] == 1, acting[:, 6:8], acting[:, 0:2])
    batch["relative"] = numbers[:, :, 0:2] - reference[:, None]
    batch["place"] = reference / 4096 if tensors["map_position"] else torch.zeros_like(reference)
    batch["other"] = numbers[:, :, 2:6]
    if flip:
        mirror = torch.rand(len(index), 2, device=index.device) < 0.5           # [B, (x, z)]
        batch["relative"] = batch["relative"] * torch.where(mirror, -1.0, 1.0)[:, None]
        last = common.N_BINS - 1
        batch["dx"] = torch.where(mirror[:, 0] & (batch["dx"] >= 0), last - batch["dx"], batch["dx"])
        batch["dz"] = torch.where(mirror[:, 1] & (batch["dz"] >= 0), last - batch["dz"], batch["dz"])
        facing = batch["facing"]                 # 0 south, 1 east, 2 north, 3 west
        facing = torch.where(mirror[:, 0] & ((facing == 1) | (facing == 3)), 4 - facing, facing)
        facing = torch.where(mirror[:, 1] & ((facing == 0) | (facing == 2)), 2 - facing, facing)
        batch["facing"] = facing
    return batch


def mean_loss(parts, batch):
    """Each head's mean over the examples that have that field, and their sum."""
    means = {}
    for name in HEADS:
        count = len(batch["type"]) if name in ("type", "options") else (batch[name] >= 0).sum().clamp(min=1)
        means[name] = parts[name].sum() / count
    return sum(means.values()), means


@torch.no_grad()
def evaluate(model, tensors, is_build, examples=None, batch_size=256):
    """Mean loss of every head over a split (or over the examples `examples` of it), how often
    the top type is the recorded one, and the same for build orders alone (is_build: yes/no
    per order type). "play" = type + target + dx + dz, the heads a game depends on most."""
    model.eval()
    sums, counts = Counter(), Counter()
    if examples is None:
        examples = torch.arange(len(tensors["type"]), device=tensors["type"].device)
    for begin in range(0, len(examples), batch_size):
        batch = batch_of(tensors, examples[begin:begin + batch_size])
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=examples.is_cuda):
            parts, correct = model.losses(batch)
        parts = {name: values.float() for name, values in parts.items()}
        build = is_build[batch["type"]]
        for name in HEADS:
            has = torch.ones_like(build) if name in ("type", "options") else batch[name] >= 0
            sums[name] += float(parts[name].sum())
            counts[name] += int(has.sum())
            sums["build_" + name] += float((parts[name] * build).sum())
            counts["build_" + name] += int((has & build).sum())
        sums["type_accuracy"] += int(correct.sum())
        sums["build_type_accuracy"] += int((correct & build).sum())
    model.train()
    counts["type_accuracy"], counts["build_type_accuracy"] = counts["type"], counts["build_type"]
    result = {name: round(sums[name] / max(counts[name], 1), 4) for name in sums}
    result["total"] = round(sum(result[name] for name in HEADS), 4)
    result["play"] = round(sum(result[name] for name in ("type", "target", "dx", "dz")), 4)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--steps", type=int, default=6000)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.05)
    parser.add_argument("--d", type=int, default=128)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--no-flip", action="store_true", help="turn the mirror augmentation off")
    parser.add_argument("--map-position", action="store_true",
                        help="give the model the reference point's map coordinates (for data from ONE "
                             "map, played on that map; turns the mirror augmentation off)")
    parser.add_argument("--eval-every", type=int, default=250)
    parser.add_argument("--select", default="play", help="validation number that picks the checkpoint")
    parser.add_argument("--eval-examples", type=int, default=16000,
                        help="validation examples measured during training (a fixed random sample)")
    parser.add_argument("--gpu-gb", type=float, default=10, help="most GPU memory this run may hold")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    if args.device == "cuda":      # other programs use this GPU too: fail rather than fill it
        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(args.gpu_gb * 2**30 / total)
    data_dir, out_dir = common.SHARED / "data" / args.data, common.SHARED / "ckpt" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data_dir / "manifest.json").read_text())
    split = {name: [m for m in manifest["matches"] if m["split"] == name]
             for name in ("train", "validation", "test")}
    train = load(data_dir, split["train"])

    # Vocabularies from the train matches only. An order type needs 2 examples to get in.
    type_counts = Counter(train["type_key"].tolist())
    vocab = {"defs": sorted(set(train["def_id"].tolist())),
             "commands": sorted(set(train["queue_command"].tolist()) | set(train["tail_command"].tolist())),
             "types": sorted(key for key, count in type_counts.items() if count >= 2)}
    # For decoding: each type's command id; which unit types were seen receiving which order types.
    acting_def = train["def_id"][train["offsets"][train["state"]] + train["unit"]]
    command_of, pair_counts = {}, Counter()
    for key, command_id, def_id in zip(train["type_key"].tolist(), train["command_id"].tolist(),
                                       acting_def.tolist()):
        command_of[key] = command_id
        pair_counts[(def_id, key)] += 1
    allowed = {}
    for (def_id, key), count in pair_counts.items():
        if count >= 2 and type_counts[key] >= 2:
            allowed.setdefault(def_id, []).append(key)
    # For orders that point at a unit: did the training targets include own units, other units?
    # (An attack never pointed at an own unit, a guard never at an enemy.) A side needs 2% of
    # the type's examples to count. The server only offers targets on a side that counts.
    has_target = train["target"] >= 0
    target_row = train["offsets"][train["state"]] + train["target"]
    target_is_own = train["numbers"][np.where(has_target, target_row, 0), 5] > 0
    side_counts = {}
    for key, own in zip(train["type_key"][has_target].tolist(), target_is_own[has_target].tolist()):
        side_counts.setdefault(key, [0, 0])[0 if own else 1] += 1
    target_sides = {key: [own >= 0.02 * (own + other), other >= 0.02 * (own + other)]
                    for key, (own, other) in side_counts.items()}
    # The prior: log of how often unit type (row) received order type (column), lightly smoothed.
    def_number = {value: number + 1 for number, value in enumerate(vocab["defs"])}
    type_number = {key: number for number, key in enumerate(vocab["types"])}
    table = torch.full((len(vocab["defs"]) + 1, len(vocab["types"])), 0.1)
    for (def_id, key), count in pair_counts.items():
        if key in type_number:
            table[def_number[def_id], type_number[key]] += count
    prior = torch.log(table / table.sum(1, keepdim=True))

    tensors = {"train": to_tensors(train, vocab, args.device),
               "validation": to_tensors(load(data_dir, split["validation"]), vocab, args.device)}
    for part in tensors.values():
        part["map_position"] = args.map_position
    is_build = torch.tensor([key.endswith(("@build", "@factory")) for key in vocab["types"]], device=args.device)
    model = UnitPolicy(prior, len(vocab["commands"]) + 1, args.d, args.layers, dropout=args.dropout).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimizer, args.lr, total_steps=args.steps, pct_start=0.05)
    examples = len(tensors["train"]["type"])
    print(f"train examples {examples}  validation examples {len(tensors['validation']['type'])}  "
          f"types {len(vocab['types'])}  unit types {len(vocab['defs'])}  "
          f"parameters {sum(p.numel() for p in model.parameters())}", flush=True)
    count = len(tensors["validation"]["type"])
    sample = torch.randperm(count, device=args.device)[:args.eval_examples]
    start_row = {"step": 0, "validation": evaluate(model, tensors["validation"], is_build, sample)}
    print(json.dumps(start_row), flush=True)           # step 0: the prior alone, before any training

    curve, best, started = [start_row], None, time.time()
    for step in range(1, args.steps + 1):
        index = torch.randint(examples, (args.batch,), device=args.device)
        batch = batch_of(tensors["train"], index, flip=not (args.no_flip or args.map_position))
        # bfloat16 inside the model: about half the GPU memory and time of float32
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=args.device == "cuda"):
            parts = model.losses(batch)[0]
        loss, _ = mean_loss({name: values.float() for name, values in parts.items()}, batch)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        schedule.step()
        if step % args.eval_every == 0 or step == args.steps:
            row = {"step": step, "train_batch_loss": round(float(loss.detach()), 4),
                   "validation": evaluate(model, tensors["validation"], is_build, sample),
                   "seconds": round(time.time() - started)}
            curve.append(row)
            print(json.dumps(row), flush=True)
            if best is None or row["validation"][args.select] < best["validation"][args.select]:
                best = row
                torch.save({"source": "standin", "weights": model.state_dict(), "vocab": vocab,
                            "command_of": command_of, "allowed": allowed, "target_sides": target_sides,
                            "model": {"d": args.d, "layers": args.layers, "map_position": args.map_position},
                            "step": step}, out_dir / "unit_policy.pt")
    # The selected step once more, on every validation example (the curve used a sample).
    model.load_state_dict(torch.load(out_dir / "unit_policy.pt", weights_only=False)["weights"])
    best = dict(best, validation_all=evaluate(model, tensors["validation"], is_build))
    settings = dict(vars(args), data_game=manifest["game"], train_examples=examples,
                    validation_examples=len(tensors["validation"]["type"]), types=len(vocab["types"]))
    (out_dir / "train.json").write_text(json.dumps(
        {"source": "standin", "note": "Local test checkpoint. Not Team B's work and not a result of any team.",
         "settings": settings, "selected": best, "curve": curve}, indent=1), encoding="utf-8")
    # The unit type table of the data's game version: the dataset's own, or Team A's release's.
    table = data_dir / "unit_defs.json"
    shutil.copy2(table if table.exists() else common.SHARED / "data" / "data05_unit_defs.json",
                 out_dir / "unit_defs.json")
    print("selected " + json.dumps(best), flush=True)


if __name__ == "__main__":
    main()
