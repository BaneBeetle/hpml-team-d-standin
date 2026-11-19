"""STAND-IN unit policy model: state + one acting unit -> that unit's order.

Shapes: B examples in a batch, K units per state (padded), d the vector width.
Every unit becomes a vector; a small transformer lets units look at each other; the acting
unit's vector plus a summary of the state is the "context" every output head reads.

Positions enter only relative to the order's reference point (the acting unit, or the end of
its queue when the order is appended to the queue), never as map coordinates. So the model
cannot memorise a map, and a mirrored state is an equally valid training example.

Heads (each is one classification):
  type      which order (move, build X, fire state = 2, ...), read first. A fixed table
            `prior` is added to it: the log of how often each unit type received each order
            type in the training data, so the network only has to learn the changes from that.
  target    which unit the order points at (attack, guard, repair ...)
  dx, dz    where the order goes, as an offset from the reference point (classes in common.py);
            dz is read after dx so the two can agree
  facing    a building's facing (4)        radius    an area order's radius (7 classes)
  options   the 5 modifier keys (meta, right, shift, ctrl, alt), each yes or no
A head only counts in the loss for orders that have that field.
"""

import torch
from torch import nn
import torch.nn.functional as Fn

import common
from common import A

OPTION_BITS = [bit for _, bit in A.OPTION_BITS]          # 4, 16, 32, 64, 128
OTHER_NUMBERS = 4         # health fraction, build progress, queue length, is own


