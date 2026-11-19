# BAR stand-in contract (reconciled against Na00s/hpml, 2026-11-16)

status: reconciled

verified by Team D session, 2026-11-16: every statement below was checked against the code on
`standin/team-d` (same commit as `standin/base`, 9d25a4c), the saved traces in
`evidence/policy_timeouts`, `shared\data` and `shared\ckpt`. Changed in this pass:
(1) the policy gets the raw request with Lua floats and must echo integers, (2) the request
envelope also carries `timing_mode` and `decision_interval_frames`, and only some fields are
validated, (3) exact response rules from `validate_response`, (4) the full list of episode
statuses, (5) the DATA-01 `state` and the live `observation` have the same keys (the old text
said the data had extra ones), (6) `predict_orders` returns `None` without an error when given
the whole request instead of its `observation`, and formation orders carry `params_per_unit`,
(7) test counts re-run. Nothing else needed changing.
Added later the same day, from the Team C stand-in session's notes: (8) the two sources of
"my team" (envelope `team_id` vs `observation.teamID`), in the checkpoint section.

This file points at the real interfaces. It defines nothing new except the short
"glue rules" section, which is provisional and local to the stand-ins.
Where this file and the code disagree, the code wins: fix this file and say so in your status file.

Everything produced under `C:\Users\lolly\bar-standins` is a local test fixture.
Tag stand-in outputs `"source": "standin"` where the format has room for it,
and never present them as another team's result.

## Changed from v0

- The v0 HTTP API (`/act`, `bar-obs/v0`, `bar-act/v0`) is dropped. Roshan's EVAL-01
  boundary already exists and is not HTTP: a policy object with `reset(request)` and
  `predict(request)`, built by a factory inside `PolicyWorker`.
- The v0 observation and action shapes are dropped. The observation is the exporter's
  `state` object; the action is one explicit `noop` or one `order` per decision.
- `bar_contract.py` and `featurize_v0` are dropped. Validation is Roshan's
  `scripts/control_loop/protocol.py`; featurization is Team B's `bar_policy.features`.
- Mock data is dropped. Team A's real DATA-01 match is committed on `origin/team-a`.
- The toy MLP is dropped. Team B's real B03 training script produces the checkpoint.
- Decision interval (15 frames, 2 Hz sim time) matched v0. The response budget is
  3 s wall clock (`policy_timeout_seconds`), not 50 ms, and a late reply fails the
  episode. It is never replaced by a no-op.

## Where things are

