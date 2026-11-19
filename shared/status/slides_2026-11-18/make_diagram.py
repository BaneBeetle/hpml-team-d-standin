#!/usr/bin/env python3
"""STAND-IN: draw harness_diagram.png, the path of one decision in a full game.

    python shared/status/slides_2026-11-18/make_diagram.py

Boxes and arrows only; the text in each box names the file that does the step.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
SURFACE, INK, MUTED, LINE, FILL = "#fcfcfb", "#0b0b0b", "#52514e", "#86b6ef", "#e9f1fc"

# (x, y, width, height, title, lines under the title)
BOXES = {
    "game": (0.2, 3.4, 3.4, 2.0, "BAR game",
             ["headless Recoil 2026.09.02 in Docker", "map Supreme Isthmus v2.1", "team 0: our checkpoint (Armada)",
              "team 1: a built-in AI (SimpleAI, BARb)"]),
    "widget": (4.9, 3.4, 3.4, 2.0, "Spectator widget",
               ["standin_control.lua", "every 15 frames: observation out", "one order in: placed, given to the unit"]),
    "bridge": (9.6, 3.4, 3.4, 2.0, "Bridge",
               ["bridge.py + Roshan's PolicyWorker", "3 s budget per decision", "stops asking after a failure"]),
    "server": (14.3, 3.4, 3.4, 2.0, "Policy server",
               ["Windows, HTTP /predict, protocol v1", "loads the checkpoint", "answers one order or 'no order'"]),
    "files": (4.9, 0.3, 8.1, 2.0, "Written for every game (its run folder)",
              ["run_settings.json: map, opponent, engine, seeds, settings",
               "teamstats.json, income.png: income, value killed / lost",
               "policy_summary.json: orders, drops, no-order share, response times, timeouts",
               "replay (.sdfz) with -SaveReplay"]),
}
ARROWS = [("game", "widget", "observation"), ("widget", "bridge", "request"), ("bridge", "server", "request"),
          ("server", "bridge", "order"), ("bridge", "widget", "order"), ("widget", "game", "command")]

figure, axis = plt.subplots(figsize=(18.5, 5.9))
figure.set_facecolor(SURFACE)
axis.set_xlim(0, 17.9)
axis.set_ylim(0, 5.7)
axis.axis("off")
for x, y, width, height, title, lines in BOXES.values():
    axis.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.02,rounding_size=0.12",
                                  facecolor=FILL, edgecolor=LINE, linewidth=1.5))
    axis.text(x + 0.15, y + height - 0.3, title, fontsize=12, fontweight="bold", color=INK, va="center")
    for number, line in enumerate(lines):
        axis.text(x + 0.15, y + height - 0.7 - 0.33 * number, line, fontsize=9.5, color=MUTED, va="center")
for start, end, label in ARROWS:
    x0, y0, w0, h0 = BOXES[start][:4]
    x1, y1, w1, h1 = BOXES[end][:4]
    forward = x1 > x0                               # requests run along the top, orders come back below
    y = y0 + h0 * (0.72 if forward else 0.28)
    begin, finish = ((x0 + w0, x1) if forward else (x0, x1 + w1))
    axis.add_patch(FancyArrowPatch((begin + (0.05 if forward else -0.05), y), (finish - (0.05 if forward else -0.05), y),
                                   arrowstyle="-|>", mutation_scale=14, color=MUTED, linewidth=1.3))
    axis.text((begin + finish) / 2, y + 0.13, label, fontsize=9, color=MUTED, ha="center")
# the run folder gets files from the game side and from the bridge
for source in ("widget", "bridge"):
    x, y, width, _ = BOXES[source][:4]
    axis.add_patch(FancyArrowPatch((x + width / 2, y - 0.05), (x + width / 2, 0.3 + 2.0 + 0.05),
                                   arrowstyle="-|>", mutation_scale=14, color=MUTED, linewidth=1.3))
axis.set_title("One decision in a full game (local stand-in harness)", loc="left", fontsize=14, fontweight="bold", color=INK)
figure.savefig(HERE / "harness_diagram.png", dpi=160, bbox_inches="tight", facecolor=SURFACE)
print("wrote harness_diagram.png")
