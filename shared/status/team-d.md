# Team D stand-in integrator: status

Last update: 2026-11-17, opponent option done and its games played. Also done: save-replay
option, run_settings.json, stand-in model. Everything here is a local test fixture.
Nothing was pushed or posted.

## Unit policy: our own model for the overnight improvement loop (starting session, 2026-11-18)

Brian asked (2026-11-18) to dig into the training, improve the checkpoint and keep a
train / eval loop going overnight. Everything below is local, tagged stand-in, never pushed.

What was found in Team B's B03 model (read, not changed), relevant to playing a game:
- It picks the order type first from a pooled state, then the units. The type is not tied
  to what the receiving unit can do.
- A position is one cell of a fixed grid over absolute map coordinates
  (`ActionSpec.grid`, 128-elmo cells), chosen from the pooled state.
- The training pairs only exist at moments a player gave an order; nothing says "wait".
- The earlier stand-in run used 2,676 train orders because the loader keeps every row's
  state as JSON in memory. Team A's 20 matches hold 346,020 order rows.

What the unit policy does instead (code in `team-d/standin_eval/unit_policy/`):
- One example = (state, one unit that received an order, the order). The model answers
  "this unit is idle: what order does it get?".
- Positions are predicted as an offset from that unit (23 classes east-west, 23 north-south).
- In a game the server picks one idle own unit per decision (longest-waiting first), and
  the order type is chosen among the types that unit type received in the training data.
- Never chosen in a game: WAIT, self-destruct, BAR custom commands (numbers 30000 and up,
  not checked across game versions).
- With `-PlaceBuilds` the widget moves a build order to the nearest place it can be built
  (an extractor: nearest free metal spot from BAR's own list; other buildings:
  `Spring.ClosestBuildPos` within 512 elmos). `run_settings.json` records it
  (`widget_places_builds`), plus `server_script` and `temperature`.

Files:
| File | What it is |
|---|---|
| `unit_policy/common.py` | state -> arrays (`featurize`), offset classes, order type keys |
| `unit_policy/build_dataset.py` | Team A's restored matches -> `shared/data/unit-v1/*.npz` |
| `unit_policy/model.py` | the model (unit vectors, 2 transformer layers, one head per order field) |
| `unit_policy/train.py` | training; picks the step with the lowest validation loss |
| `unit_policy/unit_server.py` | policy endpoint (reuses the Team C stand-in's HTTP code) |
| `unit_policy/evaluate.py` | plays a fixed set of games, appends to `shared/status/unit_policy_results.jsonl` |
| `fullgame/widgets/standin_control.lua` | `place()` added |
| `fullgame/scripts/bridge.py` | `own_units_at_last_decision` added to `policy_summary.json` |
| `fullgame/scripts/run_game.py`, `run_settings.py`, `run_fullgame.ps1` | `-PolicyServer`, `-Temperature`, `-PlaceBuilds` |

Dataset `unit-v1` (cap 15,000 examples per match, at most 3 units per group order):
train 112,055 examples / 31,231 states; validation 33,010 / 8,032; test 16,219 / 4,043.
Skipped: 56,999 rows with an order form Team B's `arg_form` does not support, 1,505 with
the target not in the state, 88 with the unit not in the state.

Runs and numbers: see "Unit policy runs" below this section as they are added, and
`shared/status/unit_policy_results.jsonl` (one line per game).

### Version 2 of the unit policy (same day)

What version 1's validation numbers showed (run `unit-v1a`, 6,000 steps): the validation
loss was lowest at step 500 (11.25) and rose to 14.47 by step 6,000 while the training loss
kept falling. On validation, a building's east-west offset loss was 3.71 (always guessing
the training frequencies gives 3.12), a building's type was right 33.6% of the time, and a
factory's type 0%.

What changed in version 2 (`common.py`, `build_dataset.py`, `model.py`, `train.py`, `unit_server.py`):
- Reference point of a position: the end of the unit's queue when the order is appended
  with shift and the queue has a position, otherwise the unit itself. (`append` is also a
  model input.)
- No map coordinates in the input. Every unit's position enters only relative to the
  reference point. Training mirrors states at random (east-west, north-south) as extra data.
- `prior`: a fixed table of log frequencies [unit type, order type] from the training
  matches, added to the type scores. Step 0 of a training log = this table alone.
- WAIT, self-destruct and custom commands are left out of the dataset (before, only out of
  the game). Cap 40,000 examples per match. Dropout 0.2, weight decay 0.05.
- In a game a unit can hold up to `STANDIN_QUEUE_DEPTH` (default 3) orders: a unit with a
  shorter queue that has a position gets its next order appended (shift on).
