# Team D update notes, 2026-11-18 (for Brian's own slides)

Facts and numbers only, written by the AI session from the run files. The slide wording is
Brian's. Everything below is local on Brian's PC ("stand-in" fixtures under
`C:\Users\lolly\bar-standins`); nothing was pushed, posted or commented on GitHub.
Full notes with every run folder: `shared\status\team-d.md`.

Already shown at the last meeting, so not repeated here: the bar-harness pipeline, the value
killed / lost plot, metal spots held, army front line, income plot, wall time.

## 1. What is new since then

1. **A checkpoint can play a full game.** One command (`run_fullgame.ps1 -Checkpoint ...`)
   puts a model on team 0 of a headless BAR game: a spectator widget sends team 0's
   observation every 15 frames, a bridge (with Roshan's `PolicyWorker`, 3 s budget per
   decision) asks a policy server, and the answer is given to the unit as an order.
   Image: `harness_diagram.png`.
2. **Opponent is a setting**: idle (`null`), SimpleAI, BARb easy / medium / default / hard-aggressive.
3. **Every game writes what was played**: `run_settings.json` (map, opponent and profile,
   engine and BAR commit, sides, start positions, cap, end rule, policy and its settings).
4. **Replays**: `-SaveReplay` keeps the engine's replay file in the run folder; replays open
   in the Windows BAR install (engine 2026.09.02 and the pinned game were added to it).
5. **Policy-side numbers per game** (`policy_summary.json`): orders given, orders dropped,
   share of decisions with no order, response time p50 / p95, and an explicit status when
   the policy stopped (timeout, error).
6. **Our team in the game is named `OUR_MODEL_<checkpoint>`.**
7. **EVAL-03 pilot** (issue 11): a pinned game list, a runner that can be continued after a
   stop, a table with win rate, and a games-per-hour number. See section 3.
8. **Our own test model ("unit policy")**, because no team has a checkpoint in the repo that
   we could run. See section 4.

## 2. Checkpoints that were plugged in (all local stand-ins)

| Checkpoint | What it is | In a game |
|---|---|---|
| `b03-h1`, `standin-d128` | Team B's B03 code, trained locally on a small sample | 11 games vs BARb: 8 lost, 3 reached the cap; every order was the same build command to one unit |
| `standin-barb-v1` | B03 code trained on BARb's orders recorded in our own games (15 games, 60,170 rows) | 4 games vs BARb, all lost (10:32 to 17:26) |
| `standin-human-v1` | B03 code trained on Team A's 20 human matches | built nothing: 98 of 136 build orders were for the other faction's units, cosmetic units, or had no position; the 8 accepted ones were 1,017 to 7,393 elmos away from the builder |
| `unit-v1a`, `unit-v2a`, `unit-v2b` | our own unit policy on Team A's human matches | see sections 3 and 4 |

## 3. EVAL-03 pilot: win rate

Game list `pilot-v1`: Supreme Isthmus v2.1, the policy as Armada on team 0, 3 games against
SimpleAI and 3 against BARb easy, 20 minute cap, replay saved for every game. Games differ
run to run even with the engine's fixed seed, so each repeat is one more independent game.
Win rate = games won / games played; a game that reaches the cap with no winner is not a win.

