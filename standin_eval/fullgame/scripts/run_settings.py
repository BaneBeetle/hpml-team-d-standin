#!/usr/bin/env python3
"""STAND-IN: write run_settings.json, one plain file per run folder saying what was played.

    python scripts/run_settings.py runs/game_A runs/record_B ...     # (re)write for these folders

run_game.py calls write() before and after every game. Every value is read from files of that
run: startscript.txt, control_config.json, record_config.json, policy_info.json, and after the
game teamstats.json and console.log. Only the engine version and BAR commit come from .env
(the pins run_game.py checks before it starts a game). Nothing is typed in by hand.
It is for sharing the settings of a run or a replay. Local test fixture.
"""

import argparse
import json
from pathlib import Path
import re
import shutil

FULLGAME = Path(__file__).resolve().parents[1]


def block(text, name):
    """The inside of one [NAME] { ... } block of a start script ('' when there is none).
    Blocks directly inside [GAME] close with a tab and a brace on their own line."""
    match = re.search(r"\[" + name + r"\]\s*\{(.*?)\n\t\}", text, re.S | re.I)
    return match[1] if match else ""


def value(text, key):
    """The value of `key=...;` in a piece of a start script, or None."""
    match = re.search(rf"^\s*{key}\s*=\s*(.*?);", text, re.M | re.I)
    return match[1] if match else None


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, ValueError):
        return None


