#!/usr/bin/env python3
"""STAND-IN: write the unit type table (number -> name) of the game version Team A's data uses.

Run inside Roshan's EVAL-01 image, which has that pinned engine and game:

    docker run --rm --mount type=bind,source=<bar-standins>/team-d,target=/work \
        --mount type=volume,source=hpml-eval01-runtime,target=/work/runtime \
        --mount type=bind,source=<bar-standins>/shared/data,target=/out \
        hpml-eval01:local python3 standin_eval/standin_model/dump_unit_defs.py /out/data05_unit_defs.json

It sets up one episode folder with Roshan's own install_episode, switches his control widget
off, adds unit_defs_dump.lua, and starts the engine. The widget writes the table and quits.
Why: a build order is "minus the unit type number", and that number is different in the game
version bar-harness runs. With both tables a number can be translated through the unit's name.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/work")
GAME = "Beyond All Reason test-31368-8379d65"    # the game Roshan's wrapper game depends on
sys.path.insert(0, str(ROOT / "scripts"))
from control_loop.engine import install_episode     # Roshan's code, unchanged


def main():
    out_path = Path(sys.argv[1])
    runtime = ROOT / "runtime" / "control_loop"       # where prepare_control_loop_runtime.py put the pins
    directory = Path(tempfile.mkdtemp(dir=ROOT / "runtime" / "output")) / "episode"
    install_episode(runtime, directory, {"seed": 1})
    shutil.copy2(Path(__file__).with_name("unit_defs_dump.lua"), directory / "LuaUI" / "Widgets")
    # Order 0 = widget off, 1 = on (BAR's widget list).
    (directory / "LuaUI" / "Config" / "BYAR.lua").write_text(
        "return {allowUserWidgets=true,order={['HPML Control Loop']=0,['STAND-IN unit defs']=1},data={}}\n")
    command = [str(runtime / "engine" / "spring-headless"), "--write-dir", str(directory),
               "--isolation-dir", str(directory), "--only-local", str(directory / "startscript.txt")]
    with (directory / "engine.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)

    lines = (directory / "unit_defs.txt").read_text().splitlines()
    table = {number: name for number, name in (line.split() for line in lines[1:])}
    out_path.write_text(json.dumps({"source": "standin", "game": GAME, "unit_defs": table}, indent=0))
    print(f"{GAME}: {len(table)} unit types -> {out_path}")
    shutil.rmtree(directory.parent)


if __name__ == "__main__":
    main()