| Policy | Opponent | Games | Won | Lost | No winner by the cap | Policy stopped early |
|---|---|---|---|---|---|---|
| first model (`standin-human-v1`) | SimpleAI | 3 | 0 | 0 | 3 | 0 |
| first model (`standin-human-v1`) | BARb easy | 3 | 0 | 0 | 3 | 1 |
| scripted (Roshan's 2-order fixture) | SimpleAI | 3 | 0 | 3 | 0 | 3 |
| scripted | BARb easy | 3 | 0 | 1 | 2 | 1 |
| learned (`unit-v2b`) | SimpleAI | 3 | 0 | 2 | 1 | 1 |
| learned (`unit-v2b`) | BARb easy | 3 | 0 | 1 | 2 | 1 |
| built-in BARb (reference, default profile) | SimpleAI | 3 | 1 | 0 | 2 | - |
| built-in BARb (reference, default profile) | BARb easy | 3 | 1 | 0 | 2 | - |

- The first model on the same six games: 617 to 2,091 orders per game, 79% to 84% of them
  without an engine callback, 1 finished unit at the end (the commander), metal income
  never above 2.4, lost value 0 in every game, value killed 1,290 / 5,665 / 1,003 against
  SimpleAI and 0 against BARb easy. Its replay screenshots (`replay_first-model_simple-2\`)
  show the commander in the sea from minute 4 on. One of its six games hit the 3 s policy
  timeout; it runs on Team C's stand-in server, not on the unit policy's server.
- In one 4 minute game looked at order by order (`first_model_orders.png`): 334 orders, all to
  the commander; 198 not build orders; 84 builds of the other faction's units; 12 Armada
  builds without a position; 2 cosmetic units; 38 Armada builds with a position, of which 8
  showed up in the commander's queue, 1,017 to 7,393 elmos away; 209 of the 334 orders
  replaced the queue.
- CORRECTION (later the same evening): six games was a small sample for the reference. With
  the 17 further 20 minute games recorded for training data, the built-in BARb in team 0's
  slot won 16 of 23 inside the cap: 11 of 15 against SimpleAI, 5 of 8 against BARb easy.
- The built-in BARb in team 0's slot won 2 of its 6 pilot games (12:24 and 13:23); the other 4 had no
  winner at the 20 minute cap, with value killed / lost of 12,705 / 4,528, 13,919 / 5,913,
  3,181 / 1,788 and 8,124 / 4,677.
- 12 policy games: wall time per game 57 to 197 s (mean 130 s); **27.7 games per hour**
  playing one at a time; 163 minutes of game time. Resource use was not measured.
- Game length (minutes): scripted vs SimpleAI 5.0 to 5.6; learned vs SimpleAI 11.8, 12.8, 20.0;
  scripted vs BARb easy 16.7, 20.0, 20.0; learned vs BARb easy 6.2, 20.0, 20.0.
- Learned policy, orders per game: 130, 130, 20, 48, 135, 28. Share of decisions with no
  order: 0.84 to 0.99.
- "Policy stopped early": the scripted policy raises an error once its unit is gone. The
  learned policy's two stops are the 3 s timeout (see section 5).
- Images: `pilot_win_rate.png`, `pilot_game_length.png`, `pilot_orders.png`,
  `pilot_killed_value.png`. Table file: `shared\status\benchmark\pilot-v1\table.md`.
- Not in the pilot yet: more than one map, swapped sides, parallel games, an uncertainty
  estimate (3 games per cell), a development / final split of the game list.

## 4. The unit policy (our own local test model)

- Question it answers: "this unit of mine can take an order: which order?" One training
  example = (state, one unit that received an order, the order). 600,000 parameters.
- Data: Team A's 20 human matches (14 train / 3 validation / 3 test, split by whole match):
  148,139 training examples. Only 1,877 of them are orders to a commander, and "build a
  factory" is 12 of 54,193 validation examples.
- Version 2 changes: positions relative to the unit (or to the end of its queue), no map
  coordinates as input, a frequency table (unit type x order type) as the starting point,
  mirrored states as extra data.
- Held-out matches, order type predicted right: 0.86 for all orders (frequency table alone:
  0.65); 0.62 for build orders (table alone: 0.63). Image: `training_curve_unit-v2a.png`.
- One training run: 4,000 steps in about 7.5 minutes on the RTX 3090 (10 GB cap, bfloat16).
- Development games against the idle opponent, 10 minutes: finished units 14 (`v1a`),
  46 and 8 (`v2a`), 8 and 28 (`v2b`). Image: `dev_games_idle_opponent.png`.
- Development games against SimpleAI / BARb easy: all lost, 4.6 to 13.3 minutes (one more
  ended at 19.3 minutes after its policy had stopped at 4:37).
  Image: `dev_games_live_opponents.png`.

## 5. Problems found by playing games

- **Own bot ordered to attack the own commander** (`unit-v2a` vs BARb easy, lost at 4:37).
  Now each targeted order type may only point at the side it pointed at in the training
  data, and never at the unit itself.
- **Commander stuck behind a GUARD order** (12 orders in 10 minutes): a guard never ends, so
  orders queued behind it never start. Now a guarding or patrolling unit can get a new order
  after 30 seconds.
- **Policy timeouts**: in 5 of the 16 games played with `unit-v2a` / `unit-v2b` (10
  development games, 6 pilot games), one reply did not arrive
  within the 3 s budget and the bridge stopped asking (the rule from Roshan's contract).
  The replies just before took 14 to 62 ms. In the one game checked with the new server
  log, the failed request never reached the model code. The worker opens a new connection
  from WSL to Windows for every request. The cause is not confirmed.
- **First overnight training did nothing**: the run stalled in its first measurement from
  03:48 to 15:38 while holding about 20 GB of GPU memory. Cause not confirmed; training now
  has a memory cap and every background job a time limit.

## 6. Images in this folder

| File | What it shows |
|---|---|
| `harness_diagram.png` | the path of one decision and what is written per game |
| `pilot_win_rate.png` | pilot: games won / lost / reached the cap, per policy and opponent |
| `first_model_orders.png` | the first model's 334 orders in one 4 minute game, by what became of them |
| `replay_first-model_simple-2\*.png` | screenshots from the first model's pilot game `simple-2` (same three views every 2 game minutes) |
| `pilot_game_length.png` | pilot: game length per game and policy |
| `pilot_orders.png` | pilot: orders given per game |
| `pilot_killed_value.png` | pilot: value killed per game |
| `training_curve_unit-v2a.png`, `training_curve_unit-v2b.png` | order type predicted right on held-out matches during training |
| `dev_games_idle_opponent.png` | finished units and orders in 10 minutes against the idle opponent |
| `dev_games_live_opponents.png` | game length against SimpleAI and BARb easy (development games) |
| `replay_unit-v2b_barb-easy-2\*.png` | screenshots from the replay of pilot game `barb-easy-2` (learned policy = blue, reached the 20 minute cap): every 2 game minutes the base from close, the base from further away, the whole map |
| run folders' `income.png` | income over time for any single game (already known to the team) |

The scripts that made the images are in the same folder (`make_charts.py`,
`make_diagram.py`, `hpml_replay_shots.lua`, `take_replay_shots.ps1`).
