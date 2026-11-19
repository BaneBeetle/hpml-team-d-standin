# HPML BAR project, Team D: local stand-in work (snapshot of 2026-11-19)

This is a copy of what was built locally on Brian's PC for Team D (closed-loop evaluation).
It is here so a teammate can read it. It is **not** the team repository and nothing in it
has been merged into `Na00s/hpml`.

Everything is a **stand-in**: local test fixtures and our own test models, made because no
team had a checkpoint we could run. Nothing here is a result of Team A, B or C.

Most of the code and notes were written in AI-assisted sessions (Claude Code). Under the
course's AI policy that use has to be disclosed, and Brian has to be able to explain every
line before any of it goes into the team repository.

## Where to start reading

| File | What it is |
|---|---|
| `shared/status/slides_2026-11-18/UPDATE_SUMMARY.md` | the short version: what is new, the win-rate table, the model, the problems found |
| `shared/status/team-d.md` | the full log, newest sections first: every run folder, every number, every change |
| `shared/status/benchmark/pilot-v1/table.md` | the EVAL-03 pilot table (six pinned games per policy) |
| `shared/status/slides_2026-11-18/*.png` | charts; `compare_first_vs_new/` has one image per number |

## What is in here

| Folder | What it is |
|---|---|
| `standin_eval/fullgame/` | a checkpoint plays team 0 of a headless BAR game: `run_fullgame.ps1`, the spectator widget, the bridge, `run_game.py`, `run_settings.py` |
| `standin_eval/unit_policy/` | our own test model ("unit policy"): dataset builders, model, trainer, policy server, game-set script |
| `standin_eval/benchmark/` | the EVAL-03 pilot: game lists (`*_suite.json`), `run_benchmark.py`, `make_table.py` |
| `standin_eval/standin_model/` | the earlier models trained with Team B's B03 script through a wrapper |
| `team-c-standin/` | the stand-in policy server whose HTTP code `unit_server.py` reuses (not Team C's work) |
| `shared/endpoint_adapter.py` | how Roshan's `PolicyWorker` calls the policy server |
| `shared/status/` | notes, per-game result rows (`*.jsonl`), tables, slide material |

## What is not in here

- Roshan's control loop (`scripts/control_loop/`), Team B's `bar_policy` and Team A's data
  scripts: they live in `Na00s/hpml` on their own branches and this code imports them.
- bar-harness itself and its `.env` pins (engine `2026.09.02`, BAR commit `3510e77`; both are
  written into every run's `run_settings.json`).
- Checkpoints, datasets, recordings, run folders and replays (several GB, local only).
- Most of the replay screenshots (two per replayed game are here: the first model, the
  second model, the win against the idle opponent, the win against SimpleAI).

## It will not run from this copy as it is

The code expects this layout on disk, which this repository does not reproduce:

    bar-standins/
      team-d/          a checkout of Na00s/hpml with standin_eval/ inside it
      team-c/standin_infer/
      shared/          endpoint_adapter.py, ckpt/, data/, status/

and Docker in WSL with bar-harness set up. `shared/status/team-d.md` has the commands that
were run. Making it run from a fresh clone has not been done.

## State of the results (2026-11-19, early morning)

Two games have been won: one against the idle opponent and one against SimpleAI
(`UPDATE_SUMMARY.md`, section 7). The setup that beat SimpleAI won 1 of its first 18
pilot-style games, and none of the 24 played after two more fixes (12 lost, 12 with no winner
by the 20 minute cap). The built-in BARb in the same seat wins 16 of 23 games of that kind.
The winning setup is two learned models (one for building, one for where the army attacks)
plus one hand-written rule (the army leaves in groups). The numbers, the fixes made along the
way and what was not checked are in the two notes files above.
