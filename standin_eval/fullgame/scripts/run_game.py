#!/usr/bin/env python3
"""STAND-IN COPY of bar-harness scripts/run_game.py: a policy plays team 0 against BARb.

Copied from C:\\Users\\lolly\\OneDrive\\Desktop\\Projects\\bar-harness (the original is untouched).
Changed in this copy, each marked "STAND-IN" below:
  - make_startscript: team 0's AI is the engine's NullAI (it owns the team and gives no orders),
    and three debug commands turn on god mode for allied teams, so the spectator host's control
    widget (widgets/standin_control.lua) can give team 0's orders. Cheats are on for frames 2-20.
  - launch: writes control_config.json for that widget, starts scripts/bridge.py before the
    game and stops it after, and deletes the request stream unless --keep-requests.
Everything else, including the report and the win-rate summary, is the original code.
The original docstring follows.

Step 3: launch one headless BARb vs BARb game, wait for it to end, report the result.

Run inside WSL (where Docker is), with the venv scripts/setup_bar.sh makes:
    ~/bar-data/venv/bin/python scripts/run_game.py                  # 20 min game-time cap
    ~/bar-data/venv/bin/python scripts/run_game.py --cap-minutes 2  # a short game
    ~/bar-data/venv/bin/python scripts/run_game.py --games 10       # 10 games in a row, then the win rate
    ~/bar-data/venv/bin/python scripts/run_game.py --report runs/game_<stamp>   # report a finished run again

The game is BAR's tools/headless_testing/startscript_barb_smoke.txt with three lines changed:
  - the player is a spectator: as shipped the game never starts (see scripts/run_smoke.sh)
  - deathmode=com (BAR's default: a team is out when its commander dies) instead of neverend,
    so the game can end with a winner; plus minspeed/maxspeed = --speed (default 20)
  - debugcommands=1:speedcontrol 0|<cap>:quitforce instead of 1800:quitforce (20 min = 36000 frames)
At BAR's normal 1x pacing a 20 min game took ~26 min of wall time; asking for 20x lets the
server run as fast as the host keeps up (its lag protection still slows it under load).
The simulation is frame-based, so speed changes wall time, not the game's rules. BARb vs BARb
games already differ run to run at 1x despite FixedRNGSeed, so treat each game as one sample.
The harness widget (widgets/harness_teamstats.lua) writes runs/<run>/teamstats.json every
15 s of game time, the winner at GameOver, and a timeout result one frame before the cap.
After GameOver, BAR's autoquit widget exits the engine 12 s later, so the game ends either way.
"""

import argparse
import json
import os
import re
import string
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS / "scripts"))  # win_rate.py, also when Python runs with -I
from win_rate import summarize  # noqa: E402
import run_settings  # noqa: E402  STAND-IN: writes run_settings.json (what was played)

GAME_SPEED = 30  # frames per second of game time
# Where docker-compose.yml mounts the run folder inside the container.
CONTAINER_RUN_DIR = "/bar/LuaUI/Widgets/harness_run"
# One color per team, in team order (categorical slots 1-2 of the dataviz reference palette).
TEAM_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def load_env(path):
    """The KEY=VALUE lines of .env, with ${KEY} expanded from earlier keys, as Compose does."""
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = string.Template(value.strip()).safe_substitute(env)
    return env


# STAND-IN: what can sit in team 1's slot: name -> (ShortName, Version, BARb profile or None).
# "barb" is the smoke script as it is (BARb, whose AIOptions.lua default profile is "hard").
# BARb profiles: folders under BAR's luarules/configs/BARb/stable/config. SimpleAI and its two
# variants: BAR's luaai.lua and luarules/gadgets/ai_simpleai.lua, written in a start script the
# way singleplayer/scenarios/scenario002.lua does. NullAI: the engine's AI that gives no orders.
OPPONENTS = {
    "barb": ("BARb", "stable", None),
    "barb-easy": ("BARb", "stable", "easy"),
    "barb-medium": ("BARb", "stable", "medium"),
    "barb-hard-aggressive": ("BARb", "stable", "hard_aggressive"),
    "simple": ("SimpleAI", "<not-versioned>", None),
    "simple-defender": ("SimpleDefenderAI", "<not-versioned>", None),
    "simple-constructor": ("SimpleConstructorAI", "<not-versioned>", None),
    "null": ("NullAI", "0.1", None),
}