def build(run_dir):
    script = (run_dir / "startscript.txt").read_text(encoding="utf-8", errors="replace")
    control = read_json(run_dir / "control_config.json")    # only a policy game has it
    policy = read_json(run_dir / "policy_info.json") or {}
    stats = read_json(run_dir / "teamstats.json") or {}     # written by the game; absent before it
    pins = dict(line.split("=", 1) for line in (FULLGAME / ".env").read_text().splitlines()
                if "=" in line and not line.startswith("#"))
    try:
        log = (run_dir / "console.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        log = ""
    options = block(script, "MODOPTIONS")
    cap = re.search(r"(\d+):quitforce", value(options, "debugcommands") or "")
    cap_frame = int(cap[1]) if cap else None

    teams = []
    for number in (0, 1):
        team = block(script, f"TEAM{number}")
        ai = next((b for b in (block(script, f"AI{n}") for n in (0, 1)) if value(b, "Team") == str(number)), "")
        row = {"team": number, "side": value(team, "Side"), "ally_team": value(team, "AllyTeam"),
               "ai_short_name": value(ai, "ShortName"), "ai_name": value(ai, "Name"),
               "ai_version": value(ai, "Version"), "ai_profile": value(ai, "profile")}
        if control and number == control["control_team"]:
            row["controlled_by"] = ("the policy (see \"policy\"), giving orders from the spectator host; "
                                    "the team's AI entry gives no orders")
        else:
            row["controlled_by"] = f"AI {row['ai_short_name']}"
        if row["ai_short_name"] == "BARb" and row["ai_profile"] is None:
            # Where the default comes from: engine AI/Skirmish/BARb/stable/AIOptions.lua, key
            # "profile", def = 'hard'. The engine log names the profile it loaded (below).
            row["ai_profile_note"] = "not set in the start script; BARb's AIOptions.lua default is 'hard'"
        teams.append(row)

    differences = ["the host player is a spectator (as in bar-harness)"]
    if control:
        differences += ["team %d's orders come from a policy through a spectator widget" % control["control_team"],
                        "debug commands in the start script: " + (value(options, "debugcommands") or ""),
                        "ally god mode is on from the 'luarules godmodeally' command to the end of the game"]
    settings = {
        "source": "standin",
        "summary": [],                                    # filled in below
        "run_folder": run_dir.name,
        "kind": "policy game" if control else "recording run (AI vs AI, no policy)",
        "map": value(script, "MapName"),
        "engine_version_pin": pins.get("ENGINE_VERSION"),
        "game_type_in_start_script": value(script, "GameType"),
        "bar_commit_pin": pins.get("BAR_COMMIT"),
        "start_pos_type": value(script, "StartPosType"),
        "fixed_rng_seed": value(script, "FixedRNGSeed"),
        "record_demo": value(script, "RecordDemo"),
        "game_time_cap_frame": cap_frame,
        "game_time_cap_minutes": cap_frame / 1800 if cap_frame else None,
        "speed_asked": value(options, "minspeed"),
        "sides_swapped": run_dir.name.endswith("_swapped"),
        "deathmode": value(options, "deathmode"),
        "teams": teams,
        "policy": None,
        "differences_from_a_normal_match": differences,
        # What the game itself reported, once it has run.
        "reported_by_the_game": {key: stats.get(key) for key in ("map", "game", "engine", "status")},
        "engine_log": {
            "barb_profiles_named": sorted(set(re.findall(r"Skirmish AI <[^>]*>: CONFIG (\w+):", log))),
            "cheat_and_god_mode_lines": re.findall(
                r"\[f=(\d+)\] (Cheating is enabled!|Cheating is disabled!|Ally godmode: \w+)", log)},
        "replay_files": sorted(p.name for p in (run_dir / "demos").glob("*.sdfz")) if (run_dir / "demos").is_dir() else [],
    }
    if control:
        settings["policy"] = {
            "policy": policy.get("policy"), "checkpoint": policy.get("checkpoint"),
            "checkpoint_sha256": policy.get("checkpoint_sha256"),
            "decoding": "sampled" if policy.get("sampled") else "greedy",
            "sampling_seed": policy.get("sampling_seed"),
            "map_name_given_to_model": policy.get("map_name_given_to_model"),
            # Only set when run_fullgame.ps1 was given another server / the placement switch.
            "server_script": policy.get("server_script"), "temperature": policy.get("temperature"),
            "server_environment": policy.get("server_environment"),
            "widget_places_builds": bool(policy.get("place_builds")),
            "decision_interval_frames": control["decision_interval_frames"],
            "policy_time_budget_seconds": control["policy_timeout_seconds"],
            "timing_mode": control["timing_mode"], "first_decision_frame": control["first_frame"]}
    settings["summary"] = [
        f"map: {settings['map']}   engine: {settings['engine_version_pin']}   BAR commit: {settings['bar_commit_pin']}",
        " vs ".join(f"team {t['team']} ({t['side']}): " + ("policy" if "policy" in t["controlled_by"] else
                    f"{t['ai_short_name']} {t['ai_version']}"
                    + (f" profile {t['ai_profile']}" if t["ai_profile"] else "")
                    + (" (profile not set; BARb default 'hard')" if "ai_profile_note" in t else ""))
                    for t in teams),
        f"cap: {settings['game_time_cap_minutes']:g} min game time   speed asked: {settings['speed_asked']}x"
        f"   sides swapped: {settings['sides_swapped']}   start positions: StartPosType={settings['start_pos_type']}",
    ]
    if control:
        p = settings["policy"]
        settings["summary"].append(
            f"policy: {p['policy']}   checkpoint: {p['checkpoint']}   decoding: {p['decoding']}"
            + (f" (seed {p['sampling_seed']})" if policy.get("sampled") else "")
            + f"   one decision per {p['decision_interval_frames']} frames, {p['timing_mode']}")
        settings["summary"].append("not a normal match: " + "; ".join(differences[1:]))
    return settings


def write(run_dir):
    """Write run_settings.json into the run folder, and a copy beside every replay file."""
    settings = build(run_dir)
    target = run_dir / "run_settings.json"
    target.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    for name in settings["replay_files"]:
        shutil.copyfile(target, run_dir / "demos" / (name + ".settings.json"))
    return settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    for folder in parser.parse_args().folders:
        print(folder.name, *write(folder.resolve())["summary"], sep="\n  ")
