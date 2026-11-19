#!/usr/bin/env python3
"""STAND-IN policy endpoint for the unit policy. Not Team C's endpoint.

    python standin_eval/unit_policy/unit_server.py --policy model --checkpoint <unit_policy.pt>

Same HTTP interface as team-c/standin_infer/server.py (whose server code is imported and
reused), so run_fullgame.ps1 and the bridge work unchanged. What is different is the policy:

  1. Who acts: one own, finished unit per decision, not ordered by us in the last COOLDOWN
     frames, that either has an empty order queue, or has fewer than QUEUE_DEPTH orders
     queued and a position at the end of its queue (then the new order is appended, with the
     shift option, and placed relative to that position). A unit with a guard or patrol in
     its queue gets a new order (replacing the queue) ENDLESS_FRAMES after our last one,
     because those two never finish. A factory's queue is not in the observation, so a factory counts as busy while one of our unfinished units stands on
     it. The unit that has waited longest goes first. No such unit -> noop.
  2. What it does: the model picks the order type among the types that unit type was seen
     receiving in the training data, then the order's other fields.

Environment: STANDIN_SAMPLE_SEED (random seed), STANDIN_TEMPERATURE (default 1; 0 = greedy),
STANDIN_QUEUE_DEPTH (default 3; 1 = only idle units get orders), STANDIN_ARMY_CHECKPOINT (a
second unit_policy.pt: it orders the units that do not build, --checkpoint orders the rest).
"""

from collections import Counter
import json
import os
from pathlib import Path
import sys
import time
import traceback

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
from common import A
from model import UnitPolicy

sys.path.insert(0, str(common.SHARED.parent / "team-c" / "standin_infer"))
import server                                   # Team C stand-in: HTTP handler and protocol checks
from control_loop.protocol import response      # Roshan's reply envelope

# Frames before a unit we just ordered can be picked again. An order shows up in the unit's
# observed queue about 45 frames after the decision that gave it (game_20261118_174832: ordered
# at frame 105, queue still empty at 120 and 135, there at 150). With 45 the unit was picked again
# while its queue still looked empty, and the new order replaced the one before.
COOLDOWN = 90
FACTORY_COOLDOWN = 150
FACTORY_REACH = 96        # an unfinished own unit this close to a factory = the factory is building
ENDLESS = (15, 25)        # PATROL and GUARD: orders that never finish by themselves
ENDLESS_FRAMES = 900      # a unit doing one of them can get a new order after this long (30 s)


class Loaded:
    """One checkpoint, ready to choose an order for a unit."""

    def __init__(self, path):
        saved = torch.load(path, map_location="cpu", weights_only=False)
        vocab = saved["vocab"]
        self.model = UnitPolicy(saved["weights"]["prior"], len(vocab["commands"]) + 1,
                                saved["model"]["d"], saved["model"]["layers"])
        # strict=False: checkpoints saved before the map-position input have no place_in weights
        self.model.load_state_dict(saved["weights"], strict=False)
        self.map_position = saved["model"].get("map_position", False)
        if "place_in.weight" not in saved["weights"]:      # such a checkpoint must get exactly 0 from it
            torch.nn.init.zeros_(self.model.place_in.weight)
            torch.nn.init.zeros_(self.model.place_in.bias)
        self.model.eval()
        self.def_number = {value: number + 1 for number, value in enumerate(vocab["defs"])}
        self.command_number = {value: number + 1 for number, value in enumerate(vocab["commands"])}
        self.types, self.command_of = vocab["types"], saved["command_of"]
        type_number = {key: number for number, key in enumerate(self.types)}
        self.target_sides = saved.get("target_sides", {})    # order type -> may point at [own, other] units
        # unit type -> yes/no per order type; the unit types that are factories; those that build at all
        self.allowed, self.factories, self.builders = {}, set(), set()
        for def_id, keys in saved["allowed"].items():
            if any("@" in key for key in keys):       # it can do more than switch a setting
                mask = torch.zeros(len(self.types), dtype=torch.bool)
                mask[[type_number[key] for key in keys]] = True
                self.allowed[def_id] = mask
            if any(key.endswith("@factory") for key in keys):
                self.factories.add(def_id)
            if any(key.endswith(("@factory", "@build")) for key in keys):
                self.builders.add(def_id)
        # unit type number as it arrives in a request -> the number this checkpoint was trained
        # with. None = the same numbers (see UnitPolicyServer.__init__ for when it is not).
        self.to_own = None

    def own(self, def_id):
        """A unit type number of the request in this checkpoint's numbering (0 = it has none)."""
        return def_id if self.to_own is None else self.to_own.get(def_id, 0)


