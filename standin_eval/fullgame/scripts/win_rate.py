#!/usr/bin/env python3
"""Win rate over finished games: of the games played, how many one team won.

    python3 scripts/win_rate.py                          # every runs/game_* with a 20 min cap, for team 0
    python3 scripts/win_rate.py --team 1                 # the same games, for team 1
    python3 scripts/win_rate.py runs/game_A runs/game_B  # just these runs

"We" is one team slot, team 0 by default: the slot a model will play later (for now both
teams are BARb). A game is won when the team is among the GameOver winners in teamstats.json.
A loss, a draw and a timeout (no winner by the cap) are all not won, so the win rate is
wins / games. Left out, and listed: runs that ended any other way (crash, wall-clock limit,
Ctrl+C), which have no result, and games with a different cap, since a 2 min game is not
comparable with a 20 min one. A folder given twice counts once. For timeouts it also shows
which side (the team's ally team, totals over its teams) was ahead on value killed / value
lost at the cap: a reading of the stats, not a result. The speed column is the speed the
startscript asked for; the engine runs slower when the machine cannot keep up.
Standard library only, so it runs with any Python 3.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
GAME_SPEED = 30  # frames per second of game time


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def killed_lost(killed, lost):
    """Value killed / value lost, inf when nothing was lost but something was killed, None for 0/0."""
    if lost:
        return killed / lost
    return math.inf if killed else None


def read_game(run_dir, team):
    """(game, None) for a run with a result, or (None, why it has none)."""
    # UTF-8 whatever the platform: BAR writes non-ASCII names (a map's, say) as raw UTF-8.
    try:
        stats = json.loads((run_dir / "teamstats.json").read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None, "no readable teamstats.json"
    teams = {t["team"]: t for t in stats.get("teams", [])}
    if team not in teams:
        return None, f"has no team {team}"
    try:
        script = (run_dir / "startscript.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        script = ""
    cap_frame = stats.get("cap_frame")
    if cap_frame is None:
        match = re.search(r"\b(\d+):quitforce", script)
        cap_frame = int(match[1]) if match else None
    match = re.search(r"^\s*minspeed=([\d.]+);", script, re.M)
    game = {
        "run": run_dir.name,
        "cap_frame": cap_frame,
        "speed": f"{float(match[1]):g}x" if match else "1x (default)",
        "side": teams[team].get("side", "?"),
        "ahead": None,
    }
    status = stats.get("status")
    if status == "game_over":
        over = stats["game_over"]
        winners = over.get("winning_teams") or []
        game["end"] = over["seconds"]
        game["result"] = "won" if team in winners else ("lost" if winners else "draw")
    elif status == "timeout":
        game["end"] = stats["timeout"]["cap_frame"] / GAME_SPEED
        game["result"] = "timeout"
        samples = stats.get("samples") or []
        if samples:
            # Side against side: each ally team's killed and lost summed over its teams, so in a
            # 2v2 both teams of a side get the same reading. The best enemy side, if several.
            totals = {}
            for row in samples[-1]["teams"]:
                ally = teams.get(row["team"], {}).get("ally_team", f"team {row['team']}")
                killed, lost = totals.get(ally, (0, 0))
                totals[ally] = (killed + (row.get("killedValue") or 0), lost + (row.get("lostValue") or 0))
            our_ally = teams[team].get("ally_team", f"team {team}")
            ours = killed_lost(*totals[our_ally]) if our_ally in totals else None
            theirs = [r for r in (killed_lost(*kl) for ally, kl in totals.items() if ally != our_ally)
                      if r is not None]
            if ours is not None and theirs:
                best = max(theirs)
                game["ours"], game["theirs"] = ours, best
                game["ahead"] = "ahead" if ours > best else ("behind" if ours < best else "even")
    else:
        return None, f"incomplete ({status}): no result"
    return game, None


def wilson(wins, games, z=1.96):
    """95% Wilson score interval for a win rate: honest about how little a handful of games says."""
    if games == 0:
        return 0.0, 1.0
    p = wins / games
    denom = 1 + z * z / games
    centre = (p + z * z / (2 * games)) / denom
    half = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def ratio_text(value):
    return "inf" if value == math.inf else f"{value:.2f}"


def summarize(run_dirs, team=0, cap_minutes=20.0):
    """Print the games, the left-out runs and the win rate. Returns (wins, games)."""
    cap_frame = None if cap_minutes is None else round(cap_minutes * 60 * GAME_SPEED)
    games, left_out, seen = [], [], set()
    for run_dir in run_dirs:
        key = Path(run_dir).resolve()
        if key in seen:  # the same folder twice, e.g. from overlapping globs
            continue
        seen.add(key)
        game, why = read_game(Path(run_dir), team)
        if game and cap_frame is not None and game["cap_frame"] != cap_frame:
            have = clock(game["cap_frame"] / GAME_SPEED) if game["cap_frame"] else "none"
            game, why = None, f"cap {have}, not {clock(cap_frame / GAME_SPEED)}"
        if game:
            games.append(game)
        else:
            left_out.append((Path(run_dir).name, why))

    cap_text = f"a {clock(cap_frame / GAME_SPEED)} game-time cap" if cap_frame is not None else "any cap"
    print(f"\nGames with {cap_text}, from team {team}'s side:")
    if games:
        side_head = f"team {team}"
        print(f"  {'run':<30}{'speed asked':<14}{side_head:<9}{'result':<19}"
              f"killed/lost at the cap (team {team}'s side vs the other)")
        for g in games:
            result = f"{g['result']} at {clock(g['end'])}"
            cap_note = ""
            if g["ahead"]:
                cap_note = f"{ratio_text(g['ours'])} vs {ratio_text(g['theirs'])}  {g['ahead']}"
            print(f"  {g['run']:<30}{g['speed']:<14}{g['side']:<9}{result:<19}{cap_note}".rstrip())
    else:
        print("  none")
    if left_out:
        print("Left out:")
        for name, why in left_out:
            print(f"  {name:<30}{why}")

    count = {r: sum(g["result"] == r for g in games) for r in ("won", "lost", "draw", "timeout")}
    total, wins = len(games), count["won"]
    print(f"\nTeam {team}: won {wins}, lost {count['lost']}, draw {count['draw']}, timeout {count['timeout']}"
          f" (of {total} game{'s' if total != 1 else ''})")
    if total:
        low, high = wilson(wins, total)
        print(f"Win rate: {wins}/{total} = {wins / total:.0%}  (95% interval {low:.0%}-{high:.0%});"
              f" a loss, draw or timeout counts as not won")
        sides = sorted({g["side"] for g in games})
        if len(sides) > 1:
            print("By faction: " + "; ".join(
                f"as {s} {sum(g['result'] == 'won' for g in games if g['side'] == s)}"
                f"/{sum(g['side'] == s for g in games)} won" for s in sides))
        timeouts = [g for g in games if g["result"] == "timeout"]
        if timeouts:
            read = [g for g in timeouts if g["ahead"]]
            ahead = sum(g["ahead"] == "ahead" for g in read)
            unread = len(timeouts) - len(read)
            if read:
                print(f"Timeouts with team {team}'s side ahead on killed/lost at the cap: {ahead} of {len(read)}"
                      + (f" ({unread} more with nothing killed or lost to compare)" if unread else "")
                      + " - a reading of the stats, not a win")
            else:
                print("Timeouts: nothing killed or lost in any of them, so no side was ahead on killed/lost")
    return wins, total


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("runs", nargs="*", type=Path,
                        help="run folders (default: every runs/game_* folder)")
    parser.add_argument("--team", type=int, default=0,
                        help="the team whose wins are counted (default 0, the slot a model will play)")
    parser.add_argument("--cap-minutes", type=float, default=20,
                        help="only count games with this game-time cap (default 20; 0 = any cap)")
    args = parser.parse_args()
    run_dirs = args.runs or sorted(p for p in (HARNESS / "runs").glob("game_*") if p.is_dir())
    _, total = summarize(run_dirs, args.team, args.cap_minutes or None)
    sys.exit(0 if total else 1)


if __name__ == "__main__":
    main()
