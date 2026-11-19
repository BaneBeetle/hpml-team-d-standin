# Stand-in model plan: train on BARb's own orders in our own games (2026-11-17)

Engineering note for Brian. Local test fixture only: the checkpoint is a stand-in, tagged as
such, never presented as Team B's work. Nothing touches the team's GitHub. Written before the
build; what actually happened goes into `team-d.md`.

## Goal (Brian's words, relayed)

"Im not sure if the other teams have access to GPUs. Lets train our own model for now."

Done means: a checkpoint trained locally that goes in through the same `-Checkpoint` path of
`run_fullgame.ps1`, and whose orders in a full game are varied (several command types, several
recipients). Winning is not required.

## Why the existing checkpoints give one order (from Team B's README and the data)

`b03-h1` and `standin-d128` were trained on 256 orders of one match on Great Divide V1 with BAR
test-31368. Our games run on Supreme Isthmus v2.1 with BAR 3510e77f. In every game played so
far every order was command -506 to one recipient.

## Checked before planning (one 3 minute BARb vs BARb game, `runs\record_20261117_134002`)

- A spectator widget's `UnitCommand` callback does see the AIs' orders, for both teams, with
  params and the coded options: 452 orders in 3 minutes of game time, 211 written (one per team
  per 15-frame window that had orders).
- All 211 carried `from_synced = true`, `from_lua = false`, `player_id = 0`.
- Command ids seen: 10 (82 rows), 2 (28), 50 (18), 85 (14), 45 (12), 135 (11), 40 (8), builds
  with 13 different negative ids (29 rows), and a few others.
- The recipient was in the recorded observation in 199 of 211 rows (in the other 12 the unit
  appeared after the observation was taken).
- Average row: 6.9 KB (early game; the observation is most of it).

## Approach

1. Record. `run_game.py --record` (in the stand-in copy) runs bar-harness's plain BARb vs BARb
   game with one more widget, `widgets\standin_recorder.lua`. Every 15 frames it takes each
   team's observation with `conservativeView`, the same call the control widget makes when a
   policy plays. Of the orders that team's units get before the next observation it keeps one,
   chosen at random, and writes one row: observation plus order. One order per window because
   every row repeats the full observation.
2. Convert. `standin_model\make_pairs.py` turns the recorded rows into the DATA-01 pair format
   that Team B's `b03_report.py` reads (`state`, `view_team`, `state_frame`, `action` with
   `command_id`, `command_name`, `unit_ids`, `params`, `options`, `pairwise`, `frame`). Command
   names come from Team A's table (`scripts/parse_bar_demo.py`, `NAMES`). It caps the rows taken
   per game so the file stays loadable, and labels every row of a game with that game's split.
3. Split by whole games: each recorded game is train, val or test as a whole.
4. Train with Team B's code. `standin_model\train_standin.py` imports `scripts/b03_report.py`
   and calls its `train` command. Two things in that script are fixed in code and cannot be set
   from the command line, so the wrapper replaces them at run time without editing the file:
   `DATA["map"]` (it says Great Divide V1) and `split_of` (minute within one match).
   Model, loss, optimizer and checkpoint format stay Team B's.
5. Play. `run_fullgame.ps1 -Checkpoint <new>` as before. The server must be told the map name
   the model was trained with (`--map-name`), so the wrapper gets a `-MapName` parameter.
6. Decode step. Team B's `predict_orders` already has `sample=True`. If greedy decoding still
   gives one order, a small stand-in server start-up file passes `sample=True`; Team C's and
   Team B's files stay as they are.

Order of work: a first small pass (3 recorded games, one checkpoint, one full game), then more
recorded games, a second training run, and several full games.

## Files to add

| File | What |
| --- | --- |
| `fullgame\widgets\standin_recorder.lua` | the recorder widget (new) |
| `fullgame\scripts\run_game.py` | `--record` option in the existing stand-in copy |
| `fullgame\docker-compose.yml` | one more read-only mount for the recorder |
| `fullgame\widgets\standin_control.lua` | removes itself when the run has no `control_config.json` |
| `standin_eval\standin_model\make_pairs.py` | recorded rows -> DATA-01 pairs, split by game (new) |
| `standin_eval\standin_model\train_standin.py` | calls Team B's `b03_report.py train` with the map and split replaced (new) |
| `fullgame\run_fullgame.ps1` | `-MapName`, and `-Sample` if step 6 is needed |
| `shared\data\standin-barb\` | the pairs file and its manifest |
| `shared\ckpt\<name>\` | checkpoint, Team B's `train.json`, `manifest.json` |

## Not settled before building

- Which of BARb's commands Team B's action encoder accepts. Their code skips queue edits
  (command ids 1 and 2) and some parameter shapes; the script prints the skipped counts.
- Unit cap: Team B's default keeps 128 units per observation, own units first. Late-game
  observations may hold more. Checked on the recorded data before choosing `--cap`.
- GPU: `b03_report.py` turns on `torch.use_deterministic_algorithms`, which on CUDA needs the
  `CUBLAS_WORKSPACE_CONFIG` environment variable. If the GPU run fails, CPU is used and noted.
- Whether orders copied from BARb do anything useful when given at a 15-frame tick by a model
  that sees one snapshot. Recorded as counts; not judged.
- Recorded orders include state settings (fire state, move state, on/off) and BARb's own queue
  removals. They are recorded as given; nothing is filtered by hand.
