#!/usr/bin/env python3
"""STAND-IN: Team C's stand-in server, with the model's choices sampled instead of greedy.

    python sampling_server.py --policy model --checkpoint <path> [--map-name <name>]

Same arguments as team-c/standin_infer/server.py, which is imported and run unchanged except
for one thing: Team B's predict_orders is called with sample=True (its own option: every
choice - order type, recipients, target, location - is drawn from the predicted distribution
instead of taking the most likely one). Neither Team C's nor Team B's files are edited.
"""

import functools
from pathlib import Path
import sys

TEAM_C = Path(__file__).resolve().parents[4] / "team-c"
sys.path.insert(0, str(TEAM_C / "standin_infer"))
import server   # Team C stand-in server module


class SamplingModelPolicy(server.ModelPolicy):
    def __init__(self, checkpoint, map_name, fired):
        super().__init__(checkpoint, map_name, fired)
        import os
        import torch
        # The same random draws every time the server is started with the same seed.
        # run_fullgame.ps1 sets the variable from -SampleSeed and records it in policy_info.json.
        torch.manual_seed(int(os.environ.get("STANDIN_SAMPLE_SEED", "0")))
        self.predict_orders = functools.partial(self.predict_orders, sample=True)


server.ModelPolicy = SamplingModelPolicy    # build_policy() looks the class up by this name
if __name__ == "__main__":
    server.main()