def unit_names(checkpoint):
    """The unit type table (number -> name) in a checkpoint's folder."""
    return json.loads((Path(checkpoint).parent / "unit_defs.json").read_text())["unit_defs"]


class UnitPolicyServer:
    def __init__(self, checkpoint, fired):
        self.main = Loaded(checkpoint)
        # Optional second checkpoint for the units that do not build (STANDIN_ARMY_CHECKPOINT): the
        # main one then orders builders and factories, the army one every other unit it knows.
        # Requests arrive in the MAIN checkpoint's unit numbering (the bridge translates them
        # using that checkpoint's unit_defs.json); the army checkpoint may have been trained on
        # another game version's numbers, so its unit types are matched by name.
        self.army = None
        if os.environ.get("STANDIN_ARMY_CHECKPOINT"):
            self.army = Loaded(os.environ["STANDIN_ARMY_CHECKPOINT"])
            number_of = {name: int(number)
                         for number, name in unit_names(os.environ["STANDIN_ARMY_CHECKPOINT"]).items()}
            self.army.to_own = {int(number): number_of[name] for number, name in unit_names(checkpoint).items()
                                if name in number_of}
        self.temperature = float(os.environ.get("STANDIN_TEMPERATURE", "1"))
        self.queue_depth = int(os.environ.get("STANDIN_QUEUE_DEPTH", "3"))
        torch.manual_seed(int(os.environ.get("STANDIN_SAMPLE_SEED", "0")))
        self.fired, self.last_order = fired, {}       # unit id -> frame of our last order to it
        self.answered = (None, None)                  # (decision id, reply) of the last predict call
        # One line per predict call: when it started, which decision, how long it took. Written
        # at once (buffering=1), so after a policy timeout it shows whether the request arrived.
        self.log = open(os.environ.get("STANDIN_SERVER_LOG", HERE / "server_requests.log"), "w", buffering=1)

    def expert_for(self, def_id):
        """The checkpoint that orders this unit type, or None when neither has orders for it."""
        if self.army and def_id not in self.main.builders and self.army.own(def_id) in self.army.allowed:
            return self.army
        return self.main if def_id in self.main.allowed else None

    def reset(self, request):
        self.last_order.clear()
        self.answered = (None, None)
        return response(request)

    def candidates(self, units, team, frame):
        """(unit, append) for every unit that can get an order now. append: add it to the queue."""
        building = [u["position"] for u in units if u["teamID"] == team and u["buildProgress"] < 1]
        found = []
        for unit in units:
            def_id = int(unit.get("defID") or 0)
            if unit["teamID"] != team or unit["buildProgress"] < 1 or self.expert_for(def_id) is None:
                continue
            factory = def_id in self.main.factories
            if frame - self.last_order.get(unit["id"], -10000) < (FACTORY_COOLDOWN if factory else COOLDOWN):
                continue
            queue = unit.get("queue") or []           # an empty queue arrives as {}
            x, _, z = unit["position"]
            if factory and any(abs(p[0] - x) < FACTORY_REACH and abs(p[2] - z) < FACTORY_REACH for p in building):
                continue
            # A guard or a patrol never ends by itself, and orders queued behind one never start.
            endless = any(q.get("id") in ENDLESS for q in queue)
            if not queue or (endless and frame - self.last_order.get(unit["id"], -10000) >= ENDLESS_FRAMES):
                found.append((unit, False))           # the new order replaces whatever is queued
            elif not endless and len(queue) < self.queue_depth and any(len(q.get("params") or []) >= 3 for q in queue):
                found.append((unit, True))
        return found

    def predict(self, request):
        started = time.time()
        # a line when the request arrives too: a call that never returns still leaves this one
        self.log.write(f"{started:.3f} decision {request.get('decision_id')} arrived" + chr(10))
        try:
            # The adapter may send a request again when it got no answer in time. The same
            # decision gets the same reply, so a unit is not ordered twice.
            if request.get("decision_id") != self.answered[0]:
                self.answered = (request.get("decision_id"), self.decide(request))
            return self.answered[1]
        except Exception:
            self.log.write(traceback.format_exc())
            raise
        finally:
            took = time.time() - started
            self.log.write(f"{started:.3f} decision {request.get('decision_id')} "
                           f"frame {request.get('source_frame')} took {took:.3f} s\n")

    def decide(self, request):
        observation, team, frame = request["observation"], request["team_id"], request["source_frame"]
        found = self.candidates(observation["units"] or [], team, frame)
        if not found:
            self.fired["no_unit_to_order_noop"] += 1
            return response(request)
        unit, append = min(found, key=lambda pair: (self.last_order.get(pair[0]["id"], -1), pair[0]["id"]))
        expert = self.expert_for(int(unit["defID"]))
        arrays = common.featurize(observation, team, frame, keep_first=[unit["id"]])   # the unit is row 0
        numbers = torch.tensor(arrays["numbers"])
        x, z = (numbers[0, 6:8] if append else numbers[0, 0:2]).tolist()        # the reference point

        def numbered(values, table):
            return torch.tensor([[table.get(int(value), 0) for value in values]])

        batch = {"def_id": numbered([expert.own(int(value)) for value in arrays["def_id"]], expert.def_number),
                 "queue_command": numbered(arrays["queue_command"], expert.command_number),
                 "tail_command": numbered(arrays["tail_command"], expert.command_number),
                 "relative": (numbers[:, 0:2] - torch.tensor([x, z])).unsqueeze(0),
                 "other": numbers[:, 2:6].unsqueeze(0),
                 "mask": torch.ones(1, len(numbers), dtype=torch.bool),
                 "resources": torch.tensor(arrays["resources"]).unsqueeze(0),
                 "unit": torch.tensor([0]), "append": torch.tensor([int(append)]),
                 "place": torch.tensor([[x, z]]) / 4096 if expert.map_position else torch.zeros(1, 2)}
        is_own = numbers[:, 5] > 0

        def targets(type_number):
            """The units this order type may point at: never the unit itself, and only a side
            (own / not own) that the type pointed at in the training data."""
            own_ok, other_ok = expert.target_sides.get(expert.types[type_number], (True, True))
            ok = (is_own & own_ok) | (~is_own & other_ok)
            ok[0] = False
            return ok.unsqueeze(0)

        # A targeted order type is only offered when the state has a unit it may point at.
        has_target = torch.tensor([not key.endswith("@unit") or bool(targets(number).any())
                                   for number, key in enumerate(expert.types)])
        allowed = expert.allowed[expert.own(int(unit["defID"]))] & has_target
        choice = expert.model.act(batch, allowed, self.temperature, targets)
        key = expert.types[choice["type"]]
        form = key.split("@")[1] if "@" in key else ("value" if "=" in key else "none")
        params = []
        if form == "value":
            params = [float(key.split("=")[1])]
        elif form == "unit":
            params = [float(arrays["unit_id"][choice["target"]])]
        elif form in ("pos", "area", "build"):
            params = [max(x + common.class_offset(choice["dx"]), 0.0), unit["position"][1],
                      max(z + common.class_offset(choice["dz"]), 0.0)]
            if form == "build":
                params.append(float(choice["facing"]))
            if form == "area":
                params.append(float(A.RADIUS_CENTERS[choice["radius"]]))
        # The shift option is ours to set: on when the order is appended, off when the queue is empty.
        options = (choice["options"] | common.SHIFT) if append else (choice["options"] & ~common.SHIFT)
        self.last_order[unit["id"]] = frame
        self.fired["order_" + form + ("_appended" if append else "") + ("_army" if expert is self.army else "")] += 1
        return response(request, {"kind": "order", "unit_id": int(unit["id"]),
                                  "command_id": int(expert.command_of[key]), "params": params,
                                  "options": int(options)})


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default="model")        # accepted so run_fullgame.ps1 can pass it
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--map-name", default="")           # not used: the unit policy has no map input
    parser.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    args = parser.parse_args()
    torch.set_num_threads(2)      # a small model: more threads only compete with the game and other jobs
    fired = Counter()
    http = server.make_server(UnitPolicyServer(args.checkpoint, fired), "model", args.port, fired=fired)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()


if __name__ == "__main__":
    main()