| What | Where |
| --- | --- |
| Base code for every worktree | local branch `standin/base` = `origin/rk3293/eval01-local-control-loop` + `origin/team-b/b03-baseline` + `origin/team-a`, merged cleanly, never pushed |
| Worktrees | `C:\Users\lolly\bar-standins\team-c` (`standin/team-c`), `...\team-d` (`standin/team-d`) |
| Shared folder | `C:\Users\lolly\bar-standins\shared` (`data\`, `ckpt\`, `status\`, `logs\`) |
| Brian's own full-game harness | `C:\Users\lolly\OneDrive\Desktop\Projects\bar-harness` (not in Na00s/hpml; runs in WSL Ubuntu-24.04 Docker) |

## Policy boundary (Team D <-> Team C): Roshan's protocol v1

Source of truth: `docs/policy-contract.md`, `docs/control-loop.md`,
`scripts/control_loop/protocol.py`, `examples/control_loop/*.json`.

- Request envelope, as the widget writes it: `protocol_version` (1), `op` (`reset` | `predict`),
  `match_id`, `generation`, `player_id`, `team_id`, `decision_id`, `source_frame`,
  `scheduled_frame`, `observation_phase`, `timing_mode`, `decision_interval_frames`,
  `observation`, `catalog`. `validate_request` checks `protocol_version`, `op`, `match_id`,
  the five integer ids, `observation.units` and `catalog`. It does not check `scheduled_frame`,
  `observation_phase`, `timing_mode` or `decision_interval_frames`; they pass through.
- `reset` has `decision_id` 0 and carries an observation and the catalog like a predict.
  Predict ids start at 1. `PolicyWorker.submit` refuses a predict unless a reset for the same
  (`match_id`, `generation`, `player_id`, `team_id`) completed first and `decision_id` is
  higher than the last completed one.
- `observation` (from `conservativeView` in `lua/bar_proof_common.lua`):
  `{ "teamID", "allyTeamID", "resources", "visibility", "units": [ { "id", "teamID", "defID",
  "position": [x, y, z], "health", "maxHealth", "buildProgress", "capture", "paralyze",
  "los", "queue" } ] }`. Allied units plus enemies in current line of sight. The files in
  `examples/control_loop` show a shorter unit (`id`, `teamID`, `defID`, `position`, `health`,
  `buildProgress`); only `id`, `teamID` and `defID` are validated.
- Lua writes every number as a float, including the envelope ids (`"protocol_version": 1.0`,
  `"source_frame": 45.0`). `PolicyWorker.submit` sends the policy the raw request, not the
  normalized one. The reply must echo integers: a reply that echoes the raw `1.0` fails with
  `Mismatched response protocol_version`. So a policy calls `validate_request(request)` first
  and builds its reply with `protocol.response(normalized, action)`, as `ScriptedPolicy` does.
- `catalog`: ids and goals of Roshan's fixture scenario (`builder_id`, `attacker_id`,
  `target_id`, `build_def_id`, `move_command`, `attack_command`, `move_goal`, `build_goal`).
  `validate_request` requires it today. It is fixture-specific.
- Response: echoes `protocol_version`, `match_id`, `generation`, `player_id`, `team_id`,
  `decision_id`, `source_frame` and `op`, plus `status` (`ok` | `error`).
  For `predict` with `ok`: `action` = `{"kind": "noop"}` or
  `{"kind": "order", "unit_id": int, "command_id": int, "params": [finite numbers], "options": int >= 0}`.
  The recipient must be an observed unit owned by `team_id`. Negative `command_id` = build that unit def.
  Checked against `validate_response`: `command_id` must be a Python `int` (`10.0` is rejected);
  `unit_id` and `options` must be whole numbers >= 0 and `options` is required; `params` is a
  list (may be empty) of finite numbers, so `None` is rejected; a `unit_ids` list is rejected;
  extra keys in `action` are accepted. A `status: "error"` reply raises `PolicyError`.
- Validate with `validate_request(message)` and `validate_response(request, reply)`. Do not fork them.
- Plugging in a policy: `PolicyWorker(factory=<importable callable returning an object with reset/predict>)`.
  The factory runs inside the worker process. `scripts/run_control_loop.py` currently always
  uses the default `ScriptedPolicy`, so choosing a factory needs a small local change there.
- Timing: 30 Hz sim, a decision every 15 frames. `stepped` mode pauses the sim while a reply is
  pending; `paced` does not. Budget 3 s for reset and predict (`configs/control_loop.json`).
  The budget clock starts when the supervisor reads the request line and is checked again just
  before the reply is published to the engine. The supervisor loop sleeps 10 ms per pass and the
  worker polls its mailbox every 5 ms, so live round-trip times include that polling.
- Episode statuses in `engine.py`: `completed` (fixture GameOver), `policy_timeout`,
  `policy_error`, `protocol_error`, `policy_worker_crashed`, `worker_crashed` (engine exited),
  `startup_timeout`, `run_timeout`, `frame_timeout`, `failed` (OSError/ValueError), `interrupted`.
  `case_passed` in `result.json` is a separate field from `episode_status`.
- Two ways a policy fault becomes `policy_error`: the policy returns a `status: "error"` reply,
  or it raises. On a raise the worker child writes `error.txt`, reports the error and leaves its
  serve loop. Either way the episode ends and `run_episode` closes the worker.

## Data (Team A -> Team B)

- `shared\data\state_command_pairs.jsonl`: Team A's real DATA-01 match `d2b6b16a...`,
  unpacked from `output/data-01/full-a/paired/state_command_pairs.jsonl.gz` on `origin/team-a`.
  2,802 rows, sha256 `803f8c8f...` (see `shared\data\manifest.json`). Map: Great Divide V1.
- Row keys: `state_frame`, `state_phase`, `action_frame`, `player_id`, `view_team`,
  `alignment`, `state` (the same keys as the live control-loop `observation`, top level and per
  unit; checked on row 0 against a saved `policy_request`), `action` (`command_id`, `command_name`, `unit_ids`, `params`, `options`, `pairwise`, ...).
- Docs: `docs/data-01/README.md`, `docs/data-02-field-inventory.md`, `schemas/observation_field_inventory.json`.

## Checkpoint (Team B -> Team C)

- `shared\ckpt\b03-h1\h1_best.pt`, format `b03-h1-checkpoint-v1`, written by Team B's own
  `scripts/b03_report.py train` on the data above (CPU, about 2 minutes, seed 0 selected,
  val loss 14.240, the same number as `docs/b03/README.md`). `train.json` beside it is the run record.
- Load and use (from `docs/b03/README.md`):

  ```python
  from bar_policy.training import load_checkpoint, predict_orders
  enc, dec, fspec, aspec, meta = load_checkpoint(path)
  orders = predict_orders(enc, dec, fspec, aspec, rows, map_name="Great Divide V1")
  ```

  A row may be a pair row or a bare `state`/`observation` object; both were checked.
  Pass `request["observation"]`, not the request: given the whole request envelope,
  `predict_orders` returns `None` and raises nothing (it looks for `teamID` and `units` at the
  top level of the row, and the envelope has neither there).
- Two sources of "my team": the protocol decides ownership with the envelope's `team_id`
  (`validate_response`), Team B's featurizer decides it with `observation.teamID`
  (`bar_policy/features.py`, `_unpack`). They were equal in every request seen. If they ever
  differ, glue rule 2 turns the order into a noop. (Found by the Team C stand-in session.)
- A formation order (`"pairwise": True`) has one more key, `params_per_unit`, and `params` is
  the first recipient's entry.
- Measured here: on the 77 saved fixture requests in `evidence/policy_timeouts/0824f030...`
  the checkpoint decoded `BUILD_UNITDEF_506` 77 times (73 for unit 9983, 4 for unit 28820).
- One decoded order looks like:
  `{"command_id": -506, "command_name": "BUILD_UNITDEF_506", "unit_ids": [20267], "params": [2752.0, None, 320.0, 0.0], "options": 32, "pairwise": False}`.
  A row with no own units gives `None`.
- It is a weak policy. Greedy decoding gives the majority order type (a build) almost every
  time. That is Team B's stated B03 result, not a stand-in bug.

## Glue rules (provisional, stand-in only): decoded order -> protocol action

These fill gaps between the two real interfaces. Each one is an open question for the
real teams, so keep them in one small function and log every time a rule fires.

1. `None` from the model -> `{"kind": "noop"}`.
2. Recipients: the protocol takes one `unit_id`, the model returns a list. Send the first
   id that is an observed unit owned by `team_id`; if none is, send `noop`. Log the dropped ids.
3. `params` may contain `None` for y (the model leaves height to the executor). Replace it
   with the recipient's observed `position[1]`. Never send `None`.
4. Cast `command_id`, `unit_id` and `options` to `int`. Pass everything else through unchanged.
   (`predict_orders` already returned `int` for all three in the rows checked; the cast is a guard.)
5. An exception inside the policy -> a `status: "error"` reply with the message. Never a silent no-op.

## Known mismatches and open questions

- Unit def ids depend on the game version. The checkpoint's vocabulary comes from the DATA-01
  replay's BAR version; Roshan's fixture pins BAR `test-31368-8379d65`. Def 506 may not be the
  same unit in both. (For Team A / SHARED-01 #14.)
- Multi-unit orders, formations (`pairwise`) and queue options are not in protocol v1.
  They belong to EVAL-02 (#10). (For Roshan.)
- `catalog` is required by `validate_request` but only means something in the fixture. (For Roshan.)
- The fixture's pass checks (move, build, attack effects) are written for the scripted policy.
  A learned policy will not satisfy them. Record what happened; do not relabel it a pass.
- Engine pins differ: Roshan's loop uses Recoil 2026.07.04 on Great Divide V1, Brian's
  `bar-harness` uses 2026.09.02 on Supreme Isthmus v2.1. (For Jon / EVAL-03 #11.)
- Roshan's launcher (`scripts/run_control_loop.ps1`) expects Docker Desktop on Windows. This
  machine has Docker only inside WSL Ubuntu-24.04. The policy worker runs inside the container,
  where `127.0.0.1` is the container itself, not Windows.
- On this Windows machine 3 of 257 repo tests fail on `standin/base` (239 pass, 15 skip):
  `test_action_decoder::test_formation_location_depends_on_recipient` (Team B),
  `test_data05_completion::test_parallel_capture_cli_fails_before_starting_work` and
  `test_visibility::test_probe_preparation_is_isolated_and_refuses_existing_output` (Team A).
  The merge did not change `bar_policy` or that decoder test. Whether the two Team A tests
  also fail on the unmerged `origin/team-a` was not checked. All control-loop tests pass.
  Do not fix other teams' tests. Re-run on `standin/team-d` 2026-11-16: the same 3 failed,
  239 passed, 15 skipped; the six control-loop test files alone: 46 passed.
- Measured live on 2026-11-17 (details in `shared\status\team-d.md`): with Docker inside WSL,
  the worktree is mounted from `/mnt/c` and episode output must go to a Linux filesystem
  (`--output runtime/output/control_loop`); on the `/mnt/c` mount one run failed with
  `OSError: [Errno 61] No data available`. A host-network container reaches a server on
  Windows `127.0.0.1` (WSL mirrored networking). `scripts/run_control_loop.py` on
  `standin/team-d` now has an optional `--policy-factory MODULE:CALLABLE`.
- The repo's `AGENTS.md` says deliverables must be pushed to GitHub. Stand-in work is not a
  deliverable and is never pushed (Brian's rule for these sessions).
- `bar-harness` pins (from its `.env` and README): Recoil 2026.09.02, BAR commit `3510e77f`,
  BARb vs BARb on Supreme Isthmus v2.1. Roshan's pins (from `scripts/prepare_control_loop_runtime.py`):
  Recoil 2026.07.04, `Beyond All Reason test-31368-8379d65`, Great Divide V1.