def policy_team_name():
    """STAND-IN: the name team 0 shows in the game, the replay and the report, so it is obvious
    which bot is ours: OUR_MODEL_<checkpoint folder>, or OUR_MODEL_<policy> without a checkpoint."""
    info = HARNESS / "policy_info.json"         # written by run_fullgame.ps1 before the game
    policy = json.loads(info.read_text(encoding="utf-8-sig")) if info.exists() else {}
    what = Path(policy["checkpoint"].replace("\\", "/")).parent.name if policy.get("checkpoint") \
        else policy.get("policy", "policy")
    return "OUR_MODEL_" + re.sub(r"[^A-Za-z0-9_.-]", "_", what)   # no spaces or ';' in a start script value


def make_startscript(src, dst, cap_frame, speed, swap_sides=False, record=False, save_replay=False,
                     opponent="barb"):
    """Copy the smoke startscript with the three edits above; each must change exactly one line.
    swap_sides also swaps the two teams' factions (Side=Armada / Side=Cortex), keeping start spots."""
    text = src.read_text()
    if swap_sides:
        swap = {"Armada": "Cortex", "Cortex": "Armada"}
        text, count = re.subn(r"^(\s*Side=)(Armada|Cortex);", lambda m: f"{m[1]}{swap[m[2]]};", text, flags=re.M)
        if count != 2:
            sys.exit(f"side swap matched {count} Side= lines of {src}, expected 2")
    edits = [
        (r"^(\s*Spectator=)0;", r"\g<1>1;"),
        # Speed: minspeed/maxspeed are engine modoptions (GameSetup.cpp), and the server applies
        # them at game start, so the game asks for `speed` x real time from frame 0.
        (r"^(\s*)deathmode=neverend;",
         rf"\g<1>deathmode=com;\n\g<1>minspeed={speed:g};\n\g<1>maxspeed={speed:g};"),
        # "speedcontrol 0" makes the server aim at 75% instead of 60% of the host's time spent
        # simulating when it slows the game down (GameServer.cpp LagProtection).
        (r"^(\s*debugcommands=)1800:quitforce;", rf"\g<1>1:speedcontrol 0|{cap_frame}:quitforce;"),
    ]
    if not record:  # STAND-IN: a policy game. With record=True the three original edits above are all.
        # One debug command per frame (the gadget keys them by frame). "cheat 1" lets BAR's dev
        # helper run; "luarules godmodeally" toggles control of allied teams' units on (the
        # spectator host's team is 0, so that is team 0); "cheat 0" turns cheats off again.
        edits[2] = (r"^(\s*debugcommands=)1800:quitforce;",
                    rf"\g<1>1:speedcontrol 0|2:cheat 1|10:luarules godmodeally|20:cheat 0|{cap_frame}:quitforce;")
        # Team 0 ([AI0]) is owned by the engine's NullAI 0.1 instead of BARb.
        edits += [(r"(\[AI0\]\s*\{[^}]*?Name=)BARbarianAI\(1\);", rf"\g<1>{policy_team_name()};"),
                  (r"(\[AI0\]\s*\{[^}]*?ShortName=)BARb;", r"\g<1>NullAI;"),
                  (r"(\[AI0\]\s*\{[^}]*?Version=)stable;", r"\g<1>0.1;")]
    if save_replay:  # STAND-IN: the smoke script has RecordDemo=0; 1 makes the engine write a replay
        edits.append((r"^(\s*RecordDemo=)0;", r"\g<1>1;"))
    if opponent != "barb":  # STAND-IN: another AI, or another BARb profile, in team 1's slot ([AI1])
        short, version, profile = OPPONENTS[opponent]
        edits += [(r"(\[AI1\]\s*\{[^}]*?Name=)BARbarianAI\(2\);", rf"\g<1>{opponent}(2);"),
                  (r"(\[AI1\]\s*\{[^}]*?ShortName=)BARb;", rf"\g<1>{short};"),
                  (r"(\[AI1\]\s*\{[^}]*?Version=)stable;", rf"\g<1>{version};")]
        if profile:         # an [Options] block inside [AI1]; added last, after the edits above
            edits.append((r"(\[AI1\]\s*\{)", rf"\g<1>\n\t\t[Options]\n\t\t{{\n\t\t\tprofile={profile};\n\t\t}}"))
    for pattern, replacement in edits:
        text, count = re.subn(pattern, replacement, text, flags=re.M)
        if count != 1:
            sys.exit(f"startscript edit {pattern!r} matched {count} lines of {src}, expected 1")
    dst.write_text(text)


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def read_stats(path):
    """teamstats.json, or None while it is missing or unreadable (the widget renames it into place)."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class Tee:
    """Print to the terminal and to a file (the run's report.txt) at the same time."""

    def __init__(self, path):
        self.file, self.stdout = open(path, "w"), sys.stdout

    def write(self, text):
        self.stdout.write(text)
        self.file.write(text)

    def flush(self):
        self.stdout.flush()
        self.file.flush()


def launch(cap_minutes, wall_minutes, speed, swap_sides=False, started=None, keep_requests=False, record=False,
           save_replay=False, opponent="barb"):
    """Run one game and report it. Returns (report exit code, why it was stopped or None).
    The run folder is appended to `started` as soon as it exists, so a caller still has it
    when an exception (a second Ctrl+C, a failed build) escapes from here."""
    pins = load_env(HARNESS / ".env")
    bar_dir = Path(os.environ.get("BAR_DIR", Path.home() / "bar-data" / "Beyond-All-Reason"))
    head = subprocess.run(["git", "-C", str(bar_dir), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.stdout.strip() != pins["BAR_COMMIT"]:
        sys.exit(f"BAR checkout at {bar_dir} is missing or not at {pins['BAR_COMMIT']}; run scripts/setup_bar.sh")

    cap_frame = round(cap_minutes * 60 * GAME_SPEED)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + ("_swapped" if swap_sides else "")
    # STAND-IN: recording runs (BARb vs BARb with the recorder widget) get their own folder prefix.
    run_dir = HARNESS / "runs" / f"{'record' if record else 'game'}_{stamp}"
    run_dir.mkdir(parents=True)
    if started is not None:
        started.append(run_dir)
    make_startscript(bar_dir / "tools/headless_testing/startscript_barb_smoke.txt", run_dir / "startscript.txt",
                     cap_frame, speed, swap_sides, record, save_replay, opponent)
    # STAND-IN: with --save-replay a second compose file mounts <run folder>/demos at /bar/demos.
    # Without it the docker command is the same as before.
    compose = ["docker", "compose"]
    if save_replay:
        (run_dir / "demos").mkdir()
        compose += ["-f", "docker-compose.yml", "-f", "docker-compose.replay.yml"]

    if record:
        # STAND-IN: read by widgets/standin_recorder.lua. Same tick length and first frame as a
        # policy game, so recorded observations are taken the way the policy later gets them.
        (run_dir / "record_config.json").write_text(json.dumps({"interval": 15, "first_frame": 90}))
    else:
        # STAND-IN: the control widget and the bridge both read this file. The first nine keys are
        # Roshan's configs/control_loop.json (same budgets); run_timeout is this game's wall limit.
        info = HARNESS / "policy_info.json"     # written by run_fullgame.ps1: policy name, checkpoint, hash
        policy_info = {}
        if info.exists():                       # utf-8-sig: tolerate a byte-order mark from PowerShell
            policy_info = json.loads(info.read_text(encoding="utf-8-sig"))
            policy_info["opponent"] = opponent  # STAND-IN: who was in team 1's slot in this game
            (run_dir / "policy_info.json").write_text(json.dumps(policy_info, indent=1))
        (run_dir / "control_config.json").write_text(json.dumps({
            "protocol_version": 1, "decision_interval_frames": 15, "simulation_hz": 30,
            "startup_timeout_seconds": 240, "policy_timeout_seconds": 3, "frame_timeout_seconds": 30,
            "run_timeout_seconds": wall_minutes * 60, "seed": 1, "timing_mode": "paced",
            # first_frame 90: after the debug commands above have run (cheats were off by frame 48).
            "match_id": run_dir.name, "generation": 0, "control_team": 0, "first_frame": 90,
            # place_builds: the widget moves a build order to the nearest place it can be built
            # (run_fullgame.ps1 -PlaceBuilds; see place() in widgets/standin_control.lua).
            "place_builds": bool(policy_info.get("place_builds"))}, indent=1))

    run_settings.write(run_dir)     # STAND-IN: the settings of this run, before the game starts
    env = dict(os.environ, BAR_DIR=str(bar_dir), RUN_DIR=f"./runs/{run_dir.name}",
               STARTSCRIPT=f"{CONTAINER_RUN_DIR}/startscript.txt")
    print(f"== Building image (engine {pins['ENGINE_VERSION']})", flush=True)
    subprocess.run(["docker", "compose", "build", "bar"], cwd=HARNESS, env=env, check=True)
    # STAND-IN: the policy bridge runs beside the game, from after the build until the game ends.
    bridge = None
    if not record:
        bridge = subprocess.Popen([sys.executable, str(HARNESS / "scripts" / "bridge.py"), str(run_dir)],
                                  stdout=open(run_dir / "bridge.log", "wb"), stderr=subprocess.STDOUT)

    name = f"bar-game-{stamp}"
    print(f"== Running {'BARb' if record else 'policy (team 0)'} vs {opponent}{' (sides swapped)' if swap_sides else ''} at up to {speed:g}x: cap {clock(cap_frame / GAME_SPEED)} game time "
          f"(frame {cap_frame}), wall-clock limit {wall_minutes:g} min")
    print(f"   run folder: runs/{run_dir.name}  (engine log: console.log)", flush=True)
    stats_path = run_dir / "teamstats.json"
    stopped = None
    # Wall time by the realtime clock: in WSL2, CLOCK_MONOTONIC (time.monotonic) ran 5-8% fast
    # against Windows time on this machine, while the realtime clock is kept in sync with the host.
    start = time.time()
    with open(run_dir / "console.log", "wb") as log:
        proc = subprocess.Popen(compose + ["run", "--rm", "-T", "--name", name, "bar"],
                                cwd=HARNESS, env=env, stdout=log, stderr=subprocess.STDOUT)
        next_progress = start + 60
        try:
            while True:
                try:
                    rc = proc.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    pass
                now = time.time()
                if now - start > wall_minutes * 60:
                    stopped = f"stopped at the {wall_minutes:g} min wall-clock limit"
                    break
                if now >= next_progress:
                    next_progress += 60
                    stats = read_stats(stats_path)
                    frame = stats.get("written_frame", 0) if stats else 0
                    print(f"   wall {clock(now - start)}   game {clock(frame / GAME_SPEED)}", flush=True)
        except KeyboardInterrupt:
            stopped = "stopped by Ctrl+C"
        if stopped:
            subprocess.run(["docker", "stop", "-t", "5", name], capture_output=True)
            rc = proc.wait()
    ended = time.time()
    (run_dir / "wall.json").write_text(json.dumps(
        {"started_unix": round(start, 3), "ended_unix": round(ended, 3), "exit_code": rc, "stopped": stopped},
        indent=1))
    print(f"== Engine exited (code {rc}){' - ' + stopped if stopped else ''}")
    run_settings.write(run_dir)     # STAND-IN: again, now with what the game reported and any replay
    if save_replay:         # STAND-IN: say which replay file the engine left in the run folder
        for demo in sorted((run_dir / "demos").glob("*.sdfz")):
            print(f"== Replay: runs/{run_dir.name}/demos/{demo.name} ({demo.stat().st_size} bytes)")
    if record:              # STAND-IN: a recording run has no bridge and no policy
        return report_to_file(run_dir, stopped=stopped), stopped
    # STAND-IN: tell the bridge the game is over, wait for its summary, show the policy status.
    (run_dir / "bridge_stop").write_text("")
    bridge.wait(timeout=60)
    if not keep_requests:   # a full observation per decision: large, and summarized by the bridge
        (run_dir / "policy_requests.jsonl").unlink(missing_ok=True)
    try:
        policy = json.loads((run_dir / "policy_summary.json").read_text())
        print(f"== Policy (stand-in): {policy['policy_status']}, {policy['decisions']['predicts_answered']} "
              f"predicts answered, {policy['orders_submitted']} orders submitted (policy_summary.json)")
    except (OSError, ValueError):
        print("== Policy (stand-in): no policy_summary.json; see bridge.log")
    return report_to_file(run_dir, stopped=stopped), stopped


def report_to_file(run_dir, stopped=None):
    """report(), printed and saved to the run's report.txt."""
    sys.stdout = Tee(run_dir / "report.txt")
    try:
        return report(run_dir, stopped=stopped)
    finally:
        sys.stdout.file.close()
        sys.stdout = sys.stdout.stdout


def plot_income(stats, out_path, end_frame, end_label):
    """Metal and energy income per team over game time, one panel each (their scales differ)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    teams = {t["team"]: t for t in stats["teams"]}
    order = [t["team"] for t in stats["teams"]][: len(TEAM_COLORS)]
    samples = stats["samples"]
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True, facecolor=SURFACE)
    for ax, key, title in [(axes[0], "metalIncome", "Metal income (per second)"),
                           (axes[1], "energyIncome", "Energy income (per second)")]:
        ax.set_facecolor(SURFACE)
        ends = []  # (last x, last y, label) per line, for the direct labels
        for index, team_id in enumerate(order):
            points = [(s["frame"] / GAME_SPEED / 60, row.get(key))
                      for s in samples for row in s["teams"] if row["team"] == team_id and row.get(key) is not None]
            if not points:
                continue
            xs, ys = zip(*points)
            label = f"team {team_id} ({teams[team_id].get('side', '?')})"
            ax.plot(xs, ys, color=TEAM_COLORS[index], linewidth=2, label=label, solid_capstyle="round")
            ends.append((xs[-1], ys[-1], label))
        ax.axvline(end_frame / GAME_SPEED / 60, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_ylim(bottom=0)
        ax.set_xlim(left=0)
        # Direct labels at the line ends, pushed apart when the lines end close together.
        low, high = ax.get_ylim()
        axis_points = ax.get_window_extent().height * 72 / fig.dpi  # axes height in points
        placed = []
        for x, y, label in sorted(ends, key=lambda end: end[1]):
            frac = (y - low) / ((high - low) or 1)
            if placed and frac - placed[-1] < 0.08:
                frac = placed[-1] + 0.08
            placed.append(frac)
            ax.annotate(label, (x, y), xytext=(8, (frac - (y - low) / ((high - low) or 1)) * axis_points),
                        textcoords="offset points", va="center", fontsize=9, color=INK_MUTED,
                        annotation_clip=False)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=INK_MUTED, labelsize=9)
    axes[0].legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK)
    axes[1].set_xlabel("Game time (minutes)", color=INK_MUTED, fontsize=9)
    axes[1].annotate(end_label, (end_frame / GAME_SPEED / 60, 0), xytext=(-4, 4), textcoords="offset points",
                     ha="right", va="bottom", fontsize=8, color=INK_MUTED)
    fig.suptitle(f"{stats.get('map', '')}: income over time", x=0.06, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 0.85, 1))  # room on the right for the direct labels
    fig.savefig(out_path, dpi=120, facecolor=SURFACE)
    plt.close(fig)


def report(run_dir, stopped=None):
    """Print winner, value killed / lost and the income plot for a run folder. Returns an exit code."""
    for line in (read_stats(run_dir / "run_settings.json") or {}).get("summary", []):
        print(line)     # STAND-IN: map, opponent, cap, speed, checkpoint, decoding at the top of the report
    stats = read_stats(run_dir / "teamstats.json")
    wall = None
    try:
        times = json.loads((run_dir / "wall.json").read_text())
        wall = times["ended_unix"] - times["started_unix"]
    except (OSError, ValueError, KeyError):
        pass  # runs from before wall.json existed
    print()
    if stats is None:
        print(f"No readable teamstats.json in {run_dir}: the widget never wrote. See console.log.")
        return 1
    teams = {t["team"]: t for t in stats["teams"]}

    def who(team_id):
        info = teams.get(team_id, {})
        # STAND-IN: a NullAI team is shown by the name given to it (OUR_MODEL_...), not as "NullAI".
        name = info.get("ai_name") if info.get("ai") == "NullAI" else info.get("ai")
        return f"team {team_id} ({info.get('side', '?')}, {name or 'player'})"

    status = stats.get("status")
    samples = stats.get("samples", [])
    end_frame = samples[-1]["frame"] if samples else stats.get("written_frame", 0)
    if status == "game_over":
        over = stats["game_over"]
        end_frame, end_label = over["frame"], "game over"
        winners = over["winning_teams"]
        print(f"Result : game over at {clock(over['seconds'])} game time (frame {over['frame']})")
        print("Winner : " + (", ".join(who(t) for t in winners) if winners else "draw (no winning ally team)"))
    elif status == "timeout":
        timeout = stats["timeout"]
        end_frame, end_label = timeout["frame"], "cap"
        print(f"Result : TIMEOUT - no winner by the {clock(timeout['cap_frame'] / GAME_SPEED)} cap "
              f"(frame {timeout['cap_frame']})")
        print("Winner : none")
    else:
        end_label = "engine stopped"
        why = stats.get("error") or ("the engine stopped before GameOver or the cap"
                                     + (f" ({stopped})" if stopped else "") + "; see console.log")
        print(f"Result : INCOMPLETE ({status}): {why}")
        print("Winner : unknown")

    if samples:
        last = samples[-1]
        print(f"\nValue killed / value lost (metal + energy/60) at {clock(last['seconds'])} game time:")
        print(f"  {'':<26}{'killed':>10}{'lost':>10}{'killed/lost':>13}")
        for row in last["teams"]:
            killed, lost = row.get("killedValue") or 0, row.get("lostValue") or 0
            ratio = f"{killed / lost:.2f}" if lost else ("inf" if killed else "-")
            print(f"  {who(row['team']):<26}{killed:>10.0f}{lost:>10.0f}{ratio:>13}")
        png = run_dir / "income.png"
        plot_income(stats, png, end_frame, end_label)
        print(f"\nIncome over time: runs/{run_dir.name}/income.png")
    else:
        print("\nNo samples were written (the game ended before 15 s of game time).")

    if wall is not None:
        # The last sample's frame (the timeout record is written 1 frame before the cap).
        game_seconds = max(end_frame, samples[-1]["frame"] if samples else 0) / GAME_SPEED
        print(f"Wall time: {clock(wall)} for {clock(game_seconds)} of game time, load included")
    return 0 if status in ("game_over", "timeout") else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cap-minutes", type=float, default=20,
                        help="game-time cap; the startscript quits at this frame (default 20)")
    parser.add_argument("--wall-minutes", type=float, default=90,
                        help="wall-clock limit before the container is stopped (default 90)")
    parser.add_argument("--speed", type=float, default=20,
                        help="game speed to ask for, x real time; the server lowers it to what the "
                             "machine keeps up with (default 20, the engine's max; 1 = BAR's normal pacing)")
    parser.add_argument("--swap-sides", action="store_true",
                        help="swap the factions: team 0 plays Cortex and team 1 Armada (same start spots)")
    parser.add_argument("--games", type=int, default=1,
                        help="games to run one after another; with more than one, print team 0's win rate "
                             "over them at the end (see scripts/win_rate.py; default 1)")
    parser.add_argument("--keep-requests", action="store_true",
                        help="STAND-IN: keep policy_requests.jsonl (every observation sent to the policy)")
    parser.add_argument("--record", action="store_true",
                        help="STAND-IN: plain BARb vs BARb with the recorder widget, no policy, no bridge")
    parser.add_argument("--opponent", choices=sorted(OPPONENTS), default="barb",
                        help="STAND-IN: the AI in team 1's slot (default barb: the smoke script unchanged)")
    parser.add_argument("--save-replay", action="store_true",
                        help="STAND-IN: have the engine write a replay and keep it in <run folder>/demos")
    parser.add_argument("--report", metavar="RUN_DIR", type=Path,
                        help="print the report for a finished run folder instead of launching a game")
    args = parser.parse_args()
    if args.report:
        sys.exit(report_to_file(args.report.resolve()))
    if not 0.1 <= args.speed <= 20:
        parser.error("--speed must be between 0.1 and 20 (the engine's MinSpeed/MaxSpeed range)")
    if args.games < 1:
        parser.error("--games must be at least 1")
    codes, run_dirs = [], []  # report exit codes; every run folder made, finished or not
    try:
        for number in range(1, args.games + 1):
            if args.games > 1:
                print(f"\n=== Game {number} of {args.games}", flush=True)
            code, stopped = launch(args.cap_minutes, args.wall_minutes, args.speed, args.swap_sides,
                                   started=run_dirs, keep_requests=args.keep_requests, record=args.record,
                                   save_replay=args.save_replay, opponent=args.opponent)
            codes.append(code)
            if stopped == "stopped by Ctrl+C":
                break
    except KeyboardInterrupt:  # Ctrl+C outside the game's wait loop, e.g. during the image build
        print("\n== Stopped by Ctrl+C")
    finally:  # also before the traceback of any other error (e.g. a failed build), for the games so far
        if args.games > 1:
            summarize(run_dirs, team=0, cap_minutes=args.cap_minutes)
            if len(codes) < args.games:
                print(f"(stopped early: {len(run_dirs)} of {args.games} games started, {len(codes)} reported)")
    # 0 only when every game was reported with a result (GameOver or the cap). With --games 1
    # that is the report's own code, as before --games existed.
    sys.exit(0 if len(codes) == args.games and all(code == 0 for code in codes) else 1)


if __name__ == "__main__":
    main()
