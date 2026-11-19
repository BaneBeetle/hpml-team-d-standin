"""STAND-IN unit policy: the pieces shared by the dataset builder, the trainer and the server.

The unit policy answers one question: "this unit of mine is idle, what order does it get?"
That is a different question from Team B's B03 model ("which order type next, then which
units"), so this is our own local test model, not Team B's work. It reuses Team B's
bar_policy.actions.arg_form to read what kind of order a recorded order is.

A state is turned into plain arrays here (featurize), the same way for Team A's recorded
states and for the live observation the game sends.
"""

from pathlib import Path
import sys

import numpy as np

TEAM_D = Path(__file__).resolve().parents[2]
SHARED = TEAM_D.parent / "shared"
sys.path.insert(0, str(TEAM_D))
from bar_policy import actions as A      # Team B's code: arg_form, RADIUS_CENTERS, OPTION_BITS

UNIT_CAP = 384            # most units kept from one state (own units first)
QUEUE_CAP = 16            # the exporter returns at most 16 queue entries
# Per-unit numbers, in this order. x and z are map coordinates in elmos.
UNIT_NUMBERS = ("x", "z", "health_fraction", "build_progress", "queue_length", "is_own",
                "tail_x", "tail_z", "has_tail")
# tail = the position of the last order in the unit's queue that has one (where the unit
# will be when its queue is done). An order appended to a queue is placed relative to it.
SHIFT = 32                # the option bit "append to the queue" (the shift key)
# Never chosen in a game and left out of training: WAIT (5) parks a unit until WAIT is sent
# again, SELFD (65) destroys it, and BAR's custom commands (30000 and up) have numbers that
# were not checked across game versions.
def blocked(command_id):
    return command_id in (5, 65) or command_id >= 30000
# Per-state numbers: metal then energy (current, storage, income, expense, pull), then game minutes.
RESOURCE_FIELDS = ("current", "storage", "income", "expense", "pull")

# An order's position is predicted relative to the unit that gets it, as two classes
# (east-west and north-south). Class edges in elmos; a class decodes to its centre.
EDGES = (16, 48, 96, 160, 256, 400, 640, 1024, 1600, 2560, 4096)
CENTRES = (0, 32, 72, 128, 208, 328, 520, 832, 1312, 2080, 3328, 5000)
N_BINS = 2 * len(EDGES) + 1          # negative classes, zero, positive classes


def offset_class(distance):
    """Signed distance in elmos -> class number 0 .. N_BINS-1 (the middle class is "about 0")."""
    size = sum(abs(distance) >= edge for edge in EDGES)
    return len(EDGES) + (size if distance >= 0 else -size)


def class_offset(number):
    """Class number -> signed distance in elmos (the centre of the class)."""
    size = number - len(EDGES)
    return CENTRES[abs(size)] * (1 if size >= 0 else -1)


def type_of(action):
    """(key, form, value) of a recorded order, or None if Team B's arg_form does not support it.

    key is what the model predicts, e.g. "MOVE@pos", "BUILD_UNITDEF_405@build", "FIRE_STATE=2".
    form says which other fields the order has: unit (a target), pos, area, build, factory.
    """
    name = action["command_name"]
    if action["command_id"] < 0 and len(action["params"]) == 3:
        # BARb orders a factory to build with a position and no facing (a player's factory
        # order has no parameters). Both are the same order type here.
        return f"{name}@factory", "factory", None
    form, value = A.arg_form(action)
    if form is None or form == "feature":      # map features (trees, wrecks) are not in the observation
        return None
    if form == "none":
        return name, form, None
    if form == "value":
        return f"{name}={value}", form, value
    return f"{name}@{form}", form, None


def featurize(state, team, frame, keep_first=()):
    """One state (Team A's export format, also the live observation) -> a dict of arrays.

    Units are ordered own units first (by id), then the others (by id); `keep_first` ids go
    to the very front so the cap never cuts them. Missing values become 0.
    """
    units = [u for u in (state.get("units") or []) if isinstance(u, dict) and "id" in u]
    first = set(keep_first)
    units.sort(key=lambda u: (u["id"] not in first, u.get("teamID") != team, u["id"]))
    units = units[:UNIT_CAP]
    count = len(units)
    out = {"unit_id": np.zeros(count, np.int32), "def_id": np.zeros(count, np.int32),
           "queue_command": np.zeros(count, np.int32), "tail_command": np.zeros(count, np.int32),
           "numbers": np.zeros((count, len(UNIT_NUMBERS)), np.float32)}
    for row, unit in enumerate(units):
        queue = unit.get("queue") if isinstance(unit.get("queue"), list) else []   # empty arrives as {}
        position = unit.get("position") or [0.0, 0.0, 0.0]
        health, max_health = unit.get("health") or 0.0, unit.get("maxHealth") or 0.0
        out["unit_id"][row] = unit["id"]
        out["def_id"][row] = unit.get("defID") or 0
        out["queue_command"][row] = queue[0].get("id", 0) if queue else 0
        out["tail_command"][row] = queue[-1].get("id", 0) if queue else 0
        tail = next((q["params"] for q in reversed(queue)
                     if isinstance(q.get("params"), list) and len(q["params"]) >= 3), None)
        out["numbers"][row] = (position[0], position[2],
                               health / max_health if max_health > 0 else 0.0,
                               unit.get("buildProgress") or 0.0,
                               min(len(queue), QUEUE_CAP) / QUEUE_CAP,
                               float(unit.get("teamID") == team),
                               tail[0] if tail else 0.0, tail[2] if tail else 0.0, float(tail is not None))
    resources = state.get("resources") or {}
    out["resources"] = np.array(
        [(resources.get(kind) or {}).get(field) or 0.0
         for kind in ("metal", "energy") for field in RESOURCE_FIELDS]
        + [frame / 1800.0], np.float32)                  # 30 frames a second -> game minutes
    return out
