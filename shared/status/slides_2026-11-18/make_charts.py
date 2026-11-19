#!/usr/bin/env python3
"""STAND-IN: draw the charts in this folder from the recorded numbers.

    python shared/status/slides_2026-11-18/make_charts.py

Reads shared/ckpt/<name>/train.json (training curves), shared/status/unit_policy_results.jsonl
(development games) and shared/status/benchmark/pilot-v1/*.jsonl (pilot games). Every chart
shows recorded numbers as they are; a game whose policy stopped answering early is marked.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # draw to files, no window
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1]
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"      # fixed order: 1st, 2nd, 3rd series

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "font.size": 12, "text.color": INK, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
                     "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "axes.axisbelow": True,
                     "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left"})


# Pilot policies: the order they are shown in, the name written on the charts, one fixed colour each.
POLICIES = {"standin-human-v1": ("first model (standin-human-v1)", BLUE),
            "unit-v2b": ("new model (unit-v2b)", ORANGE),
            "scripted": ("scripted policy (2 orders)", AQUA),
            "builtin-barb": ("built-in BARb (reference)", "#eda100")}


def policy(label):
    """(name on the charts, colour) of a pilot policy; one not listed above keeps its own name."""
    return POLICIES.get(label, (label, "#6250d6"))


def in_order(labels):
    """The labels in the order of POLICIES, then any others by name."""
    return [label for label in POLICIES if label in labels] + sorted(set(labels) - set(POLICIES))


def rows_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def save(figure, name):
    figure.savefig(HERE / name, dpi=160, bbox_inches="tight")
    plt.close(figure)
    print("wrote", name)


def bars(axis, labels, values, color, marks=None, digits=0):
    """Thin bars with the value written above each; marks[i] adds a note under that value."""
    drawn = axis.bar(range(len(values)), values, width=0.55, color=color)
    axis.set_xticks(range(len(labels)), labels)
    top = max(values) if max(values) > 0 else 1
    axis.set_ylim(0, top * 1.22)
    for index, bar in enumerate(drawn):
        text = f"{values[index]:.{digits}f}" + (f"\n{marks[index]}" if marks and marks[index] else "")
        axis.text(bar.get_x() + bar.get_width() / 2, values[index] + top * 0.02, text,
                  ha="center", va="bottom", fontsize=10, color=INK,
                  bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1})


def training_curve(name):
    """Validation accuracy of the order type during one training run, against the frequency table alone."""
    curve = json.loads((SHARED / "ckpt" / name / "train.json").read_text())["curve"]
    steps = [row["step"] for row in curve]
    figure, axis = plt.subplots(figsize=(8, 4.5))
    for key, label, color in (("type_accuracy", "all orders", BLUE), ("build_type_accuracy", "build orders", ORANGE)):
        values = [row["validation"][key] for row in curve]
        axis.plot(steps, values, color=color, linewidth=2, label=f"{label} (ends at {values[-1]:.2f})")
        # dashed, same colour: the value at step 0, which is the frequency table alone
        axis.axhline(values[0], color=color, linewidth=1, linestyle=(0, (4, 3)),
                     label=f"{label}, frequency table alone ({values[0]:.2f})")
    axis.set_title(f"{name}: order type predicted right on held-out matches")
    axis.set_xlabel("training step")
    axis.set_ylabel("share of validation orders")
    axis.set_ylim(0.3, 1.0)
    axis.legend(frameon=False, loc="lower right")
    save(figure, f"training_curve_{name}.png")


def stop_note(row):
    """'policy stopped at m:ss' (on two lines) for a game whose policy stopped answering
    before the end, else ''."""
    if row["policy_status"] == "answered_until_stopped":
        return ""
    summary = json.loads((SHARED.parent / "team-d" / "standin_eval" / "fullgame" / "runs" / row["run"]
                          / "policy_summary.json").read_text())
    seconds = summary["failed_policy_call"]["source_frame"] // 30
    return f"policy stopped\nat {seconds // 60}:{seconds % 60:02d}"


def short(result):
    """'lost at 13:19' / 'cap' from a result line of evaluate.py."""
    return "cap" if result.startswith("TIMEOUT") else "ended " + result.split("at ")[1].split(" ")[0]


def development_games():
    """Games of evaluate.py: against the idle opponent (units, orders) and against live opponents (length)."""
    rows = rows_of(SHARED / "status" / "unit_policy_results.jsonl")
    idle = [row for row in rows if row["opponent"] == "null" and row["cap_minutes"] == 10]
    labels = [f"{row['checkpoint'].replace('unit-', '')}\nseed {row['seed']}" for row in idle]
    marks = [stop_note(row) for row in idle]
    figure, (left, right) = plt.subplots(1, 2, figsize=(12, 4.5))
    bars(left, labels, [row["finished_units"] for row in idle], BLUE, marks)
    left.set_title("Finished units at 10:00, idle opponent")
    bars(right, labels, [row["orders"] for row in idle], BLUE, marks)
    right.set_title("Orders given in 10 minutes, idle opponent")
    save(figure, "dev_games_idle_opponent.png")

    live = [row for row in rows if row["opponent"] != "null"]
    labels = [f"{row['checkpoint'].replace('unit-', '')}\n{row['opponent']}\nseed {row['seed']}" for row in live]
    minutes = [int(short(row["result"]).split(" ")[1].split(":")[0]) + int(short(row["result"]).split(":")[1]) / 60
               if short(row["result"]) != "cap" else row["cap_minutes"] for row in live]
    marks = [stop_note(row) for row in live]
    figure, axis = plt.subplots(figsize=(10, 4.5))
    bars(axis, labels, minutes, BLUE, marks, digits=1)
    axis.axhline(20, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    axis.text(len(live) - 0.5, 20.2, "20 minute cap", ha="right", va="bottom", fontsize=9, color=MUTED)
    axis.set_ylim(0, 25)
    axis.set_title("Game length against live opponents (every game was lost)" if all(
        short(row["result"]) != "cap" for row in live) else "Game length against live opponents")
    axis.set_ylabel("game minutes")
    save(figure, "dev_games_live_opponents.png")


def pilot():
    """Pilot benchmark: one bar per episode and policy."""
    folder = SHARED / "status" / "benchmark" / "pilot-v1"
    by_label = {path.stem: {row["episode"]: row for row in rows_of(path) if row["outcome"] != "runner_error"}
                for path in sorted(folder.glob("*.jsonl"))}
    if len(by_label) < 2:
        print("pilot: fewer than two policies have rows, no pilot chart")
        return
    episodes = [episode["id"] for episode in json.loads(
        (SHARED.parent / "team-d" / "standin_eval" / "benchmark" / "pilot_suite.json").read_text())["episodes"]]
    for key, title, name, digits in (("game_minutes", "Pilot: game length per episode (minutes, cap 20)", "pilot_game_length.png", 1),
                                     ("orders", "Pilot: orders given per episode", "pilot_orders.png", 0),
                                     ("killed_value", "Pilot: value killed per episode (metal + energy/60)", "pilot_killed_value.png", 0)):
        figure, axis = plt.subplots(figsize=(14, 4.8))
        width = 0.2
        # only the policies that have this number (the built-in AI reference has no order counts)
        having = [label for label in in_order(by_label)
                  if any(row.get(key) is not None for row in by_label[label].values())]
        for number, label in enumerate(having):
            shown, color = policy(label)
            values = [by_label[label].get(episode, {}).get(key) or 0 for episode in episodes]
            places = [index + (number - (len(having) - 1) / 2) * (width + 0.02) for index in range(len(episodes))]
            axis.bar(places, values, width=width, color=color, label=shown)
            for place, value, episode in zip(places, values, episodes):
                row = by_label[label].get(episode)
                note = f"{value:.{digits}f}" if row else "no row"
                if row and key == "game_minutes":
                    note += f"\n{row['outcome']}"
                axis.text(place, value, note, ha="center", va="bottom", fontsize=8, color=INK)
        axis.set_xticks(range(len(episodes)), episodes)
        axis.set_title(title)
        axis.margins(y=0.18)
        axis.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncols=4)   # under the plot
        save(figure, name)


def pilot_outcomes():
    """Pilot benchmark: per policy and opponent, how many games were won, lost, or reached the cap."""
    folder = SHARED / "status" / "benchmark" / "pilot-v1"
    groups = {}                                 # (policy label, opponent) -> list of outcomes
    for path in sorted(folder.glob("*.jsonl")):
        for row in rows_of(path):
            if row["outcome"] != "runner_error":
                groups.setdefault((row["label"], row["opponent"]), []).append(row["outcome"])
    if not groups:
        return
    groups = {key: groups[key] for label in in_order({label for label, _ in groups})
              for key in groups if key[0] == label}                  # policies in the fixed order
    figure, axis = plt.subplots(figsize=(11, 0.62 * len(groups) + 1.6))
    names = [f"{policy(label)[0]} vs {opponent}" for label, opponent in groups]
    for kind, color in (("win", BLUE), ("loss", ORANGE), ("cap", "#b9b8b2")):
        left = [sum(outcome in ("win", "loss", "cap")[:("win", "loss", "cap").index(kind)] for outcome in outcomes)
                for outcomes in groups.values()]            # where this segment starts
        counts = [outcomes.count(kind) for outcomes in groups.values()]
        axis.barh(names, counts, left=left, height=0.5, color=color, edgecolor=SURFACE, linewidth=2,
                  label={"win": "won", "loss": "lost", "cap": "no winner by the 20 minute cap"}[kind])
        for place, (start, count) in enumerate(zip(left, counts)):
            if count:
                axis.text(start + count / 2, place, str(count), ha="center", va="center", fontsize=11, color=INK)
    for place, outcomes in enumerate(groups.values()):      # the win rate, written at the end of each bar
        axis.text(len(outcomes) + 0.08, place, f"win rate {outcomes.count('win')} of {len(outcomes)}",
                  va="center", fontsize=10, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, max(len(outcomes) for outcomes in groups.values()) + 1.2)
    axis.set_xlabel("games")
    axis.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    axis.grid(False)
    axis.set_title("Pilot benchmark: game results per policy and opponent")
    axis.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncols=3)
    save(figure, "pilot_win_rate.png")


def first_model_orders():
    """The first model's orders in one 4 minute game, by what became of them. The counts are the
    table in shared/status/team-d.md ("Why standin-human-v1's build orders produced no buildings",
    run game_20261118_030059: 334 orders, all to the commander, our team is Armada)."""
    counts = [("not a build order (mostly move)", 198),
              ("build a unit of the other faction (Cortex)", 84),
              ("build an Armada unit, position given,\nnever seen in the commander's queue", 30),
              ("build an Armada unit, no position given", 12),
              ("build an Armada unit, seen in the queue\n(sites 1,017 to 7,393 elmos away)", 8),
              ("build a cosmetic unit", 2)]
    figure, axis = plt.subplots(figsize=(10, 4.6))
    names = [name for name, _ in counts]
    values = [value for _, value in counts]
    axis.barh(names, values, height=0.55, color=BLUE)
    for place, value in enumerate(values):
        axis.text(value + 3, place, str(value), va="center", fontsize=11, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, 225)
    axis.grid(False)
    axis.set_xlabel("orders (334 in total, one game, 4 minutes)")
    axis.set_title("First model: what its orders were. Buildings finished: 0")
    save(figure, "first_model_orders.png")


def first_vs_new():
    """First model against the new model on the six pilot games: four numbers, each as the mean
    of the six games (bar) with the lowest and highest game written under it."""
    folder = SHARED / "status" / "benchmark" / "pilot-v1"
    labels = ("standin-human-v1", "unit-v2b")
    rows = {label: rows_of(folder / f"{label}.jsonl") for label in labels}
    panels = (("share of orders reaching the engine", lambda r: 1 - r["orders_without_callback_share"], 2),
              ("highest metal income", lambda r: r["max_metal_income"], 1),
              ("highest energy income", lambda r: r["max_energy_income"], 0),
              ("most metal spots held", lambda r: r["max_metal_spots"], 1))
    figure, axes = plt.subplots(1, len(panels), figsize=(15, 4.4))
    for axis, (title, number, digits) in zip(axes, panels):
        for place, label in enumerate(labels):
            values = [number(row) for row in rows[label]]
            average = sum(values) / len(values)
            axis.bar(place, average, width=0.55, color=policy(label)[1])
            axis.text(place, average, f"{average:.{digits}f}", ha="center", va="bottom", fontsize=12, color=INK)
            axis.text(place, -0.14, f"{min(values):.{digits}f} to {max(values):.{digits}f}", ha="center", va="top",
                      fontsize=9, color=MUTED, transform=axis.get_xaxis_transform())
        axis.set_xticks(range(len(labels)), ["first model", "new model"])
        axis.set_title(title, fontsize=11)
        axis.margins(y=0.15)
    figure.suptitle("First model and new model on the same six pilot games: mean of the games (lowest to highest below)",
                    x=0.01, ha="left", fontsize=13, fontweight="bold")
    figure.tight_layout()
    save(figure, "first_vs_new_model.png")


def compare_one_by_one():
    """First model against the new model: one image per number, in the folder compare_first_vs_new.
    The bar is the mean of the six pilot games; each dot is one game."""
    folder = SHARED / "status" / "benchmark" / "pilot-v1"
    labels = ("standin-human-v1", "unit-v2b")
    rows = {label: rows_of(folder / f"{label}.jsonl") for label in labels}
    out = HERE / "compare_first_vs_new"
    out.mkdir(exist_ok=True)

    # 1. Won / lost / reached the cap, as counts of games.
    figure, axis = plt.subplots(figsize=(7.5, 3.2))
    for kind, color, name in (("win", BLUE, "won"), ("loss", ORANGE, "lost"), ("cap", "#b9b8b2", "no winner by the cap")):
        order = ("win", "loss", "cap")
        left = [sum(row["outcome"] in order[:order.index(kind)] for row in rows[label]) for label in labels]
        counts = [sum(row["outcome"] == kind for row in rows[label]) for label in labels]
        axis.barh(["first model", "new model"], counts, left=left, height=0.5, color=color, edgecolor=SURFACE,
                  linewidth=2, label=name)
        for place, (start, count) in enumerate(zip(left, counts)):
            if count:
                axis.text(start + count / 2, place, str(count), ha="center", va="center", fontsize=12, color=INK)
    axis.invert_yaxis()
    axis.grid(False)
    axis.set_xlabel("games (6 each)")
    axis.set_title("Game results")
    axis.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.3), ncols=3)
    figure.savefig(out / "1_game_results.png", dpi=160, bbox_inches="tight")
    plt.close(figure)

    # 2 and on: one number per image.
    numbers = (("2_orders_per_game", "Orders given per game", lambda r: r["orders"], 0),
               ("3_orders_reaching_engine", "Share of orders that reached the engine",
                lambda r: 1 - r["orders_without_callback_share"], 2),
               ("4_metal_income", "Highest metal income in the game", lambda r: r["max_metal_income"], 1),
               ("5_energy_income", "Highest energy income in the game", lambda r: r["max_energy_income"], 0),
               ("6_metal_spots", "Most metal spots held in the game", lambda r: r["max_metal_spots"], 1),
               ("7_units_at_end", "Finished units at the last decision", lambda r: r["finished_units_at_last_decision"], 1),
               ("8_value_killed", "Value killed (metal + energy/60)", lambda r: r["killed_value"], 0),
               ("9_value_lost", "Value lost (metal + energy/60)", lambda r: r["lost_value"], 0),
               ("10_game_length", "Game length in minutes (cap 20)", lambda r: r["game_minutes"], 1))
    for name, title, number, digits in numbers:
        figure, axis = plt.subplots(figsize=(5.2, 4.2))
        for place, label in enumerate(labels):
            values = [number(row) for row in rows[label]]
            average = sum(values) / len(values)
            axis.bar(place, average, width=0.5, color=policy(label)[1])
            # each game as a dot beside the bar, spread a little so equal values stay visible
            spots = [place + 0.33 + 0.03 * (index - 2.5) for index in range(len(values))]
            axis.scatter(spots, values, s=42, color=policy(label)[1], edgecolor=SURFACE, linewidth=1.5, zorder=3)
            axis.text(place, average, f"{average:.{digits}f}", ha="center", va="bottom", fontsize=13, color=INK)
            axis.text(place + 0.1, -0.13, f"games: {min(values):.{digits}f} to {max(values):.{digits}f}", ha="center",
                      va="top", fontsize=9, color=MUTED, transform=axis.get_xaxis_transform())
        axis.set_xticks([0.1, 1.1], ["first model", "new model"])
        axis.set_xlim(-0.45, 1.65)
        axis.set_title(title, fontsize=13)
        axis.margins(y=0.15)
        figure.savefig(out / f"{name}.png", dpi=160, bbox_inches="tight")
        plt.close(figure)
    print("wrote", len(numbers) + 1, "images in compare_first_vs_new")


if __name__ == "__main__":
    compare_one_by_one()
    first_vs_new()
    first_model_orders()
    pilot_outcomes()
    for checkpoint in ("unit-v2a", "unit-v2b"):
        if (SHARED / "ckpt" / checkpoint / "train.json").exists():
            training_curve(checkpoint)
    development_games()
    pilot()