- `server.py` was renamed `unit_server.py` (the old name hid Team C's `server` module).

Dataset `unit-v2`: train 148,139 examples / 28,192 states; validation 54,416 / 7,916;
test 15,493 / 3,633. Skipped: 38,721 unsupported form, 75,482 left-out commands, 1,013
target not in the state, 99 unit not in the state.

`unit-v1a`'s saved file is in the version 1 format; the current code cannot load it.

### Unit policy runs (2026-11-18)

Per-game numbers are in `shared/status/unit_policy_results.jsonl`; every run folder has its
`run_settings.json`. All games: Supreme Isthmus v2.1, team 0 Armada = the checkpoint, widget
build placement on, sampled at temperature 1, queue depth 3.

What went wrong first:
- The first `unit-v2a` training run was started at 03:48 and did not finish its first
  validation measurement until 15:38. The process held about 20 GB of GPU memory while
  other programs used the same GPU. The cause of the stall was not confirmed. No training
  happened in that time.
- Changed after that in `train.py`: `--gpu-gb` (default 10, the run fails instead of
  taking more), bfloat16 inside the model, the curve is measured on a fixed sample of
  16,000 validation examples (`--eval-examples`) and the selected step once more on all of
  them (`validation_all` in `train.json`), and the checkpoint is selected on `play`
  (type + target + dx + dz) instead of the sum of all heads. In the stalled run the facing
  head's validation loss went 1.38 -> 3.38 in 750 steps while type accuracy rose.
- Every background job now runs under `timeout`.

`unit-v2a` (data `unit-v2`, 4,000 steps, 453 s): selected step 2250. Validation sample:
type accuracy 0.852 (step 0, the prior alone: 0.654), build type accuracy 0.601 (0.626),
build dx / dz loss 3.15 / 2.95 (3.44 / 3.58), target loss 0.119 (5.903).

Games with `unit-v2a` (`evaluate.py --name unit-v2a`), last stats sample of each:

| Run | Opponent, cap | Seed | Result | Metal / energy income | Killed / lost value | Finished units | Orders | Policy status |
|---|---|---|---|---|---|---|---|---|
| `game_20261118_155507` | null, 10 min | 1 | cap | 11.3 / 210.4 | 0 / 20 | 46 (2 armlab, 11 armpw, 10 armjeth, 10 armrectr, 5 armham) | 409 | answered until stopped |
| `game_20261118_155653` | null, 10 min | 2 | cap | 7.6 / 107.0 | 0 / 0 | 8 | 13 | `policy_timeout` |
| `game_20261118_155812` | simple, 20 min | 1 | lost at 19:17 | 0 / 0 | 5020 / 5938 | 10 | 43 | `policy_timeout` at frame 8310 |
| `game_20261118_160012` | simple, 20 min | 2 | lost at 07:03 | 0 / 9.5 | 1740 / 4600 | 0 | 33 | answered until stopped |
| `game_20261118_160134` | barb-easy, 20 min | 1 | lost at 04:37 | 0 / 0 | 0 / 5710 | 0 | 147 | answered until stopped |

- The two `policy_timeout` games are not usable as results: one predict call was not
  answered within the 3 s budget, the bridge stopped asking (the rule kept from Roshan's
  contract) and team 0 was idle from then on. Both timeouts fell in the minutes when this
  session started other jobs on the machine (a dataset conversion with 3 worker processes,
  scripts loading the dataset; free memory was about 6 GB). Not confirmed as the cause.
  The server now runs the model on 2 threads (`torch.set_num_threads(2)`).
- `game_20261118_160134`: at 2:00 the model gave an own armpw the order ATTACK with the
  own commander as target (trace: command 20, params [25947]). Team 0's lost value went
  from 207 to 5710 in one sample at 4:37 while team 1's killed value stayed 207.
- For comparison, `unit-v1a` (version 1, step 500) vs null, 10 min, seed 1
  (`game_20261118_033*`): 6.6 / 99.3 income, 14 finished units (1 armap, 5 armpeep), 21 orders.

Changed after these games:
- `target_sides` (made in `train.py`, saved in the checkpoint, used by `unit_server.py`):
  for every order type that points at a unit, whether its training targets included own
  units and whether they included other units (a side needs 2% of the type's examples).
  In a game a targeted order only gets a target on a side that counts, never the unit
  itself, and is not offered when the state has no such unit.
- `evaluate.py --set NAME=VALUE` passes server settings (`STANDIN_QUEUE_DEPTH`, ...);
  `run_settings.json` lists them under `policy.server_environment`.

`unit-v2b` (same data and settings as `unit-v2a`, plus `target_sides`; the model now has the
`place_in` layer, which changes the random start and the validation sample): selected step
2000, validation sample: type accuracy 0.836, build type accuracy 0.598, build dx / dz loss
3.21 / 2.94, target loss 0.125. Its `target_sides`: GUARD, REPAIR, LOAD_UNITS own units only;
ATTACK, MANUAL_FIRE other units only; RECLAIM both.

Games with `unit-v2b` (`evaluate.py --name unit-v2b`). They were played while BARb
recording games ran on the same machine:

| Run | Opponent, cap | Seed | Result | Metal / energy income | Killed / lost value | Finished units | Orders | Policy status |
|---|---|---|---|---|---|---|---|---|
| `game_20261118_161146` | null, 10 min | 1 | cap | 5.3 / 89.0 | 0 / 0 | 8 | 12 | answered until stopped |
| `game_20261118_161410` | null, 10 min | 2 | cap | 25.8 / 140.7 | 0 / 0 | 28 (2 armlab, 6 armmex) | 59 | `policy_timeout` at frame 13395 |
| `game_20261118_161612` | simple, 20 min | 1 | lost at 13:19 | 0 / 0 | 2618 / 7216 | 0 | 222 | answered until stopped |
| `game_20261118_161945` | simple, 20 min | 2 | lost at 09:40 | 0 / 0 | 1045 / 6081 | 0 | 241 | answered until stopped |
| `game_20261118_162204` | barb-easy, 20 min | 1 | lost at 11:25 | 0 / 0 | 2947 / 4080 | 0 | 27 | answered until stopped |

- Policy timeouts so far: 3 of the 10 games above (frames 17310 of 18000, 8310, 13395).
  In each, the 12 replies before the failed call took 14 to 62 ms. `unit_server.py` now
  writes one line per predict call to `unit_policy/server_requests.log` (start time,
  decision, duration); `run_benchmark.py` copies it into the run folder.
- `game_20261118_161146` (12 orders): at 1:27 the commander got GUARD (command 25) on an
  own unit, appended to its queue; two builds were appended after it; from 1:58 to 10:00
  no unit could get an order. `game_20261118_155653` (`unit-v2a`, 13 orders) was not
  looked at the same way. Changed in `unit_server.py` after this (the last game of the
  table above, `game_20261118_162204`, already ran with it): a unit with GUARD or PATROL
  in its queue gets nothing appended, and can get a new order that replaces its queue 900
  frames after our last order to it (`ENDLESS`, `ENDLESS_FRAMES`).

What the human matches hold for the early game (`unit-v2` train split): 1,877 of 148,139
examples are orders to a commander (590 in the first 3 minutes). 12 of 54,193 validation
examples are "build a factory" orders; `unit-v2a` puts a mean probability of 0.012 on the
recorded type there.

### EVAL-03 pilot, local (2026-11-18)

Brian asked for it after a read of issue 11 (EVAL-03; on GitHub: no comment, branch or PR).
Nothing was posted. Code in `team-d/standin_eval/benchmark/`:

| File | What it is |
|---|---|
| `pilot_suite.json` | the pinned game list `pilot-v1`: Supreme Isthmus v2.1, the policy as Armada on team 0, 3 games vs SimpleAI and 3 vs BARb easy, 20 minute cap, replay saved, widget build placement on |
| `run_benchmark.py` | plays the list with one policy (`--policy scripted`, `--checkpoint <unit policy>`, `--policy builtin-barb`), one row per game in `shared/status/benchmark/pilot-v1/<label>.jsonl`; a second run plays only the games without a row; a game that could not be played gets a `runner_error` row |
| `make_table.py` | rows -> `shared/status/benchmark/pilot-v1/table.md` (every game; per policy and opponent; time) |

Played 16:25 to 16:53, one game at a time, no other job of this session running except
drawing charts: `scripted` (Roshan's scripted policy through Team C's stand-in server) and
`unit-v2b` (sampled, temperature 1, the repeat number as sampling seed).

| Policy | Opponent | Games | Won | Lost | No winner by the cap | Policy stopped early |
|---|---|---|---|---|---|---|
| scripted | simple | 3 | 0 | 3 | 0 | 3 (`policy_error`) |
| scripted | barb-easy | 3 | 0 | 1 | 2 | 1 (`policy_error`) |
| unit-v2b | simple | 3 | 0 | 2 | 1 | 1 (`policy_timeout`) |
| unit-v2b | barb-easy | 3 | 0 | 1 | 2 | 1 (`policy_timeout`) |

- Time: 12 games, wall time per game 57 to 197 s (mean 130 s), 27.7 games per hour one
  at a time (server start and image check before each game not counted), 163 minutes of
  game time. Resource use was not measured.
- The scripted policy gives 2 orders per game. Its `policy_error` is "ProtocolError:
  Controlled attacker is missing", raised once its unit is gone.
- `unit-v2b` per game: orders 130, 130, 20, 48, 135, 28; no-order share 0.84 to 0.99.
- The two `policy_timeout` games: `game_20261118_163855` (decision 816, frame 14010) and
  `game_20261118_164759`. In the first, `server_requests.log` ends with decision 815
  ("took 0.000 s") and has no line for 816, while the bridge's summary counts the request
  as seen: the request did not reach `predict` in the server. The worker opens a new
  connection from WSL to 127.0.0.1:8765 on Windows for every request
  (`shared/endpoint_adapter.py`, WSL `networkingMode=mirrored`). Where the 3 seconds went
  is not confirmed.
- `--policy builtin-barb` (added after these 12 games): the built-in BARb AI in team 0's
  slot on the same list, as a reference with no policy numbers (a `run_game.py --record`
  run with `--opponent` and `--save-replay`).

Added to the pilot later the same day (rows in `shared/status/benchmark/pilot-v1/`):

| Policy | Opponent | Games | Won | Lost | No winner by the cap | Policy stopped early |
|---|---|---|---|---|---|---|
| builtin-barb (BARb default profile on team 0, `run_game.py --record`) | simple | 3 | 1 (12:24) | 0 | 2 | - |
| builtin-barb | barb-easy | 3 | 1 (13:23) | 0 | 2 | - |
| standin-human-v1 (`--policy b03`: Team C's stand-in server, sampled, map name given) | simple | 3 | 0 | 0 | 3 | 0 |
| standin-human-v1 | barb-easy | 3 | 0 | 0 | 3 | 1 (`policy_timeout`) |

- `standin-human-v1` per game: 617 to 2,091 orders, 0.785 to 0.837 of them without an engine
  callback, 1 finished unit at the last decision, max metal income 2 (2.4 in one game),
  lost value 0, killed value 1,290 / 5,665 / 1,003 vs simple and 0 vs barb-easy.
- The `policy_timeout` in `game_20261118_173424` happened with Team C's stand-in server, so
  the timeout is not specific to `unit_server.py`.
- Two tests of the timeout, both without a stall: 18,752 POSTs with a 10 kB body from WSL to
  a dummy HTTP server on Windows over 7 minutes (max 0.195 s), while recording games ran;
  63,054 recorded predict requests replayed from Windows against `unit_server.py` with
  `unit-v2b` over 7 minutes (the first call took 2.05 s, no other above 0.5 s). In the two
  pilot games with a timeout and a server log, the last logged call was a model call 0.1
  to 0.2 s before, and the failed decision has no line. Since then `unit_server.py` also
  writes a line when a request arrives, and `run_benchmark.py` keeps the requests of
  unit-policy games (`-KeepRequests`). Cause still not known.
- Replay screenshots: `shared/status/slides_2026-11-18/hpml_replay_shots.lua` (a widget that
  in a replay takes three screenshots every 2 game minutes and quits at game over) and
  `take_replay_shots.ps1` (plays one replay in the Windows BAR install in a 1600x900 window
  with a copy of `springsettings.cfg`, copies the widget in and removes it after). The
  replay file stays in the install's `demos` folder. Taken: `replay_unit-v2b_barb-easy-2`
  and `replay_first-model_simple-2` (27 images each).
- `unit-barb-v1` (`build_dataset_barb.py`, all 24 complete recordings, only teams played by
  BARb with its default profile): 104,892 train examples, 22,941 validation (the two
  recordings `record_20261118_170357`, `_170640`). `unit-barb-v1a` (`--map-position`,
  8,000 steps, 392 s): validation type accuracy 0.74 to 0.79 in the second half of the run
  (prior alone 0.680), build type accuracy 0.16 (0.111), target loss 0.85 (4.87).
  Check game `game_20261118_174502` (null, 4 min): 29 orders, 3 armmex finished, metal
  income 10.9, energy income 30.

`unit-barb-v1a` on the pilot list (17:46 to 17:57): simple 0 won / 2 lost / 1 cap, barb-easy
0 / 2 / 1; orders per game 1, 128, 173, 224, 239, 58; max metal income 4.3 to 17.5, max
energy income 30 to 106 (`unit-v2b`: 171 to 560).

- Its first game, `game_20261118_174612`, is a `policy_timeout` at decision 2 (frame 165).
  `server_requests.log` has "decision 1 arrived" and "decision 1 ... took 0.072 s" and no
  line at all for decision 2; the bridge counts 3 requests seen. So the request left the
  bridge and did not reach `predict` in the server.
- Changed after that: `shared/endpoint_adapter.py` gives a request up to three tries, each
  on a new connection; the first two give up after 1 s, the last keeps the 5 s timeout, so
  a request that keeps failing is still a `policy_timeout` at 3 s. Each failed try is one
  line in the run's `bridge.log`; `run_benchmark.py` counts them (`adapter_failed_tries`).
  `unit_server.py` answers a repeated decision id with the reply it already gave. Rows
  made before this change have no `adapter_failed_tries`.

`unit-v2b` on the pilot list at lower sampling temperatures (17:59 to 18:30, with the adapter's
retry in place):

| Temperature | Won / lost / cap | Policy stopped early | Failed tries that were retried | Orders per game | Max metal income per game |
|---|---|---|---|---|---|
| 1.0 (the rows above, before the retry) | 0 / 3 / 3 | 2 | not counted | 130, 130, 20, 48, 135, 28 | 10.9, 12.9, 4.3, 13.0, 30.0, 6.1 |
| 0.7 | 0 / 4 / 2 | 0 | 2 (both in one game) | 35, 549, 20, 237, 62, 82 | 11.6, 69.4, 11.2, 19.7, 12.9, 26.1 |
| 0.4 | 0 / 5 / 1 | 0 | 1 | 12, 36, 38, 1097, 1724, 86 | 2, 9.6, 9.0, 14.3, 36.6, 12.3 |

- In these 12 games a try got no answer within 1 s three times; each time a later try on a
  new connection was answered and the game went on (`policy_status` answered until stopped
  in all 12). Before the retry: 5 `policy_timeout` in 16 unit-policy games.
- From the kept requests of `game_20261118_174832` (`unit-barb-v1a`, simple-3): a build order
  decided on the observation of frame 105 was not in the commander's observed queue at
  frames 120 and 135 and was there at 150. `COOLDOWN` was 45 frames, so the same unit was
  picked again while its queue still looked empty and got an order that replaced the first
  (options without the shift bit). `COOLDOWN` is now 90. `unit-v2b-cd90` = `unit-v2b` on the
  pilot list with that change (played while the recording below was running).
- `unit-v2b-cd90` on the pilot list (18:38 to 18:54): simple 0 won / 2 lost / 1 cap, barb-easy
  0 / 0 / 3; no policy stop, 1 retried try; orders per game 44, 65, 602, 1155, 113, 73; max
  metal income 8.6, 8.3, 61.8, 23.7, 25.8, 26.5; finished units at the last decision 0, 0,
  14, 107, 17, 14.
- In `game_20261118_184113` (`unit-v2b-cd90`, barb-easy-1, 107 units at the cap, value killed
  364): armham got 440 orders (354 MOVE, 84 FIGHT), armpw 409 (395 MOVE), with a median
  distance of 560 to 700 elmos per order; team 0's front-line stat stayed between 0 and 9.
  `unit-v2b` has no map position as input (its data is 20 matches on other maps).
- `unit-barb-v1a-cd90` on the pilot list (18:56 to 19:14): 0 won / 5 lost / 1 cap; orders 34,
  103, 194, 200, 131, 80; max metal income 11.2 to 30.9, max energy income 30 to 107; no
  policy stop, 8 retried tries (6 in one game). Team 0's front-line stat was 0 in five of
  the six games (builtin-barb: 52 to 81 at its highest).
- `unit-barb-v1` train split by acting unit: armcom 1,512 examples (MOVE 0.30, REPAIR 0.19,
  armmex 0.12, GUARD 0.08, armwin 0.07), armck 1,248, armlab 101, armpw 4,719 (MOVE 0.84).
- `unit-barb-v1b` (`unit-barb-v1`, `--d 192 --layers 3`, 12,000 steps, 1,305 s while games
  ran): selected step 7000; all validation examples: type accuracy 0.859, build type
  accuracy 0.141, target loss 0.954 (`unit-barb-v1a`: 0.786, 0.151, 0.843).
- 19:07: `builtin-barb` started on `pilot_suite_cap40.json` (the same six games, 40 minute
  cap; rows in `shared/status/benchmark/pilot-v1-cap40/`), asked by Brian's question
  whether to extend the cap.
- Probe of the two BARb-data checkpoints (a made-up state: one armpw with an own commander,
  lab and two armpw near it, 300 sampled orders per place, temperature 1). Mean offset of
  its MOVE / FIGHT orders: `unit-barb-v1b` at team 0's base (7600, 4900): dx -210, dz +214;
  at (6100, 6100): -147, +143; at (4500, 7500): +13, +91. `unit-barb-v1a`: -124, -17;
  +23, -122; +187, -192. (The other start spot is to the lower left of team 0's.)
- `unit_server.py`: `STANDIN_ARMY_CHECKPOINT` names a second `unit_policy.pt`. Then the main
  checkpoint orders the unit types that build (builders, factories) and the second one
  every other unit type it knows; unit types are matched by name between the two
  checkpoints' `unit_defs.json` tables. `glue_rules_fired` counts its orders with
  `_army`. `run_benchmark.py` rows now carry `server_environment`. Label
  `unit-v2b+army-barb-v1b` = `unit-v2b` with `unit-barb-v1b` as the army checkpoint.
- 19:15 to 19:58, too many jobs at once (recording, the 40 minute reference, a pilot and a
  probe): up to four game containers, WSL load average 49, Windows free memory 538 MB.
  Effects: `unit-barb-v1b-cd90` (0 won / 3 lost / 2 cap, one `runner_error`: no `report.txt`
  for `game_20261118_194721`; 13 retried tries in one game; wall time 290 to 449 s per
  game); the 40 minute reference's fourth game hit the runner's 900 s limit
  (`runner_error`); two `wsl` starts failed with `Wsl/Service/WSAETIMEDOUT`. Those two
  `unit-v2b+army-barb-v1b` rows (both `runner_error`, no game played) were removed and the
  run restarted at 19:59 with only the recording beside it. The runner's limit per game is
  now 600 s + 30 s per cap minute. Rule from here on: one pilot at a time, at most one
  recording beside it.
- `builtin-barb` with a 40 minute cap, the three games that finished (vs simple): won at
  20:10, 21:08 and 10:51 (value killed / lost 12,934 / 7,440, 20,666 / 6,263, 7,512 /
  1,994). With the 20 minute cap the same pairing gave 1 win in 3. The barb-easy games of
  that list were not played (stopped at 19:58).
- The recording started at 18:31 ended at its 100 minute limit (20:11) with 17 complete
  20 minute games instead of 24 (one more was running and was stopped). BARb (default, team
  0) in those 17: vs simple 10 won, 2 no winner by the cap; vs barb-easy 4 won, 1 no winner.
  Together with the six `builtin-barb` pilot rows (1 won + 2 cap vs each): simple 11 of 15
  won, barb-easy 5 of 8 won, 16 of 23 in all inside the 20 minute cap. The six pilot rows
  alone gave 2 of 6.
- `unit-v2b+army-barb-v1b` on the pilot list (19:59 to 20:15, the recording beside it until
  20:11): 0 won / 5 lost / 1 cap; orders 398, 977, 31, 49, 65, 41; value killed 4,758,
  5,344, 0, 830, 2,075, 850; value lost 7,217, 8,223, 801, 5,392, 6,148, 5,170; max metal
  income 7.6 to 17.2; no policy stop, 4 retried tries. (`unit-v2b-cd90` alone: 0 / 2 / 4.)
- 20:16: started `build_dataset_barb.py --name unit-barb-v2` (every complete recording),
  then `unit-barb-v2a` (`--map-position --d 192 --layers 3`, 12,000 steps), then its pilot,
  one after the other with nothing else running.
- The first `unit-barb-v2` build stopped on a recording with an unfinished line
  (`JSONDecodeError`); the chain went on, so training and six pilot starts failed with no
  game played (those six `runner_error` rows were removed). `build_dataset_barb.py` now
  skips and counts such lines ("unreadable line": 20 in this build), and the chain runs a
  step only when the one before worked.
- `unit-barb-v2`: 44 recordings, 296,228 examples (252,590 train, 35,106 validation).
  `unit-barb-v2a` (`--map-position --d 192 --layers 3`, 12,000 steps, 1,160 s): validation
  type accuracy 0.896, build type accuracy 0.15, target loss 0.73. Pilot (20:37 to 20:48,
  alone on the machine): 0 won / 4 lost / 2 cap; orders 100, 78, 307, 166, 726, 703; max
  metal income 8.9 to 22.7, max energy income 88 to 216; value killed 0 to 1,747.
- 20:49: `easier_suite.json` (`easier-v1`: the idle opponent three times, simple-constructor
  and simple-defender once each, 20 minute cap) with `unit-v2b` plus `unit-barb-v2a` as the
  army checkpoint, then with `unit-v2b` alone. Not part of the pilot's comparison.
- 18:31: started recording 24 more games of BARb (default profile, team 0, Armada) against
  simple (12) and barb-easy (12), the pilot's seat and opponents, for `unit-barb-v2`.

### BARb-recorded data for the unit policy (2026-11-18)

- `widgets/standin_recorder.lua` now also writes `actions`: the first 64 orders of the
  window per team (before: one order per window, still written as `action`).
- `unit_policy/build_dataset_barb.py`: `runs/record_*/recorded_orders.jsonl` -> the same
  array layout as `build_dataset.py`. A unit gives at most one example per window (its
  first order). BARb's factory orders have 3 parameters (a position, no facing);
  `common.type_of` reads them as the same type as a player's factory order (in
  `record_20261117_135315` every 3-parameter build order went to a factory: 21 of 21).
- The dataset folder gets `unit_defs.json` (this game version's table, from the newest
  `game_*` run folder) and `train.py` copies it into the checkpoint folder.
- `train.py --map-position`: the reference point's map coordinates / 4096 as one more
  input (`place_in` in `model.py`), mirror augmentation off. For data from one map played
  on that map. Checkpoints without it get exactly zero from that input.
- `unit-barb-v0`: the 15 recordings of 2026-11-17 (one order per window): 33,207 train
  examples (11 games), 6,108 validation (2), test 2 games. `unit-barb-v0a` (3,000 steps,
  `--map-position`): validation type accuracy 0.79 (prior alone 0.694), build type
  accuracy 0.18 (0.129). Not played in a game.

## Why standin-human-v1's build orders produced no buildings (starting session, 2026-11-18)

Checked with one extra game: `runs/game_20261118_030059`, same settings as
`game_20261117_221252` (SimpleAI, sampled seed 1, Supreme Isthmus v2.1) but 4 minutes and
`-KeepRequests`, so every observation is kept in `policy_requests.jsonl`. The observation
has the commander's position and its order queue at each decision. No code was changed.

Counts from that game (336 decisions, 334 orders, all to the commander, team 0 is Armada):

| Order | Count | Seen in the commander's queue within 3 decisions |
|---|---|---|
| not a build order | 198 | not counted |
| build a Cortex unit, with a position | 57 | 0 |
| build a Cortex unit, no position | 27 | 0 |
| build an Armada unit, no position | 12 | 0 |
| build another unit (hats), with a position | 2 | 0 |
| build an Armada unit, with a position | 38 | 8 (armllt 3, armwin 3, armsolar 1, armmakr 1) |

- The 8 that reached the queue had build sites 1,017 / 1,350 / 3,637 / 4,114 / 5,646 /
  5,899 / 7,200 / 7,393 elmos from the commander (the commander moved about 19 elmos per
  decision in this game).
- A build order was somewhere in the queue at 17 of 336 decisions, and first in the queue
  at 4. The first entry was a move order at nearly every other decision.
- 78 orders had options 0 and 131 had options 16: neither has the "queue behind" bit (32),
  so each of them replaces the queue.
- Team 0's last observation: metal expense 0, energy expense 0 (nothing was being built).
- For comparison, the scripted policy's game (`game_20261117_215116`) gave one build order
  (armsolar, 96 elmos from the commander, options 0) and no order after it: team 0's energy
  income went from 30 to 50 by frame 900. So the order path does build.

Not checked: which of the 30 Armada orders with a position that never showed in the queue
were refused by the game and which were replaced before the next observation; the full
20-minute games (their requests were not kept); custom command numbers across the two game
versions (the data game's files in Roshan's volume are in the engine's hashed pool format).

Also: removed my leftover `/work/runtime/output/tmp9q0er04r` from the `hpml-eval01-runtime`
Docker volume (created by the first failed run of `dump_unit_defs.py`).

## Checkpoint trained on Team A's human matches: standin-human-v1 (starting session, 2026-11-17)

Task from Brian: "Yes, try it" (train our model on Team A's 20-match release, pushed to
`origin/team-a` on 2026-11-17, commit 10fd4b8). Made by the session that started this one.
Local only; nothing pushed or posted. The checkpoint is a stand-in fixture, not Team B's work.

Steps and files:

- `C:\Users\lolly\bar-standins\team-a-data`: a second local checkout of `origin/team-a` made with
  `core.autocrlf=false`. In the main clone Git rewrote line endings and Team A's restore script
  then failed its own hash check ("Publication manifest hash mismatch"). Nothing edited there.
- Restore: Team A's `scripts/restore_data05.py`, all 20 matches verified, 5.2 GB in
  `shared\data\data05-native\`.
- `standin_model\make_pairs_data05.py` (new): Team A's pair rows hold `state_ref`
  `[view_team, state_frame]` instead of the state. The script reads the states with Team A's
  `state_stream.iter_states` and writes rows in the DATA-01 layout Team B's script reads, with
  three labels added to `action`: `split`, `game`, `map`. Sample: 300 order packets per match
  (seeded). With 1,000 per match the file was 3.7 GB; Team B's loader keeps every row's state
  in memory. Output `shared\data\data05-native-v1\` (1.29 GB; rows train 8,203, val 1,976, test 1,113).
- `standin_model\train_standin.py` (16 lines added): for data from several maps the map
  vocabulary is the train maps (12) and each order is encoded with its own match's map;
  `--unit-defs` copies the data's unit type table next to the checkpoint.
- Training: Team B's `b03_report.py train`, unchanged; command in
  `shared\ckpt\standin-human-v1\manifest.json`. Orders the script used: train 2,676, val 454,
  test 580 (the rest merged or skipped; counts in `train.json` under `skipped`). Selected step
  100 (first measurement): val TF total 19.656, type acc 0.289. Frequency baseline on the same
  val orders: 22.568, 0.187. Val total at step 3000: higher than at step 100 (curve in `train.json`).
- Unit type numbers: the data is on game `test-31368-8379d65`, bar-harness runs BAR commit
  3510e77. The same unit has a different number in each (corwin 506 vs 511, armcom 52 vs 56).
  - `standin_model\dump_unit_defs.py` + `unit_defs_dump.lua` (new): dump the data version's
    table from the engine in Roshan's image (587 unit types) to `shared\data\data05_unit_defs.json`.
  - `fullgame\widgets\standin_control.lua` (6 lines added): writes this game's table to
    `unit_defs.json` in every run folder (593 unit types).
  - `fullgame\scripts\bridge.py` (about 70 lines added): if the checkpoint folder has
    `unit_defs.json`, unit numbers are rewritten by name: observation `defID` and queued build
    ids before the policy, a build order's command id before the game. 585 names are in both
    tables. Counts go to `policy_summary.json` under `unit_type_translation`. Checkpoints
    without the file behave as before.
  - Side finding: command -506 from the DATA-01 checkpoints is "build corwin" in the data's
    version; in the harness version 506 is another unit.

Games (Supreme Isthmus v2.1, 20 min cap, `-SaveReplay`, model given the map name
"Supreme Isthmus v2.1"; settings of each run in its `run_settings.json`):

| Run | Opponent | Decoding | Result | Team 0 killed / lost | Orders | Command ids | Build orders |
| --- | --- | --- | --- | --- | --- | --- | --- |
| game_20261117_220147 | barb-easy | greedy | timeout | 0 / 0 | 2,135 | 2 | 0 |
| game_20261117_220451 | barb-easy | sampled, seed 1 | lost at 15:07 | 0 / 3,133 | 1,542 | 108 | 607 |
| game_20261117_220714 | barb-easy | sampled, seed 2 | timeout | 0 / 0 | 1,920 | 111 | 601 |
| game_20261117_220942 | simple | greedy | timeout | 1,720 / 0 | 2,036 | 2 | 0 |
| game_20261117_221252 | simple | sampled, seed 1 | timeout | 1,147 / 0 | 2,077 | 111 | 702 |
| game_20261117_221531 | simple | sampled, seed 2 | timeout | 1,483 / 0 | 1,829 | 105 | 662 |

- bar-harness's unchanged `win_rate.py --cap-minutes 20`: won 0, lost 1, timeout 5 of 6.
- In all six games every order went to one unit, and team 0's last stats sample (in the five
  games it survived) shows metal income 2, energy income 30, metal spots 0. No build order
  without a name match (0 in every game). Greedy games used two command ids: 34924
  (`UNIT_CANCEL_TARGET` in BAR's customcmds) and 10 (move).
- Also: `game_20261117_215116` (scripted, 1 min) and `game_20261117_220043` (model, 3 min) were
  check runs for the widget and bridge changes.
- Not checked: why build orders produced no buildings; whether custom command numbers
  (34924, 34571, ...) are the same in both game versions; games on another map or opponent.

## Policy team name: OUR_MODEL_<checkpoint> (changed by the starting session, 2026-11-17)

Task from Brian: "Can we make our model a more obvious name so we know what bot is ours."
Made by the session that started this one, not by the Team D session (commit bd0731e, local).

- `fullgame\scripts\run_game.py`, 14 lines added, 2 removed:
  - `policy_team_name()` (new): reads `policy_info.json` and returns `OUR_MODEL_` plus the
    checkpoint's folder name (for example `OUR_MODEL_standin-barb-v1`), or `OUR_MODEL_<policy>`
    for the scripted and noop policies. Characters other than letters, digits, `_ . -` become `_`.
  - `make_startscript`: team 0's `[AI0] Name=` is that name instead of `StandInPolicy`.
    `ShortName=NullAI` is unchanged (it has to be a real AI).
  - `report`: a NullAI team is labelled by its name, so the report says
    `team 0 (armada, OUR_MODEL_standin-barb-v1)` instead of `team 0 (armada, NullAI)`.
- Checked with one 3 minute game, `runs\game_20261117_162329` (sampled, vs barb-easy,
  `-SaveReplay`): `startscript.txt` has `Name=OUR_MODEL_standin-barb-v1;`, `teamstats.json` has
  `ai_name` `OUR_MODEL_standin-barb-v1` (its `ai` is still `NullAI`), `run_settings.json` lists the
  name, and bar-harness's unchanged `win_rate.py` reads the run.
- Not checked: how the name is drawn in the game window. Runs made before this change keep
  `StandInPolicy` in their start scripts and replays.

## Opponent option: done (easier bots in team 1's slot)

Task from Brian, relayed: "have these go against the easier bots rather than the barbarian ones
first".

What can sit in team 1's slot on the pinned engine and BAR checkout (read from the files):

| `-Opponent` | Start script entry | Where it is defined |
| --- | --- | --- |
| `barb` (default, every earlier run) | `ShortName=BARb; Version=stable;`, no profile set | engine `AI/Skirmish/BARb/stable/`; its `AIOptions.lua` has `key = 'profile'`, `def = 'hard'`; the engine log of the games says "CONFIG hard" |
| `barb-easy`, `barb-medium`, `barb-hard-aggressive` | the same plus `[Options] { profile=easy; }` (or `medium`, `hard_aggressive`) inside `[AI1]` | BAR `luarules/configs/BARb/stable/config/` and `.../script/`, folders `easy`, `medium`, `hard`, `hard_aggressive` |
| `simple`, `simple-defender`, `simple-constructor` | `ShortName=SimpleAI;` (or `SimpleDefenderAI`, `SimpleConstructorAI`) `Version=<not-versioned>;` | BAR `luaai.lua` (all three listed with `desc = "EasyAI"`) and `luarules/gadgets/ai_simpleai.lua`; written the way `singleplayer/scenarios/scenario002.lua` writes it |
| `null` | `ShortName=NullAI; Version=0.1;` | engine `AI/Skirmish/NullAI/0.1` (gives no orders) |

Also in `luaai.lua` but not offered: `ScavengersAI` and `RaptorsAI` (other game modes).
`ai_simpleai.lua` also recognises a `SimpleCheaterAI` name that `luaai.lua` does not list.

Option: `run_fullgame.ps1 -Opponent <name>`, passed on as `run_game.py --opponent`. With the
default the start script is byte-identical to an earlier run's. The opponent used is in the run
folder three ways: `startscript.txt`, `policy_info.json` (`"opponent"`), and `run_settings.json`
(team 1's AI name, version, profile, plus the profile the engine log named).
Checked in the games below: with `barb-easy` the engine log names profile `easy`; with `simple`
`teamstats.json` and the report show team 1 as `SimpleAI`.

Games (policy on team 0, 20 minute cap, speed 20x asked, one run each; `-SaveReplay` on the
sampled ones; `b03-h1` was given the server's default map name as in its earlier games):

| Run folder | Opponent | Checkpoint, decoding | Result | Team 0 killed / lost | Team 1 killed / lost | Order replies / submitted | Command ids | Distinct recipients | Policy status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `game_20261117_144919` | barb-easy | standin-barb-v1, greedy | timeout at 20:00 | 0 / 0 | 0 / 10 | 2084 / 2083 | 2 (-162: 1865, 135: 219) | 2 | answered until stopped |
| `game_20261117_145233` | barb-easy | standin-barb-v1, sampled (seed 0) | lost at 16:50 | 402 / 3789 | 3714 / 402 | 1749 / 1744 | 40 | 16 | answered until stopped |
| `game_20261117_145557` | barb-easy | standin-barb-v1, sampled (same server run) | lost at 15:03 | 748 / 3488 | 3133 / 748 | 1497 / 1495 | 42 | 12 | answered until stopped |
| `game_20261117_145812` | barb-easy | b03-h1, greedy | timeout at 20:00 | 0 / 0 | 0 / 1 | 2093 / 2092 | 1 (-506) | 1 | answered until stopped |
| `game_20261117_150052` | simple | standin-barb-v1, greedy | lost at 07:25 | 527 / 3192 | 3133 / 527 | 654 / 654 | 2 (-162: 544, 135: 110) | 2 | answered until stopped |
| `game_20261117_150221` | simple | standin-barb-v1, sampled (seed 0) | lost at 05:18 | 1584 / 3390 | 3133 / 1584 | 436 / 435 | 27 | 6 | answered until stopped |
| `game_20261117_150324` | simple | standin-barb-v1, sampled (same server run) | lost at 04:23 | 790 / 3390 | 3133 / 790 | 389 / 387 | 26 | 5 | answered until stopped |
| `game_20261117_150425` | simple | b03-h1, greedy | lost at 04:04 | 287 / 3133 | 3133 / 287 | 332 / 332 | 1 (-506) | 1 | answered until stopped |

bar-harness's own `win_rate.py` (original file, unchanged), per group:

    barb-easy, standin-barb-v1:  Team 0: won 0, lost 2, draw 0, timeout 1 (of 3 games)   Win rate: 0/3 = 0%  (95% interval 0%-56%)
    barb-easy, b03-h1:           Team 0: won 0, lost 0, draw 0, timeout 1 (of 1 game)    Win rate: 0/1 = 0%  (95% interval 0%-79%)
    simple, standin-barb-v1:     Team 0: won 0, lost 3, draw 0, timeout 0 (of 3 games)   Win rate: 0/3 = 0%  (95% interval 0%-56%)
    simple, b03-h1:              Team 0: won 0, lost 1, draw 0, timeout 0 (of 1 game)    Win rate: 0/1 = 0%  (95% interval 0%-79%)

For the two timeouts it printed "nothing killed or lost in any of them, so no side was ahead".

- Round trip p50 23 to 31 ms and p95 33 to 66 ms in these eight games; no failed call.
- Replays of the four sampled games are in their `demos\` folders (49,579 to 185,176 bytes),
  each with its `.settings.json`.
- Does anything assume the opponent is BARb? `win_rate.py`: no code does; one docstring line
  says "for now both teams are BARb". `harness_teamstats.lua`: no; it reads each team's AI name
  from the engine. `run_game.py` (original): only texts (docstring, the "Running BARb vs BARb"
  line) and the name of BAR's smoke start script it starts from.
- Not run: `barb-medium`, `barb-hard-aggressive`, `simple-defender`, `simple-constructor`, `null`.
  Their start script edits were only dry-run for `null`.

Changed for this (committed locally): `fullgame\scripts\run_game.py` (the `OPPONENTS` table,
`--opponent`, up to four more start script edits on `[AI1]`, the opponent written into the run's
`policy_info.json`, the opponent's name in the "Running" line) and `fullgame\run_fullgame.ps1`
(`-Opponent`, with the same list of names).

## Save-replay option: done. Opening it in Brian's BAR install: untested

Option: `run_fullgame.ps1 -SaveReplay` (off by default), passed on as `run_game.py --save-replay`.
- It changes `RecordDemo=0` to `RecordDemo=1` in the start script and adds a second compose
  file, `docker-compose.replay.yml`, that mounts `<run folder>\demos` at `/bar/demos`, where the
  engine writes the replay. The replay therefore stays in `runs\<run>\demos\`.
- With the option off nothing changes: the start script built with defaults is byte-identical to
  an earlier run's (`game_20261117_142256`), and the docker command is the one used before.

One game with it: `runs\game_20261117_143503` (`standin-barb-v1`, sampled, vs BARb; game over at
frame 16308, winner team 1).
- Replay file: `demos\2026-11-17_19-35-08-007_Supreme Isthmus v2.1_2026.09.02.sdfz`, 113,666 bytes
  (the engine log says 398,063 bytes before compression). Beside it:
  `...sdfz.settings.json`, a copy of the run's `run_settings.json`.
- Played back once in the harness's own Linux image, headless (same engine and game checkout):
  the log has "Opening demofile" and "Beginning demo playback", runs to frame 16668 (the
  original game-over frame 16308 plus 360) and has no line containing "desync". Playback ran at
  about game speed (frame 8872 after 5.5 minutes). The check was ended by its own time limit
  while the engine was already shutting down.

In Brian's Windows BAR install (`C:\Users\lolly\AppData\Local\Programs\Beyond-All-Reason`):
**not opened, not tried.** Read-only look: `data\engine` has only `recoil_2026.07.04`;
`data\games` is empty; `data\maps` has `supreme_isthmus_v2.1.sd7`. The replay names engine
2026.09.02 and game "Beyond All Reason $VERSION" (the source checkout at 3510e77f).
Nothing in that install was changed. Steps he would have to do himself (untested):
1. Engine: Recoil release 2026.09.02, Windows 64-bit archive, from the RecoilEngine releases
   page on GitHub (bar-harness's `.env` uses the Linux file of the same release,
   `recoil_2026.09.02_amd64-linux.7z`; the Windows file's exact name was not checked).
   Extract it so that `spring.exe` is in `...\Beyond-All-Reason\data\engine\recoil_2026.09.02\`.
2. Game: the Beyond-All-Reason repository at commit `3510e77f98a4d1408de64e73e5656f3ebd7a13eb`
   as the folder `...\data\games\BAR.sdd\`. Either copy the checkout bar-harness already has in
   WSL (`\\wsl$\Ubuntu-24.04\home\lolly\bar-data\Beyond-All-Reason`), or
   `git clone https://github.com/beyond-all-reason/Beyond-All-Reason.git BAR.sdd` and
   `git checkout 3510e77f98a4d1408de64e73e5656f3ebd7a13eb` (the URL `setup_bar.sh` uses).
3. Map: already there.
4. Copy the `.sdfz` (and its `.settings.json`) into `...\data\demos\`.
5. Start it with that engine: `...\data\engine\recoil_2026.09.02\spring.exe --isolation
   --write-dir "<...>\data" "<...>\data\demos\<file>.sdfz"`. Whether the BAR launcher's own
   replay list shows and opens it was not checked.

What the replay shows for team 0, so it is no surprise:
- Team 0's AI entry is "StandInPolicy" / NullAI 0.1. It gives no orders. The policy's orders
  were given by the host (the spectator "SmokeRunner") under ally god mode, so in the replay
  they are that player's orders to team 0's units.
- Console lines near the start: "Cheating is enabled!" (frame 31), "Ally godmode: enabled"
  (frame 37), "Cheating is disabled!" (frame 49), from the start script's debug commands.
- BAR's dev helper runs the start script's debug commands on every client, also on the one
  watching a replay: the playback log shows "Executing debugcommand, cheat 0" at frame 20.
  The list ends with `36000:quitforce`, so a replay of a game that reached the cap would close
  the viewer at frame 36000 (from the gadget's code; not tried).
- Team 1 is the opponent AI as in a normal game.

## run_settings.json: one file per run folder saying what was played

Brian's requirement, relayed: map, bot difficulty and other settings must travel with a run or
replay. `fullgame\scripts\run_settings.py` writes `run_settings.json` into every run folder
(before the game, and again after it with what the game reported), a copy beside every replay
file (`<replay>.settings.json`), and `run_game.py` prints its "summary" lines at the top of
`report.txt`. All 35 existing run folders got the file too (`python scripts\run_settings.py runs\...`);
their old `report.txt` files were not rewritten.

Values are read from the run's own files: `startscript.txt` (map, game type, start position
type, RNG seed, RecordDemo, cap frame, speed, death mode, each team's side and AI name, short
name, version and profile), `control_config.json` (decision interval, time budget, timing mode),
`policy_info.json` (policy, checkpoint, sha256, greedy or sampled, seed, map name given to the
model, opponent), and after the game `teamstats.json` (map, game, engine, status as the game
reported them) and `console.log` (which BARb profile the engine loaded, at which frames cheats
and god mode switched). Only the engine version and BAR commit come from the copied `.env` pins.

Example summary lines (`game_20261117_143503`):

    map: Supreme Isthmus v2.1   engine: 2026.09.02   BAR commit: 3510e77f98a4d1408de64e73e5656f3ebd7a13eb
    team 0 (Armada): policy vs team 1 (Cortex): BARb stable (profile not set; BARb default 'hard')
    cap: 20 min game time   speed asked: 20x   sides swapped: False   start positions: StartPosType=0
    policy: model   checkpoint: ...\shared\ckpt\standin-barb-v1\h1_best.pt   decoding: sampled   one decision per 15 frames, paced
    not a normal match: team 0's orders come from a policy through a spectator widget; debug commands ...; ally god mode is on ...

BARb's difficulty in every run so far: the start script sets no profile. The default is `hard`:
the engine-side `AI/Skirmish/BARb/stable/AIOptions.lua` has `key = 'profile'`, `def = 'hard'`,
and the engine log of the games names it ("Skirmish AI <BARbarIAn-stable>: CONFIG hard").
`run_settings.json` records both (`ai_profile_note` and `engine_log.barb_profiles_named`).
The sampling seed is recorded from now on (`-SampleSeed`, default 0); earlier sampled games used
seed 0, fixed in the code at that time, and show `sampling_seed: null`.
This file is for Brian to share himself; nothing was posted anywhere.

## Stand-in model: done (trained on BARb's orders in our own games)

Task from Brian, relayed: "Lets train our own model for now". Plan written first:
`standin-model-plan.md`. The checkpoint is a stand-in fixture, not Team B's work.

Checkpoint: `shared\ckpt\standin-barb-v1\h1_best.pt` (+ `train.json` from Team B's script,
`manifest.json`). It goes in through the same path:

    .\run_fullgame.ps1 -Checkpoint C:\Users\lolly\bar-standins\shared\ckpt\standin-barb-v1\h1_best.pt -MapName "Supreme Isthmus v2.1" -Sample -Games 3

Recording (plain BARb vs BARb on bar-harness's pins, `run_game.py --record`, no policy, no god mode):
- Check first (one 3 minute game): a spectator widget's `UnitCommand` does see the AIs' orders
  for both teams with params and coded options (452 orders seen, 211 rows written).
- 15 games of 20 minutes game time (9 normal, 6 with `--swap-sides`), 14 ended at the cap and
  1 by game over at 19:36. Wall time 1:58 to 2:34 per game.
- The widget saw 544,390 orders in the 15 games and wrote 60,170 rows: one order per team per
  15-frame window, chosen at random among that window's orders, with the team's observation
  from the start of the window (`conservativeView`, the call the control widget makes).
- Recorded files: 2.8 GB in `fullgame\runs\record_*\recorded_orders.jsonl` (git-ignored).

Data set `shared\data\standin-barb-v1\` (`make_pairs.py`, DATA-01 pair format, manifest beside it):
- 1,200 rows per game picked at random: 18,000 rows, 661.7 MB, sha256 `a70382b7...`.
- Split by whole game: 11 games train (13,200 rows), 2 val (2,400: `record_20261117_135911`,
  `record_20261117_141148_swapped`), 2 test (2,400: `record_20261117_140320`,
  `record_20261117_141618_swapped`). The test split was not used.
- Rows by command name: MOVE 8810, REMOVE 2386, FIGHT 1274, WAIT 1165, FIRE_STATE 621,
  MOVE_STATE 609, builds (all unit defs) 602, REPAIR 593, ATTACK 355, ON_OFF 309,
  AUTO_REPAIR 304, PATROL 265, STOP 258, GUARD 144, IDLE_MODE 115, INSERT 96, RECLAIM 69,
  RESURRECT 14, MANUAL_FIRE 6, REPEAT 4, CUSTOM_37382 1.
- After Team B's encoding: 10,816 train, 1,953 val, 1,970 test orders. Skipped by their code:
  2,558 unsupported form (queue edits and parameter shapes it does not cover), 460 recipient
  not in the observation, 231 target not in the observation, 12 type not in the train vocabulary.

Training (Team B's `scripts/b03_report.py train`, file unchanged, through `train_standin.py`):

    python standin_eval/standin_model/train_standin.py --data standin-barb-v1 --name standin-barb-v1 --steps 3000 --eval-every 100 --seeds 0 --device cuda --cap 192

Printed by the script:

    seed 0: selected step 1100  val TF total 11.608  type acc 0.590  family 0.590  exact set 0.117  (151 s)

From its `train.json`: 66 order types, 9,216 location classes, 37,488 + 1,286,931 parameters;
frequency baseline on val: TF total 15.962, type acc 0.588; val TF total by step went from
13.97 (step 100) to 11.61 (step 1100) to 12.41 (step 3000) while the train total went from
14.81 to 6.80. GPU: RTX 3090, torch 2.9.0+cu126. What the wrapper replaces at run time:
`b03_report.DATA` (map name) and `b03_report.split_of` (split label per row). Changed from
Team B's defaults: steps 400 -> 3000, eval-every 4 -> 100, seeds 0 1 2 -> 0, device, cap 128 -> 192.

First small pass before scaling (`standin-barb-pass1`): 3 recorded games (1 train, 1 val, 1 test,
1,500 rows each), `--steps 1500`, printed `seed 0: selected step 100  val TF total 15.421
type acc 0.545  family 0.545  exact set 0.120  (95 s)`. (Its data folder was made with an
earlier form of `make_pairs.py` that took `--val 1 --test 1`; the script now takes game names.)

Games played (policy on team 0 vs BARb, 20 minute cap, counts from `order_counts.py`;
"greedy" = Team C's stand-in server as is, "sampled" = `-Sample`, Team B's `sample=True`):

| Checkpoint | Decoding | Games | Results | Order replies per game | Command ids per game | Distinct recipients per game |
| --- | --- | --- | --- | --- | --- | --- |
| `b03-h1` | greedy | 9 | 7 lost, 2 timeout | 1058 to 1938 | 1 (all -506) | 1 |
| `standin-d128` | greedy | 2 | 1 lost, 1 timeout | 1361, 1929 | 1 (all -506) | 1 |
| `standin-barb-pass1` | greedy | 1 | lost at 11:23 | 1108 | 3 (135: 1045, 5: 51, 10: 12) | 1 |
| `standin-barb-pass1` | sampled | 1 | lost at 6:50 | 598 | 26 | 2 |
| `standin-barb-v1` | greedy | 1 | lost at 11:39 | 1199 | 3 (-162: 882, 135: 300, 10: 17) | 10 |
| `standin-barb-v1` | sampled | 3 | lost at 12:29, 17:26, 10:32 | 1207, 288, 1032 | 37, 26, 31 | 14, 5, 9 |

Per game with `standin-barb-v1` (value killed and lost from the last team-stats sample):

| Run folder | Decoding | Result | Order replies / submitted | Callbacks tied to a decision | Team 0 killed / lost | Team 0 max metal income, max metal spots | Round trip p50 / p95 ms | Policy status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `game_20261117_142256` | greedy | winner team 1, frame 20982 | 1199 / 1195 | 912 | 692 / 3425 | 4.3, 1 | 30.3 / 58.6 | answered until stopped |
| `game_20261117_142543` | sampled | winner team 1, frame 22476 | 1207 / 1205 | 341 | 1088 / 3688 | 8.3, 1 | 34.4 / 86.4 | answered until stopped |
| `game_20261117_142834` | sampled | winner team 1, frame 31390 | 288 / 288 | - | 30 / 3288 | - | 31.5 / 47.7 | `policy_timeout` at decision 289 |
| `game_20261117_143044` | sampled | winner team 1, frame 18988 | 1032 / 1030 | 160 | 169 / 4125 | 8.7, 1 | 31.1 / 52.1 | answered until stopped |

- The most frequent command ids in the sampled v1 games: 135, -162, 40, 85, 10, -410, 45, -216,
  50, -249, -511 (full lists: run `order_counts.py`).
- `game_20261117_142834`: the predict call for decision 289 (frame 5520) was not answered within
  the 3 s budget (3.001 s elapsed). By the rule kept from Roshan's contract the bridge stopped
  answering; the game ran on with team 0 idle to game over at frame 31390. The server log has no
  warning or error line. The cause was not determined. The 288 answered calls before it had
  p50 31.5 ms and max 76.9 ms.
- In the earlier b03-h1 games team 0's killed value was 0 in every game.
- The sampled server is seeded once at start (`torch.manual_seed(0)`), so the three sampled
  games of one batch share one random stream.
- Recording and the pass-1 games ran at the same time as other jobs on this machine (training,
  other games); round-trip times of those games include that load.

New or changed code (committed locally on `standin/team-d`):
- `fullgame\widgets\standin_recorder.lua` (new, 67 lines): active only when the run folder has
  `record_config.json`; `GameFrame` writes the row of the window that ended and takes the next
  observation per team; `UnitCommand` keeps one of the window's orders (the n-th with
  probability 1/n).
- `fullgame\scripts\run_game.py` (copy): `--record` (skips the NullAI and god-mode edits, writes
  `record_config.json`, no bridge, folder prefix `record_`).
- `fullgame\widgets\standin_control.lua`: removes itself when there is no `control_config.json`.
- `fullgame\docker-compose.yml` (copy): one more read-only mount for the recorder.
- `fullgame\run_fullgame.ps1`: `-MapName` (passed to the server as `--map-name`; empty keeps the
  server default "Great Divide V1") and `-Sample`; both are written into `policy_info.json`.
- `fullgame\scripts\sampling_server.py` (new, 31 lines): imports Team C's `server.py` and makes
  its model policy call `predict_orders(..., sample=True)`. Team C's and Team B's files are unchanged.
- `standin_model\make_pairs.py` (new): recorded rows -> pair rows with Team A's command names
  (`parse_bar_demo.NAMES`), split label per game, manifest.
- `standin_model\train_standin.py` (new): the two run-time replacements, then
  `b03_report.main(["train", ...])`.
- `standin_model\order_counts.py` (new): the counts in the tables above.

Not checked or not settled:
- What the orders do in the game beyond the counts above (which units were built, where units went).
- Why the one predict call took over 3 s.
- Whether the greedy/sampled difference holds over more games; one greedy game per checkpoint.
- No GPU was used for serving (the server runs the model on CPU); training used the GPU.
- Installs: none. Downloads: none beyond what Phase 4 had.
- State at hand-over: no container, bridge, server or training job running.

## Phase 4: done (a checkpoint plays team 0 in a bar-harness game)

Approval: Brian's "Go ahead and write and build according to this", relayed by the session
that started this one, with two later relayed scope updates (local edits to bar-harness
allowed; installs, GPU and other downloads allowed). Neither was used: bar-harness was not
edited, nothing was installed, no GPU was used. The plan written first is `phase4-plan.md`.

One command (PowerShell, from `team-d\standin_eval\fullgame\`):

    .\run_fullgame.ps1 -Checkpoint C:\Users\lolly\bar-standins\shared\ckpt\b03-h1\h1_best.pt -Games 5

What it does: starts Team C's stand-in server on Windows with that checkpoint, runs the game(s)
in WSL Docker on bar-harness's pins (Recoil 2026.09.02, BAR 3510e77f, Supreme Isthmus v2.1),
team 0 = the policy, team 1 = BARb, and stops the server. Each run folder in `fullgame\runs\`
has what a bar-harness run has (`startscript.txt`, `console.log`, `teamstats.json`, `wall.json`,
`report.txt`, `income.png`) plus `policy_info.json` (policy name, checkpoint path and sha256),
`policy_summary.json`, `policy_trace.jsonl`, `control_config.json`, `bridge.log`.

How team 0 is controlled (details and the code reasons are in `phase4-plan.md`):
- The host stays a spectator, as in bar-harness, so the stats widget gets both teams' rows.
- Team 0's AI entry is the engine's `NullAI` 0.1. In `teamstats.json` and the report team 0
  therefore shows as `NullAI`; the policy that played is in `policy_info.json`.
- The start script's `debugcommands` gets `2:cheat 1|10:luarules godmodeally|20:cheat 0`.
  From the engine log of game 013036: "Cheating is enabled!" at frame 30, "Ally godmode:
  enabled" at frame 39, "Cheating is disabled!" at frame 48. Control starts at frame 90.
- `widgets\standin_control.lua` writes Roshan's request envelope for team 0 and gives the
  reply's order with `Spring.GiveOrderToUnit`. `scripts\bridge.py` sends each request through
  Roshan's `PolicyWorker` with `endpoint_adapter.make_policy`. Paced mode, a decision every 15 frames.

Files in `team-d\standin_eval\fullgame\` (committed locally on `standin/team-d`, d1e0772):

| File | Origin | Lines changed against the original |
| --- | --- | --- |
| `.env` | copy of bar-harness `.env` | none (byte-identical; git-ignored by the hpml repo's own rules, present on disk) |
| `scripts\win_rate.py` | copy | none (byte-identical) |
| `widgets\harness_teamstats.lua` | copy | none (byte-identical) |
| `docker-compose.yml` | copy | 12 added, 2 removed: project name and image tag (own image tag and cache volume), two read-only mounts |
| `scripts\run_game.py` | copy | 53 added, 5 removed: docstring note, start script edits (debug commands, NullAI), `control_config.json`, start and stop of the bridge, `--keep-requests`, one status line, one print text |
| `widgets\standin_control.lua` | new, 144 lines, after Roshan's `control_loop_widget.lua` | - |
| `scripts\bridge.py` | new, 173 lines | - |
| `run_fullgame.ps1` | new, 56 lines | - |
| `.gitignore`, `.gitattributes` | new | - |

bar-harness itself: read and copied only. No file in it was edited, added or deleted by this
session. Its own `scripts\win_rate.py` was executed (it only reads the folders given to it).

Games run (stand-in, local CPU for the model, speed 20x asked, one run each):

| Run folder | Policy | Result (`teamstats.json`) | Predicts answered | noop / order replies | Orders submitted | Callbacks tied to a decision | Round trip ms p50 / p95 / p99 / max | Pending-frame advance p50 / p95 / max | Most units in an observation | Wall s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `game_20261117_012900` | scripted, 2 min cap | timeout at frame 3599 | 218 | 216 / 2 | 2 | 2 | 16.5 / 25.4 / 29.0 / 48.7 | 10 / 15 / 32 | 4 | 47.8 |
| `game_20261117_013036` | model (checkpoint) | game over, winner team 1, frame 25933 | 1773 | 253 / 1520 | 1520 | 1216 | 23.5 / 31.4 / 36.4 / 111.9 | 11 / 16 / 32 | 37 | 124.2 |
| `game_20261117_013306` | model | game over, winner team 1, frame 21665 | 1475 | 281 / 1194 | 1193 | 971 | 22.6 / 27.8 / 33.0 / 42.6 | 12 / 17 / 24 | 6 | 98.1 |
| `game_20261117_013446` | model | game over, winner team 1, frame 22692 | 1487 | 307 / 1180 | 1180 | 968 | 22.1 / 25.6 / 31.1 / 58.2 | 12 / 17 / 27 | 30 | 92.7 |
| `game_20261117_013620` | model | game over, winner team 1, frame 25133 | 1630 | 304 / 1326 | 1325 | 1094 | 22.1 / 25.9 / 31.1 / 39.6 | 12 / 17 / 22 | 48 | 99.8 |
| `game_20261117_013801` | model | timeout at frame 35999 | 1918 | 0 / 1918 | 1917 | 1615 | 22.5 / 29.1 / 32.5 / 64.6 | 12 / 17 / 23 | 5 | 119.5 |
| `game_20261117_014002` | model | game over, winner team 1, frame 22654 | 1515 | 315 / 1200 | 1200 | 979 | 22.3 / 27.1 / 32.1 / 58.8 | 12 / 17 / 35 | 17 | 94.4 |

- Policy status was `answered_until_stopped` in all seven games: no timeout, error or crash,
  no failed call, no cleanup error. Sum of the seven games' wall time: 676.6 s.
- Glue rules counted by the endpoint in the model games: rule 3 (`None` y -> unit height) on
  every order reply, rule 1 (`None` -> noop) on every noop reply. No other rule fired.
- All order replies in the six model games were command -506 with options 160, to one
  recipient per game. Two were not submitted by the widget (`order_dropped`: the recipient was
  no longer a team 0 unit when the reply arrived; one each in 013306 and 013620).
- Scripted game, from the kept request stream: unit 25947 (team 0's first unit) was at
  (7600, 4900) at frame 45 and at (7598, 4843) from frame 225 on (move goal z 4836). A unit of
  def 216 (`armsolar`, the catalog's build def) appeared at (7704, 4904) with build progress
  0.63 at frame 405 and 1.0 at frame 1035. Both submitted orders had an engine callback.
- Team stats: both teams have rows in every sample. Last sample of the timeout game 013801:
  team 0 metal income 2, energy income 30, killed 0, lost 0; team 1 metal income 157.1,
  energy income 1674.7, killed 0, lost 525. In the five game-over games team 0's last row has
  `dead: true` and `lostValue` 3133.3.

bar-harness's own `win_rate.py` (the original file, unchanged) on the six model run folders:

    Games with a 20:00 game-time cap, from team 0's side:
      game_20261117_013036          20x           armada   lost at 14:24
      game_20261117_013306          20x           armada   lost at 12:02
      game_20261117_013446          20x           armada   lost at 12:36
      game_20261117_013620          20x           armada   lost at 13:57
      game_20261117_013801          20x           armada   timeout at 20:00
      game_20261117_014002          20x           armada   lost at 12:35
    Team 0: won 0, lost 5, draw 0, timeout 1 (of 6 games)
    Win rate: 0/6 = 0%  (95% interval 0%-39%); a loss, draw or timeout counts as not won
    Timeouts: nothing killed or lost in any of them, so no side was ahead on killed/lost

Six games is the batch size (one single game, then `-Games 5`). The setup differs from the
25 BARb vs BARb games in the bar-harness README in three ways that are in the files: team 0 is
`NullAI` plus the policy instead of BARb, cheats are on for frames 30 to 48, and ally god mode
is on for the rest of the game.

Docker and disk: new image `bar-standin-headless:recoil-2026.09.02` 669 MB (same Dockerfile and
engine pin as bar-harness's image, which was not rebuilt: still "11 days ago"), new volume
`bar-standin_cache` 4.553 MB. The image build downloaded the pinned engine and map again.
Run folders: 1.0 to 2.3 MB each. No install on Windows, in WSL or in an image.

Not checked or not settled:
- What unit def 506 is in this BAR version, and whether any -506 order changed the game.
- Stepped mode in a full game (the widget copy is paced only).
- What the game does after a policy failure (none happened; by design the bridge stops answering).
- A unit of team 2 appeared in one observation of the scripted game (not looked into).
- The first attempt of the wrapper failed before any game: Windows PowerShell treated docker's
  stderr progress lines as errors. Fixed in `run_fullgame.ps1`; the empty run folders were removed.
- State at hand-over: no container, no bridge process, no server on port 8765.

Walkthrough of the new code:
- `run_fullgame.ps1`: starts `team-c\standin_infer\server.py` with `--policy` and, for the
  model, `--checkpoint`; waits for `/health`; writes `policy_info.json` (policy name, checkpoint
  path, sha256); calls the copied `run_game.py` in WSL with bar-harness's Python; stops the server.
- `scripts\run_game.py` (copy): every change is marked `STAND-IN`. `make_startscript` has four
  more regex edits, each of which must match exactly once like the original three.
  `launch` writes `control_config.json` (Roshan's nine config keys plus match id, controlled
  team, first frame), starts `bridge.py` after the image build, and after the engine exits
  creates `bridge_stop`, waits for the bridge and deletes the request stream.
- `widgets\standin_control.lua`: `emit` appends one JSON line per event; `observe` calls
  `conservativeView` for team 0; `request` writes Roshan's envelope; `GameFrame` sends the reset
  once the team has a unit and then a predict every 15 frames unless one is pending; `Update`
  reads the reply file, checks the identity fields, gives the order or records `order_dropped`;
  `UnitCommand` records the callback for the last order only.
- `scripts\bridge.py`: `read_new` reopens the request file for every read (the `/mnt/c` issue
  from Phase 2); the main loop validates each request, submits it to `PolicyWorker`, polls,
  applies Roshan's `deadline_failure`, publishes the reply with his `atomic_json`, and writes
  one trace line per decision; at the end it writes `policy_summary.json`.

## Phase 3: done (policy-side metrics per run)

Approval: Brian's "Approve Phase 3", relayed by the session that started this one.
Scope: policy-side numbers only. Game-level metrics (winner, win rate, value killed or lost,
income) are not computed here; they stay with bar-harness.

Files written or changed in `team-d\` (committed locally on `standin/team-d`):
- `standin_eval\metrics.py` (new): reads one run folder (`result.json`, `trace.jsonl`,
  `standin.json`, optional `server.log`) and writes `shared\logs\metrics_<label>_<match8>.json`.
  It measures nothing itself. Command: `python standin_eval\metrics.py` (all `live_*` folders).
- `standin_eval\run_live.sh`: the copy step now also saves the in-container endpoint log as
  `server.log` in the run folder (`inside` step). For the `host` step the Windows server's
  output has to be saved there by hand.

Where each number comes from:
- `episode_status`, `case_passed`, `reason`, `timing_errors`, `sim_frames` (`last_engine_frame`),
  `wall_seconds`, `failed_policy_call`, pending-frame advance (`pending_frame_deltas`): Roshan's `result.json`.
- decisions, action kinds, orders submitted, callbacks tied to a decision: counts of
  `policy_call_started`, `policy_response`, `order_submitted`, `engine_command_callback` events in his `trace.jsonl`.
- round trip: `policy_call_seconds` of answered predict calls in `policy_response` events
  (supervisor reads the request -> reply published; includes his 10 ms poll), nearest-rank percentiles.
- failed calls by status: the call still open when the episode failed, under `episode_status`.
- glue rules: lines of the endpoint's `server.log` (`INFO glue <rule>:` for rules 1 to 4,
  `WARNING policy error on` for rule 5). `null` when the run folder has no `server.log`.

Table printed by `metrics.py` on 2026-11-17 (stand-in, local CPU, one run each):

| Label | Match | `episode_status` | `case_passed` | Predicts answered | noop | order | p50 ms | p95 ms | p99 ms | Failed call | Glue rules fired | Pending-frame max | Sim frames | Wall s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `endpoint_model` | 4246fd50 | `run_timeout` | false | 194 | 0 | 194 | 21.168 | 41.771 | 217.6 | - | rule 3: 194, rule 5: 0 | 0 | 2955 | 120.432 |
| `endpoint_noop` | 5beb75e7 | `run_timeout` | false | 205 | 205 | 0 | 11.062 | 11.582 | 12.085 | - | rule 5: 0 | 0 | 3120 | 120.39 |
| `endpoint_scripted_happy` | 86f0ab16 | `completed` | true | 76 | 73 | 3 | 11.134 | 25.043 | 87.494 | - | rule 5: 0 | 0 | 1197 | 57.703 |
| `endpoint_scripted_timeout` | 68782d43 | `policy_timeout` | true | 0 | 0 | 0 | - | - | - | `policy_timeout`: 1 | rule 5: 0 | 0 | 60 | 19.263 |
| `roshan_happy` | 1c1a0cdf | `completed` | true | 76 | 73 | 3 | 11.033 | 11.462 | 12.836 | - | no server.log | 0 | 1197 | 58.636 |
| `roshan_happy` | 86df9852 | `failed` | false | 44 | 42 | 2 | 76.658 | 108.107 | 111.601 | - | no server.log | 0 | 705 | 83.886 |

Notes on what was run:
- `endpoint_scripted_timeout` is the one new run of this phase: Roshan's own `--case timeout`
  with `--policy-factory endpoint_adapter:make_policy` and the scripted server in the container.
  His fault injection blocks inside the policy worker before the policy is called. The failed
  call: predict, decision 1, frame 60, `elapsed_seconds` 3.009 against `budget_seconds` 3.
  `case_passed` is true there because his timeout case expects `policy_timeout`.
- `roshan_happy` 86df9852 is the run that failed with OSError 61 on the `/mnt/c` output folder.
- The other four runs are the Phase 2 runs; their server logs were copied into the run folders
  (two from the Docker volume, the model one from the Windows server's saved output).
- No container or server is running. No download, no install, no outbound network call.

## Phase 2: done (live loop on Roshan's fixture)

Approval: Brian's "Approve Phase 2", relayed by the session that started this one. Covered:
Docker in WSL, the downloads, the `--policy-factory` option, scripted and noop inside the
container, and trying host networking for the model. Not used: any install, GPU, second image.

Files written or changed in `team-d\` (committed locally on `standin/team-d`):
- `scripts\run_control_loop.py`: the one change to Roshan's files, 10 lines added, 1 removed.
  New optional `--policy-factory MODULE:CALLABLE`; without it nothing changes.
- `standin_eval\run_live.sh`: the docker commands of his `.ps1`, run inside WSL.
- `standin_eval\control_loop_short.json`: his config with `run_timeout_seconds` 120 instead of 480.
- `standin_eval\.gitattributes`: keeps `run_live.sh` with Unix line endings.

How the four snags went:
- a. Policy choice: `--policy-factory endpoint_adapter:make_policy`. Control-loop tests after the
  change: 46 passed.
- b. Launcher: `wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/lolly/bar-standins/team-d/standin_eval/run_live.sh STEP ...`.
  Roshan's default output folder is on the `/mnt/c` mount here. The first happy run failed on it:
  `episode_status: failed`, `OSError: [Errno 61] No data available`, at frame 705 after 45
  answered calls, 0.5 s after the last reply, with the engine still running (log kept in
  `shared\logs\live_roshan_happy_86df9852...`). All later runs pass his own
  `--output runtime/output/control_loop`, which puts episode files in the Docker volume.
- c. Scripted and noop: the Team C server runs inside the same container (`inside` step).
  Model: the server ran on Windows (`python standin_infer\server.py --policy model` in `team-c\`)
  and the container used `--network host` (`host` step). `/health` answered from Windows, from
  WSL and from a host-network container. No torch was installed anywhere.
- d. Sizes: image `hpml-eval01:local` 640 MB. Volume `hpml-eval01-runtime` 2.244 GB after all
  runs (engine, map, game and five episode folders). The game download was 3,346,983,625 bytes
  in 17,837 files (pr-downloader's own count); preparation took 147 s. `C:` free space was
  201.4 GB before the first download. WSL `/` used space went from 37 GB to 40 GB.

Runs (Roshan's `result.json`, `trace.jsonl`, `trace.md`, `manifest.json` copied unchanged to
`shared\logs\live_<label>_<match id>\`, plus `standin.json` with the label and loop arguments):

| Label / match | Policy and path | `episode_status` | `case_passed` | Effects move/build/attack | Last frame | Wall s | Replies | Orders submitted | Callbacks tied to a decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `roshan_happy` 86df9852 | his `ScriptedPolicy` in the worker, output on `/mnt/c` | `failed` (OSError 61) | false | false/false/false | 705 | 83.9 | 2 order, 42 noop | 2 | 2 |
| `roshan_happy` 1c1a0cdf | same, output in the volume | `completed` | true | true/true/true | 1197 | 58.6 | 3 order, 73 noop | 3 | 3 |
| `endpoint_scripted_happy` 86f0ab16 | `ScriptedPolicy` behind the endpoint, server in the container | `completed` | true | true/true/true | 1197 | 57.7 | 3 order, 73 noop | 3 | 3 |
| `endpoint_noop` 5beb75e7 | noop behind the endpoint, 120 s cap | `run_timeout` | false | false/false/false | 3120 | 120.4 | 205 noop | 0 | 0 |
| `endpoint_model` 4246fd50 | B03 checkpoint behind the endpoint on Windows, 120 s cap | `run_timeout` | false | false/false/false | 2955 | 120.4 | 194 order | 194 | 194 |

More from the traces (counted with one-off commands, not with new code):
- `roshan_happy` 1c1a0cdf and `endpoint_scripted_happy`: the same three orders at the same frames
  (move unit 28820 at frame 60, build -212 with unit 9983 at frame 90, attack 20 on 13225 at
  frame 1140), the same event counts (77 requests, 77 responses, 154 pause events, 16 callbacks,
  1 game_over), the same 77 responses with zero pending-frame advance as Roshan's saved run 0824f030.
- `policy_call_seconds` of predict calls in the trace, ms (p50 / p95 / p99 / max): in-process
  scripted 11.0 / 11.5 / 12.8 / 12.8; endpoint scripted 11.1 / 25.0 / 87.5 / 87.5; endpoint noop
  11.1 / 11.6 / 12.1 / 13.7; endpoint model (Windows server) 21.2 / 41.8 / 217.6 / 465.5.
  The supervisor polls every 10 ms. No call reached the 3 s budget.
- `endpoint_model`: all 194 orders were unit 9983, command -506, options 160, params
  `[1856.0, 245.09, 64.0, facing]`. The engine sent 194 `engine_command_callback` events for
  command -506. In all 195 requests the observation had the same 3 units (def ids 49, 182, 302),
  every unit queue was empty, and no unit moved. Not checked: what def 506 is in this game
  version, or why no queue entry appeared.
- Pending-frame advance was 0 in every run (`pending_frame_deltas`). `timing_errors`: none.
  `cleanup_errors`: none.
- `case_passed` is Roshan's verdict for the scripted fixture. The noop and model rows are
  recorded as he computes them and are not relabeled.
- The manifest hash of `lua/bar_proof_common.lua` differs from Roshan's saved runs: the Team A
  merge added an optional third argument to `M.unit`. `conservativeView` does not pass it.
  The hash of `scripts/run_control_loop.py` differs from the endpoint runs on (the new option).

State at hand-over: no container running (`docker ps` empty), no server on port 8765 (the
Windows model server was stopped by process id), image and volume kept for later phases.
One mistake to report: a reachability check ran `curl --noproxy *` through WSL without quoting
that survived, so the shell expanded `*` to the file names in `team-d\` and curl also requested
some of them as host names (one answered with an nginx 301 page). No file content was sent.

## Phase 1: done (dry loop, no engine)

File written: `team-d\standin_eval\dry_loop.py` (committed locally on `standin/team-d`).
No change to Roshan's files. Nothing in `team-c\` or `shared\endpoint_adapter.py` was edited.
Added to `shared\CONTRACT.md`: the two sources of "my team" (item 8 in its verified line).

How a run works: the Team C stand-in server is started from `team-c\`, then
`python standin_eval\dry_loop.py --label <name> --source traces|data` sends saved requests
through Roshan's `PolicyWorker` with the factory `endpoint_adapter.make_policy`, one episode
per trace file or per DATA-01 viewing team, and the server is stopped afterwards.
Deadlines use Roshan's `deadline_failure` and his config (3 s budget). The dry loop polls every
10 ms like `engine.run_episode`, and the worker polls its mailbox every 5 ms, so every round
trip includes that polling.

Runs (logs in `shared\logs\`, all stand-in, local CPU, one run each):

| Log | Server | Requests | Episode status | Replies | Round trip of answered predicts, ms (p50 / p95 / p99 / max) |
| --- | --- | --- | --- | --- | --- |
| `dry_scripted_traces_20261116_202404.json` | `--policy scripted` | 3 traces: 77, 1, 2 | all answered | 73 noop + 3 order; 0 + 0; 0 + 1 | 30.5 / 51.5 / 51.7 / 51.7 (77-request trace) |
| `dry_model_traces_20261116_202411.json` | `--policy model` | same 3 traces | all answered | 76 order; 0; 1 order | 31.2 / 50.8 / 62.2 / 62.2 (77-request trace) |
| `dry_model_data_20261116_202424.json` | `--policy model` | 200 DATA-01 states: team 0 159 + reset, team 1 41 + reset | all answered | 159 order; 41 order | team 0: 42.2 / 64.3 / 73.9 / 75.0; team 1: 33.1 / 64.0 / 75.1 / 75.1 |
| `dry_noop_data_20261116_202433.json` | `--policy noop` | same 200 states | all answered | 159 noop; 41 noop | team 0: 30.8 / 53.4 / 74.1 / 75.0; team 1: 29.1 / 60.2 / 71.4 / 71.4 |
| `dry_scripted_data_20261116_202436.json` | `--policy scripted` | same 200 states | `policy_error` at decision 1, both teams | none | failed call after 29.1 ms and 28.6 ms |
| `dry_timeout_sleep4000_20261116_202441.json` | `--policy noop --sleep-ms 4000` | first trace only | `policy_timeout` at decision 1 | none (reset answered) | failed call stopped at 3004.4 ms |

Other things measured in those runs:
- Scripted over the endpoint, 77-request trace: 77 of 77 replies equal the replies recorded in
  Roshan's trace (`policy_response` events), compared as whole JSON objects.
- Model on the same trace: 1 of 77 equal (the reset reply).
- Glue rules counted by the endpoint (`/stats`): model runs fired `rule3_none_y_to_unit_height`
  77 times (traces) and 200 times (data). No other rule fired. Scripted and noop: none.
- The scripted `policy_error` reason: `ProtocolError: Controlled attacker is missing` (the
  placeholder catalog's unit ids are not in the DATA-01 match). Expected, per Team C's note.
- Worker cleanup errors: none in any run. No server left running (port 8765 checked).
- A first set of six runs was deleted and re-run: in it the elapsed time of a failed call was
  read after the worker was closed (3263 ms for the timeout), which was a bug in the dry loop.

## Checked for Phase 2 (no Docker was run)

- WSL Ubuntu-24.04: networking mode `mirrored`, Python 3.12.3, no torch.
- Disk: `/` in WSL has 920 GB free of 1007 GB (virtual disk). `C:` has 12 GB free of 1.9 TB.
  Not checked: on which Windows drive the WSL virtual disk file is stored.
- Roshan's image (`Dockerfile`) has python3 and no torch. `prepare_control_loop_runtime.py`
  downloads the engine archive, the map and the game (through `pr-downloader`) into the runtime.

## Phase 0: done

- Read all 39 issues of Na00s/hpml (table below). The project-board call failed:
  the gh token lacks `read:project`. To fix: `gh auth refresh -s read:project`.
  Until then owners and dates come from the issues only.
- Read Roshan's loop: `docs/control-loop.md`, `docs/policy-contract.md`,
  `scripts/control_loop/{protocol,policy_worker,engine,scripted_policy,mailbox}.py`,
  `lua/control_loop_widget.lua`, `scripts/run_control_loop.py` and `.ps1`,
  and Team B's `docs/b02/README.md` (executor checks) and `docs/b03/README.md`.
- Checked every statement in `shared\CONTRACT.md` against that code, the saved traces in
  `evidence/policy_timeouts`, `shared\data` and `shared\ckpt`. The changes are listed in the
  "verified by Team D session" line at the top of the contract.
- Tests in `team-d\` (`python -m pytest tests -q`): 3 failed, 239 passed, 15 skipped,
  45 subtests passed, 23.7 s. The 3 failures are the ones listed in the contract (one Team B,
  two Team A). The six control-loop test files alone: 46 passed, 35 subtests passed.
- No code written. No file in `team-d\` changed. No change to Roshan's files.

## What exists

| Piece | Where | State |
| --- | --- | --- |
| Roshan's EVAL-01 loop | `team-d\scripts\control_loop`, `lua\control_loop_widget.lua` | real code, tests pass |
| Saved live requests | `team-d\evidence\policy_timeouts\*\trace.jsonl` (77 + 1 + 2 `policy_request` events) | real traces |
| Team A data | `shared\data\state_command_pairs.jsonl` (2,802 rows, sha256 re-checked) | real DATA-01 match |
| Team B checkpoint | `shared\ckpt\b03-h1\h1_best.pt` | loads, decodes orders on CPU |
| Team C stand-in endpoint | `team-c\standin_infer\server.py` and `shared\endpoint_adapter.py` (other session) | ready, see `status\team-c.md`; used by Phase 1 |
| Dry loop | `team-d\standin_eval\dry_loop.py` | written in Phase 1, six logs in `shared\logs\` |
| Brian's full-game harness | `OneDrive\Desktop\Projects\bar-harness` | read only; different engine, game and map pins |

## What is next (each needs Brian's go)

1. Phase 1: done, see above.
2. Phase 2: done, see above. The proposal as it was written before the runs:
   a. One suggested change to Roshan's `scripts\run_control_loop.py`: an optional
      `--policy-factory module:callable` argument passed to `PolicyWorker(factory=...)`.
      Default stays `ScriptedPolicy`. His happy case is reproduced before this change is made.
   b. No change to `run_control_loop.ps1`. The same three docker commands are run inside WSL
      with the worktree mounted from `/mnt/c/Users/lolly/bar-standins/team-d`.
   c. Scripted and noop: start `team-c\standin_infer\server.py` inside the same container as
      the loop (python3 only), with `team-c\` and `shared\` mounted read-only.
      Model: the image has no torch. Either run the server on Windows and the container with
      `--network host` (WSL is in mirrored networking mode; not tried), or install CPU torch in
      a second local image (an install, needs Brian's OK).
   d. The first run builds the image and downloads the engine, map and game into the Docker
      volume `hpml-eval01-runtime`. `C:` has 12 GB free. Needs Brian's OK.
   A model run has no fixture GameOver, so it ends by `run_timeout_seconds` (480 s in Roshan's
   config). A copy of the config with a smaller value can be passed with `--config`.
3. Phase 3: done, see above. Scope as it was set: policy-side metrics per run into
   `shared\logs\`: round-trip percentiles, action-kind
   counts, glue-rule counts, late or failed calls by status, pending-frame advance.
   Game-level metrics (result, win rate, value killed/lost, income) are NOT rewritten: they
   come from Brian's bar-harness (`scripts/run_game.py`, `scripts/win_rate.py`,
   `widgets/harness_teamstats.lua`).
4. Phase 4: done, see above (Brian later approved building it). Scope as it was first set:
   a written plan only: the smallest change that lets a policy-controlled team take
   team 0's slot in a `run_game.py` game against BARb, so `win_rate.py` and the stats widget
   work unchanged. The number to compare with is in the bar-harness README: BARb vs BARb,
   team 0 won 6 of 25 games with a 20 min cap (as of 2026-11-13).

Scope correction from Brian, relayed 2026-11-16 by the session that started this one:
bot-vs-bot games and win-rate metrics already exist in bar-harness; reuse them, write no new
versions. bar-harness stays read-only until Brian says otherwise.

## Facts from the code that Phase 1 and 2 must respect

- The policy gets the raw request with Lua floats (`1.0`, `45.0`). It must normalize with
  `validate_request` and echo integers, or `validate_response` rejects the reply.
- A predict is refused unless a reset for the same match, generation, player and team completed
  first, and decision ids must increase. Saved predicts cannot be sent on their own.
- `validate_request` requires the fixture `catalog`. States from `shared\data` have none,
  so the dry loop has to add a placeholder catalog to wrap them in the envelope.
- `scripts\run_control_loop.py` builds `PolicyWorker(fault=args.case)` with the default
  `ScriptedPolicy`. There is no option to choose another factory yet.
- The factory is pickled by name for a `spawn` child, so it must be a top-level importable
  callable and its module must be on `sys.path`.

## Open questions

For Roshan (EVAL-01, EVAL-02):
- Suggested change to take to him: `--policy-factory MODULE:CALLABLE` on
  `scripts/run_control_loop.py` (see `git diff 9983e94 -- scripts/run_control_loop.py` in `team-d\`).
- With Docker inside WSL and the repo on `/mnt/c`, his default `output/` failed once with
  `OSError: [Errno 61] No data available` (supervisor side, engine still running). Should the
  launcher default to an output folder on a Linux filesystem, or should `engine.py` retry that read?
- A model run on the fixture never reaches GameOver and ends by `run_timeout`. Does he want a
  frame cap in the fixture or widget for non-scripted policies?
- In the model run the engine sent a callback for all 194 build orders (-506) but no queue entry
  and no new unit appeared. Is that an EVAL-02 case (order accepted by the API, no effect)?
- Can `run_control_loop.py` take an option naming the policy factory (module:callable)?
- `catalog` is required by `validate_request` but only the scripted policy uses it. Should a
  model policy have to receive it?
- The policy receives un-normalized floats and must echo ints. Intended, or should the worker
  hand the policy the normalized request?
- Protocol v1 takes one `unit_id`; the B03 decoder returns `unit_ids` (and `params_per_unit`
  for formations). Is multi-recipient planned for EVAL-02, and in what shape?
- B03 leaves y as `None` in `params`; the protocol rejects `None`. Who fills y: policy adapter
  or the widget (ground height)?
- Team B proposed `check_executable` (docs/b02) as Team D's executor check. Adopt it, and where
  does it run: before `validate_response`, or in the widget?
- The fixture pins BAR `test-31368-8379d65`; the checkpoint's unit def ids come from the
  DATA-01 replay's game version. Is def 506 the same unit in both?
- The pass checks (move, build, attack) are for the scripted policy. What should
  `case_passed` mean for a model run?

For Jon (benchmarks, EVAL-03):
- Should the EVAL-03 benchmark be built on Brian's existing runner (bar-harness `run_game.py`,
  `win_rate.py`, `harness_teamstats.lua`)? It already runs capped BARb vs BARb games and
  computes win rate. It is not on any branch of Na00s/hpml.
- Which engine, game version and map does the benchmark pin? Roshan's loop: Recoil 2026.07.04,
  BAR test-31368-8379d65, Great Divide V1. bar-harness: Recoil 2026.09.02, BAR commit 3510e77f,
  Supreme Isthmus v2.1.
- Which opponent first (NullAI, SimpleAI, BARb), and which frame cap and seeds?
- The Nov 20 checkpoint asks for a scripted baseline and a first learned checkpoint on a small
  suite. Which scripted policy plays a real match? `ScriptedPolicy` only knows the fixture.
- Episode end: the fixture ends by a fixture `GameOver`; bar-harness ends by commander death
  or a `quitforce` cap. Which rule does the benchmark use?

For Nikash (game metrics):
- Which per-game metrics are required? bar-harness's widget writes team stats every 450 frames,
  the GameOver winner and a timeout record. Roshan's `result.json` has episode status, effects,
  pending-frame deltas, wall seconds and last engine frame.
- Can the stats widget and Roshan's control widget run in the same game? Roshan's widget
  asserts that it is a player, not a spectator. Not checked: whether the stats widget works
  from a player slot.
- Where does failed-order rate come from: `order_submitted` vs `engine_command_callback` events
  in the trace, or a new check from EVAL-02?
- Is inactivity (EVAL-03 asks for it) defined yet?

## Issue table (from `gh issue list`, 2026-11-16)

Due = the "Due" line in the issue body; the GitHub milestone date is in brackets when it differs.
Owner = issue assignee (the project board could not be read). **D** = Team D owns it.
**Nov 20** = due Nov 20. (cp Nov 20) = has a checkpoint on Nov 20 but is due later.

| # | Issue | Team | Owner | Due | Produces | Consumes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | DATA-01 one complete match (closed) | A | - | Nov 6 [Nov 13] | reproducible command sequence, match summary, annotated transitions | - |
| 2 | DATA-02 field inventory | A | - | Nov 6 [Nov 13] | machine-readable field inventory, coverage statistics | - |
| 3 | DATA-03 fog of war, radar, memory | A | - | Nov 13 | visibility scenario suite, expected observations, leak report | DATA-02 |
| 4 | DATA-04 action sequence and timing | A | - | Nov 6 [Nov 13] | trace examples, action coverage table, join rates, timing offsets | DATA-01 |
| 5 | DATA-05 replay census and split | A | - | Nov 6 [Nov 13] | split manifest, corpus summary, duplicate checks | DATA-01 |
| 6 | DATA-06 resumable extraction, scaling | A | - | Nov 25 [Dec 4] | resumable extractor, games/hour and scaling numbers | DATA-01, DATA-04 |
| 7 | DATA-07 storage formats, history sampler | A | - | **Nov 20** | loader and history sampler, fixture suite, format measurements | DATA-04, DATA-05 |
| 8 | DATA-08 corpus release | A | - | Dec 4 | released corpus (v0 20 matches Nov 13, v1 Dec 4), checksums, quality report | DATA-02 to 07, B01, B02 |
| 9 | **D** EVAL-01 one decision into a running game | D | rk3293 | Nov 6 [Nov 13] | one-command demo, annotated trace, control-loop description, request/response/reset examples for Team C | - |
| 10 | **D** EVAL-02 move, attack, build, queued orders | D | rk3293 | **Nov 20** | scenario runner, expected outcomes, table of supported command semantics; fixtures for B02/C02 | EVAL-01, DATA-04 |
| 11 | **D** EVAL-03 small repeatable benchmark | D | - | Dec 4 (cp Nov 20: scripted vs learned pilot) | benchmark command, games/hour and cost estimate, first comparison table | EVAL-01, EVAL-02, a checkpoint with its serving config |
| 12 | **D** EVAL-04 imitation loss vs play | D | - | Dec 18 | checkpoint comparison table, loss-versus-outcome plots, annotated examples | EVAL-03, B05, C08 |
| 13 | **D** EVAL-05 stale observations | D | - | Dec 11 (cp Nov 20: first delay curve) | delay-versus-outcome plot, annotated execution trace, starting decision cadence | EVAL-01, EVAL-02, C01, C02 |
| 14 | SHARED-01 one example from replay to command | shared | - | Nov 13 | walkthrough, observation/action/history/checkpoint specification (schema v1) | - |
| 15 | SHARED-02 repository easy to run | shared | - | Nov 6 [Nov 13] | setup and contribution instructions | - |
| 16 | SHARED-03 experiment plan, run records | shared | - | Nov 6 [Nov 13] | compute budget, common run-record fields | - |
| 17 | SHARED-04 final report | shared | - | Dec 23 | report, configurations, manifests, benchmark commands | DATA-08, B05, B06, B09, B10, C08, EVAL-04, EVAL-05 |
| 18 | B01 state encoder (closed) | B | nickmeeks | Nov 9 [Nov 13] | state encoder, tensor and unit-id fixtures | DATA-02, SHARED-01 |
| 19 | B02 command decoder (closed) | B | SulRash | Nov 11 [Nov 13] | action decoder, vocabulary and masks, executor-check proposal for Team D | B01, DATA-04 |
| 20 | B03 small model on real examples (closed) | B | nickmeeks | Nov 13 | tiny-set fit, H=1 baseline, checkpoint for Team C | B01, B02, DATA-01, DATA-05 |
| 21 | B04 causal history model | B | nickmeeks | **Nov 20** | history model, mask/reset checks, cache specification for Team C | B03, DATA-07 |
| 22 | B05 gain from longer history | B | y656 | Dec 4 | paired H=1/8/32/128 results and checkpoints | B04, DATA-07 |
| 23 | B06 compress units and history | B | - | Dec 11 | comparison of unit/history representations | B04, B05 |
| 24 | B07 optimizer comparison | B | - | **Nov 20** | selected AdamW settings for the history study | B03 |
| 25 | B08 model size vs training time (extension) | B | - | Dec 11 | throughput and equal-budget comparison of three sizes | B05, B07 |
| 26 | B09 recipe search, resumable training | B | - | Dec 1 [Dec 4] (cp Nov 20) | checkpoint/resume support, primary recipe, recipe comparison | B07, SHARED-03 |
| 27 | B10 training throughput | B | - | Dec 11 | throughput measurements and optimization sequence | B04, DATA-07 |
| 28 | B11 demonstration selection (extension) | B | - | Dec 11 | paired comparison of a selected subset | B05, B09 |
| 29 | B12 distillation (extension) | B | y656 | Dec 11 | distilled student, serving measurements | B05, B09 |
| 30 | C00 released action policy measurements | C | Devang-Shah-49, kdorch11 | Nov 6 [Nov 13] | native baseline and one implementation comparison on a released policy | - |
| 31 | C01 how long a BAR decision takes | C | hbzengin, JHshin6688 | Nov 13 | paced driver, stage timing, p50/p95/p99, deadline-miss fraction | shared state/action representation, a reference model or stub |
| 32 | C02 served policy matches training model | C | - | **Nov 20** | reference-vs-serving agreement checks and fixtures | C01, B02, B03; Team A traces; Team D execution semantics |
| 33 | C03 BAR policy in vLLM | C | - | **Nov 20** | vLLM compatibility table, adapter or feasibility result | C00, C01, C02, B04 |
| 34 | C04 eager vs compiled vs CUDA graphs | C | - | Dec 4 | backend comparison with action agreement | C01, C02 |
| 35 | C05 KV cache reuse | C | - | Dec 4 | cache study with eviction and reset | C02, B04 |
| 36 | C06 games per server within the deadline | C | - | Dec 11 | concurrency curve, queue delay, deadline misses | C01, C02, C04, C05; Team D trace timing |
| 37 | C07 quantization | C | - | Dec 11 | precision comparison, changed decisions | C02, C04, B05; Team D closed-loop comparison |
| 38 | C08 serving results inside the game | C | - | Dec 16 [Dec 18] | live timing trace, final serving configuration | C02, C03, C05, C06, C07, EVAL-03 (Team D game runner) |
| 39 | C09 action chunks (extension) | C | - | Dec 11 | chunk-policy prototype and comparison | C02, C06, EVAL-05, B04 |