class UnitPolicy(nn.Module):
    def __init__(self, prior, n_commands, d=128, layers=2, heads=4, dropout=0.1):
        """prior: [unit type numbers, order types] log frequencies (see the top of the file)."""
        super().__init__()
        n_defs, n_types = prior.shape
        self.register_buffer("prior", prior)
        self.def_embed = nn.Embedding(n_defs, 48)
        self.command_embed = nn.Embedding(n_commands, 16)       # used for the queue's first and last order
        # per unit: two embeddings of queue commands, 4 numbers, "is the acting unit",
        # offset from the reference point (2) and the log of that distance (1)
        self.unit_in = nn.Linear(48 + 2 * 16 + OTHER_NUMBERS + 4, d)
        block = nn.TransformerEncoderLayer(d, heads, 4 * d, dropout, batch_first=True, norm_first=True)
        self.blocks = nn.TransformerEncoder(block, layers, enable_nested_tensor=False)
        self.resources_in = nn.Linear(len(common.RESOURCE_FIELDS) * 2 + 1, d)
        self.append_embed = nn.Embedding(2, d)                  # is the order appended to the queue
        self.place_in = nn.Linear(2, d)       # the reference point on the map; zeros when not used
        self.context = nn.Sequential(nn.Linear(4 * d, d), nn.GELU(), nn.Dropout(dropout), nn.Linear(d, d))
        self.type_head = nn.Linear(d, n_types)
        self.type_embed = nn.Embedding(n_types, d)
        self.target_query, self.target_key = nn.Linear(d, d), nn.Linear(d, d)
        self.dx_head, self.dz_head = nn.Linear(d, common.N_BINS), nn.Linear(d, common.N_BINS)
        self.dx_embed = nn.Embedding(common.N_BINS, d)
        self.facing_head, self.radius_head = nn.Linear(d, 4), nn.Linear(d, len(A.RADIUS_CENTERS))
        self.options_head = nn.Linear(d, len(OPTION_BITS))

    def encode(self, batch):
        """batch: def_id, queue_command, tail_command [B,K] (vocabulary numbers), relative [B,K,2]
        (elmos from the reference point), other [B,K,4], mask [B,K], resources [B,11], unit [B]
        (row of the acting unit), append [B] (0/1), place [B,2] (the reference point in map
        coordinates / 4096, or zeros: see train.py --map-position). Returns units [B,K,d],
        context [B,d], type logits [B, n_types]."""
        mask = batch["mask"]
        rows = torch.arange(len(batch["unit"]), device=mask.device)
        offset = batch["relative"] / 1024
        distance = torch.log1p(offset.norm(dim=-1, keepdim=True))
        is_acting = torch.zeros_like(distance)
        is_acting[rows, batch["unit"]] = 1.0
        x = torch.cat([self.def_embed(batch["def_id"]), self.command_embed(batch["queue_command"]),
                       self.command_embed(batch["tail_command"]), batch["other"], is_acting,
                       offset.clamp(-8, 8), distance], -1)
        units = self.blocks(self.unit_in(x), src_key_padding_mask=~mask)
        weight = mask.unsqueeze(-1).float()
        mean = (units * weight).sum(1) / weight.sum(1).clamp(min=1)
        highest = units.masked_fill(~mask.unsqueeze(-1), -1e9).amax(1)
        resources = self.resources_in(torch.log1p(batch["resources"].clamp(min=0)))
        context = self.context(torch.cat([mean, highest, resources, units[rows, batch["unit"]]], -1))
        context = context + self.append_embed(batch["append"]) + self.place_in(batch["place"])
        type_logits = self.type_head(context) + self.prior[batch["def_id"][rows, batch["unit"]]]
        return units, context, type_logits

    def target_logits(self, units, context, mask):
        scores = (self.target_key(units) @ self.target_query(context).unsqueeze(-1)).squeeze(-1)
        return (scores / units.shape[-1] ** 0.5).masked_fill(~mask, -1e9)

    def losses(self, batch):
        """Per example loss of every head [B] (0 where the order has no such field), and whether
        the most likely type is the recorded one [B]."""
        units, context, type_logits = self.encode(batch)
        parts = {"type": Fn.cross_entropy(type_logits, batch["type"], reduction="none")}
        after_type = context + self.type_embed(batch["type"])
        heads = {"target": self.target_logits(units, after_type, batch["mask"]),
                 "dx": self.dx_head(after_type),
                 "dz": self.dz_head(after_type + self.dx_embed(batch["dx"].clamp(min=0))),
                 "facing": self.facing_head(after_type), "radius": self.radius_head(after_type)}
        for name, logits in heads.items():
            has = batch[name] >= 0                      # -1 = this order has no such field
            parts[name] = Fn.cross_entropy(logits, batch[name].clamp(min=0), reduction="none") * has
        bits = torch.stack([(batch["options"] & bit) > 0 for bit in OPTION_BITS], 1).float()
        parts["options"] = Fn.binary_cross_entropy_with_logits(
            self.options_head(after_type), bits, reduction="none").sum(1)
        return parts, type_logits.argmax(-1) == batch["type"]

    @torch.no_grad()
    def act(self, batch, allowed, temperature=1.0, targets=None):
        """One order for one acting unit (B = 1). `allowed` [n_types] bool: the types to choose from.
        `targets`: a function, order type number -> [1,K] bool, the units that type may point at.
        temperature 0 = always the most likely choice, 1 = drawn from the predicted distribution."""
        def choose(logits):
            if temperature <= 0:
                return logits.argmax(-1)
            return torch.distributions.Categorical(logits=logits / temperature).sample()

        units, context, type_logits = self.encode(batch)
        order_type = choose(type_logits.masked_fill(~allowed, -1e9))
        after_type = context + self.type_embed(order_type)
        dx = choose(self.dx_head(after_type))
        option_logits = self.options_head(after_type)[0]
        if temperature <= 0:
            options = option_logits > 0
        else:
            options = torch.bernoulli(torch.sigmoid(option_logits / temperature)).bool()
        others = targets(int(order_type)) if targets else batch["mask"]
        return {"type": int(order_type), "dx": int(dx),
                "dz": int(choose(self.dz_head(after_type + self.dx_embed(dx)))),
                "target": int(choose(self.target_logits(units, after_type, others))),
                "facing": int(choose(self.facing_head(after_type))),
                "radius": int(choose(self.radius_head(after_type))),
                "options": sum(bit for bit, on in zip(OPTION_BITS, options.tolist()) if on)}
