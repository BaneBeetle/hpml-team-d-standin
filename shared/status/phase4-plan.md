# Phase 4 plan: a checkpoint plays team 0 in a bar-harness game (2026-11-17)

Engineering note for Brian. Local test fixture only. Nothing is pushed. bar-harness is read and
copied, never edited. Written before the build; what actually happened is in `team-d.md`.

Outcome (added after the build): built as planned and run for seven games. The first
"not settled" item was settled by the first game: `luarules godmodeally` alone let the
spectator's orders through. Results and numbers: `team-d.md`, section "Phase 4".

## Goal (Brian's words, relayed)

"Prove that we can plug in a model's checkpoint and gather information like economy, team value,
and whatever the old code in bar harness had alongside win rate."

Done means: (1) a checkpoint path is an input and a full game runs with one team controlled by
the policy loaded from it, against BARb; (2) the game writes the same `teamstats.json` and report
a bar-harness game writes today; (3) bar-harness's own `scripts/win_rate.py` runs unchanged on
the run folders.

## Which side moves

The policy side moves to bar-harness's pins: Recoil 2026.09.02, BAR commit 3510e77f, Supreme
Isthmus v2.1, BARb "stable". Reasons, all from the code:

- `win_rate.py`, `run_game.py` and `harness_teamstats.lua` are written for that image and its
  run-folder layout, and the 25-game BARb vs BARb numbers were made with it.
- Roshan's `engine.run_episode` cannot launch a full game: `install_episode` builds his fixture
  mod (`hpml_loop.sdd`), his start script and his fixture gadget, with fixed paths.
- What is reused from Roshan unchanged: `PolicyWorker`, `mailbox.atomic_json`,
  `protocol.validate_request` / `validate_response`, the config budgets, and the request and
  response file names and shapes. From Team C's stand-in: `endpoint_adapter.make_policy` and
  `server.py --policy model --checkpoint PATH`. From Team A: `lua/bar_proof_common.lua`
  (`conservativeView`, the same observation as the fixture loop).

Consequence: the checkpoint was trained on a DATA-01 replay (another BAR version and map).
Its unit def ids and map coordinates may not mean the same thing here. Not checked.

## How the policy takes team 0's slot

Two facts from BAR's code decide this:

1. `luarules/gadgets/api_teamstats.lua`, function `visible`: LuaUI is handed a team's stats only
   if the local client is a full-view spectator, or the team is on the client's own ally team,
   or the game is over. So if the host joined team 0 as a player (Roshan's fixture does that),
   Brian's stats widget would get team 0's rows only, and the timeout reading in `win_rate.py`
   would have nothing to compare. The host therefore stays a spectator, as in bar-harness.
2. A spectator cannot give orders unless god mode is on. BAR's dev helper gadget
   (`luarules/gadgets/cmd_dev_helpers.lua`) has `luarules godmodeally 1`, which calls
   `Spring.SetGodMode(true, nil)` (control of allied teams). It needs cheats to be on at the
   moment it runs. The start script's `debugcommands` modoption can run commands at given frames
   (bar-harness already uses it for `speedcontrol` and `quitforce`).

Plan:
- Team 0: the engine's `NullAI` 0.1 instead of BARb (it is in the image: `AI/Skirmish/NullAI/0.1`).
  It owns the team and gives no orders. Team 1: BARb, unchanged.
- `debugcommands`: `1:cheat 1`, `2:luarules godmodeally 1`, `3:cheat 0`, then bar-harness's own
  `speedcontrol 0` and `<cap>:quitforce`. Cheats are on for two frames only.
- A stand-in LuaUI widget in the spectator client (next to the unchanged stats widget) builds
  the observation for team 0 with `conservativeView` (allied units plus enemies in team 0's line
  of sight), writes Roshan's request envelope, reads the reply and calls `Spring.GiveOrderToUnit`.
- A small Python bridge in WSL reads the requests, sends each through Roshan's `PolicyWorker`
  with `endpoint_adapter.make_policy`, checks the 3 s budget and writes the reply file.
- The model server runs on Windows as in Phase 2 (`--checkpoint PATH`); WSL reaches it at
  `127.0.0.1:8765` (mirrored networking, checked in Phase 2).

Timing mode: `paced` (Roshan's second mode: the game is not paused while a reply is pending).
In Phase 2 the stepped mode ran at about 26 sim frames per wall second (3120 frames in 120 s,
load included), so a 20 minute game would take over 20 minutes of wall time. Paced keeps
bar-harness's speed setting. The pending-frame advance of every reply is recorded.

## Files to add (all under `team-d\standin_eval\fullgame\`)

| File | Origin | Change |
| --- | --- | --- |
| `.env` | copy of bar-harness `.env` | none |
| `widgets/harness_teamstats.lua` | copy | none |
| `scripts/win_rate.py` | copy | none (also the original is run directly on the run folders) |
| `docker-compose.yml` | copy | project name (own cache volume, not bar-harness's), two more read-only mounts (control widget, `bar_proof_common.lua`) |
| `scripts/run_game.py` | copy | start script edits (NullAI, debug commands), writes the widget config, starts and stops the bridge |
| `widgets/standin_control.lua` | new, after Roshan's `control_loop_widget.lua` | file paths inside the widget sandbox, spectator instead of player, no fixture, placeholder catalog |
| `scripts/bridge.py` | new | request file -> `PolicyWorker` -> reply file, policy-side log |
| `run_fullgame.ps1` | new | starts the model server with the checkpoint, runs the game(s) in WSL, stops the server |

Run folders: `fullgame\runs\game_<time>\` (git-ignored), same layout as bar-harness plus the
bridge's policy log. The request stream holds a full observation per decision; it is deleted
after each game unless asked to keep it.

## Order of runs

1. One short capped game with Team C's `--policy scripted` to see whether orders from a
   spectator take effect at all (Roshan's scripted policy moves a unit and builds a solar; the
   widget fills the catalog from team 0's first unit). This separates "control works" from
   "the weak model does something".
2. One 20 minute capped game with `--policy model --checkpoint shared\ckpt\b03-h1\h1_best.pt`.
3. A small batch of model games, then `win_rate.py` (the original file) on the run folders.
   A batch over about an hour of wall time needs Brian's OK first.

## Not settled before building

- Whether `godmodeally` lets a spectator's orders through on this engine. If not: try
  `luarules godmode 1` as well; if that fails too, stop and report.
- Whether BAR treats a NullAI team like any AI team (commander spawn, game end rules).
- Reading the growing request file over the `/mnt/c` mount failed once in Phase 2 with
  `OSError 61`. The bridge reopens the file for every read and treats a failed read as
  "nothing new yet". The `PolicyWorker` mailbox goes to a temporary folder on the Linux side.
- What the game does when the policy fails mid-game. Rule kept from Roshan's contract: no retry,
  no substitute action. The bridge stops answering, the game runs on to its cap with team 0 idle,
  and the policy status is recorded next to the game result.
- A game with two frames of cheats and god mode is not the same setup as the 25 BARb vs BARb
  games. Whether Brian and Jon accept it for EVAL-03 is their call.
- Observation size late in the game and its cost at 20x speed. Measured in the first game.
