# Public benchmark: re-run our numbers yourself

English · [中文](README.zh.md) · numbers we published: [docs/measured.md](../docs/measured.md) and the
[hold-out report (hc1)](../docs/research/2026-10-29-hc1-holdout.md)

> **The hold-out set is no longer a hold-out set.** Its 10 tasks were kept out of ccx's development until the
> hc1 run (2026-10-29). Now that they are published here, anyone, including us, can tune against them, and models
> trained later may have seen them. Numbers on them from now on are a re-run, not a fresh hold-out result. Our next
> headline claim will come from a new hold-out set built for it.

## What this is

20 real code changes, each with a brief, a starting point and hidden tests that decide right or wrong:

| Set | Tasks | What it was for | Published runs |
|---|---|---|---|
| `holdout` (hc1) | 10: 5 from this repository, 4 from [humanize](https://github.com/python-humanize/humanize), 1 from [itsdangerous](https://github.com/pallets/itsdangerous) | the README's headline (10 tasks × 3 rounds) | [results/hc1.jsonl](results/hc1.jsonl) |
| `r5` (dev set) | 10 from this repository | tuning ccx: a signal, not a claim | [results/r5-dev.jsonl](results/r5-dev.jsonl) |

Each task is the repository at the parent of a merged commit; the brief says what is wrong or missing and the names
the tests use, never the tests' inputs or expected values; the hidden tests are that commit's own test files. One file
per task is in [tasks/](tasks/) (brief, commit, test files, the exact pytest command).

The "arms" are who does the work. The lead is a fresh headless Claude Code (`claude -p`, Sonnet, medium effort):

| `--arm` | r5.py arm | The lead... | Needs |
|---|---|---|---|
| `self` | `self` | does the change itself | Claude Code |
| `ccx` | `ccx2` | hands it to Codex through `ccx run` (cheapest Codex model first, review on, a targeted `--check`) | Claude Code, Codex, a dedicated Codex home |
| `builtin` | `builtin` | hands it to Claude Code's built-in sub-agent (a Haiku worker) | Claude Code |

The engine is [scripts/eval/r5.py](../scripts/eval/r5.py); [run.py](run.py) only picks its arguments and prints the
table. Every unit runs in a clean room: a fresh copy of the repository, its own temporary HOME, hub and git identity,
the lead without your settings, hooks, CLAUDE.md or memory, reads of your real home folders denied. Before the first
unit, r5.py checks the machine and refuses to start if anything would make the numbers unfair (see "If it refuses").

## Install

You need git, Python 3.11+, and [Claude Code](https://docs.claude.com/en/docs/claude-code) logged in (`claude` on your
PATH). The `ccx` arm also needs [Codex CLI](https://github.com/openai/codex). You do **not** need to install ccx:
the evaluation runs it from this checkout.

```bash
git clone https://github.com/SUPERD6/relayline.git
cd relayline
python -m venv .venv
```

Activate it (`source .venv/bin/activate`, or `.venv\Scripts\activate` on Windows), then:

```bash
python -m pip install pytest freezegun
```

Keep the full git history (no `--depth`): this repository's tasks start from old commits. The external tasks clone
humanize and itsdangerous from GitHub at the start of a run (network needed once); their tests run with this same
Python, which must not have `humanize` or `itsdangerous` installed.

## Run the `self` arm (the cheapest)

One unit first, to check your setup (about $0.03–0.15, plus a few cents for the canary: one tiny Haiku request that
checks the isolation before anything else is spent):

```bash
python bench/run.py run --set holdout --arm self --tasks hz-intword-carry
```

Then the whole hold-out set, one round (10 units; about $1 at our prices, 21 s median each):

```bash
python bench/run.py run --set holdout --arm self --budget 3
```

`--dry-run` prints the schedule and a cost estimate and runs nothing. `--rounds 3` matches hc1. Units run one at a
time by default (`--jobs 1`), so wall times are not slowed by each other. Anything after `--` goes to r5.py as it is
(`python scripts/eval/r5.py run -h`).

## Run the `ccx` arm

Codex must not see your own settings, so the evaluation uses a separate Codex home that you log in to once:

```bash
mkdir ~/codex-eval-home
CODEX_HOME=~/codex-eval-home codex login
```

(PowerShell: `$env:CODEX_HOME = "$HOME\codex-eval-home"; codex login`, then close that window.) Then pass its
absolute path:

```bash
python bench/run.py run --set holdout --arm ccx --codex-home /absolute/path/to/codex-eval-home --budget 3
```

The `builtin` arm needs nothing extra (`--arm builtin`).

## Results

Rows go to `bench/runs/<tag>-results.jsonl` (git-ignored); the tag defaults to `<set>-<commit>`, because r5.py runs
one tag on one commit only. At the end run.py prints the table; for any file:

```bash
python bench/run.py table bench/runs/holdout-abc1234-results.jsonl
python bench/run.py table bench/results/hc1.jsonl
```

which for our hc1 rows prints:

| Tag | Arm | Right | Cost per success | Wall, median |
|---|---|---|---|---|
| hc1 | builtin (Claude Code's built-in sub-agent) | 27/28 | $0.103 | 123 s |
| hc1 | ccx2 (delegated to Codex through ccx) | 29/30 | $0.063 | 61 s |
| hc1 | self (the lead does it itself) | 29/30 | $0.090 | 21 s |

Right = the hidden tests passed. Cost per success = the arm's whole spend over its right units (API-equivalent list
prices, also where a subscription paid). Wall = the true median of the units' wall times. Rows whose clean-environment
check failed (`env_clean: false`) are not counted, and the table says how many.

One row per unit (JSON lines). The fields you need most:

| Field | Meaning |
|---|---|
| `tag`, `taskset`, `round`, `task`, `arm` | which unit |
| `ok` | the hidden tests passed |
| `pytest` | the last line of their output |
| `usd`, `lead_usd`, `ccx_usd`, `sub_usd` | spend: all, the lead's, ccx's runs, the delegated part |
| `wall_s` | wall time of the unit, seconds |
| `lead_model`, `lead_effort`, `lead_requests`, `lead_tokens` | the lead and how much it used |
| `env_clean`, `fingerprint` | the clean-environment result; commit, CLI versions, Python, OS, isolation |
| `timeline` | seconds, $ and tokens per role and reason |

Your rows also keep fields we removed from the published ones (local paths, run ids); don't publish them as they are.
`python scripts/eval/r5.py export <file.json> --taskset holdout --results <your file> --include-unclean` writes a scrubbed copy, which is
how [results/](results/) was made (`*-summary.json` there is r5.py's own summary: paired tests, intervals, per
repository).

## Compare with ours

- Hold-out: [results/hc1.jsonl](results/hc1.jsonl), 90 rows, commit `b473976`, Windows, Claude Code 2.1.309, Codex
  CLI 0.164.0, Sonnet medium lead. The [hc1 report](../docs/research/2026-10-29-hc1-holdout.md) has the
  pre-registration, every deviation, the paired intervals and eight limits.
- Dev set: [results/r5-dev.jsonl](results/r5-dev.jsonl), tags r5 to r6a (before the clean-environment checks, except
  r6a); [docs/measured.md](../docs/measured.md) says which tags each published row uses.

What to expect from a re-run: 10 units is a small sample. In hc1 the per-task interval of a difference between two
arms was about ±3 right answers out of 30, and costs move with the model versions and prices of the day. Compare
the same arms run by you at the same time, not your one arm against our table. A ccx row is also not hc1's: ccx runs
from your checkout, which is newer than `b473976`.

Known limits (details in the hc1 report): this repository's tasks may have their answers in the ccx code that ccx
runs from (its own checkout is readable to Codex), so the external-repository tasks are the clean ones; external
commits from before a model's training cut-off may be remembered; only a Sonnet medium lead was measured; the
published runs were on Windows only. The Linux and macOS paths of r5.py (process cleanup without a Job Object)
were written but not run for real: experimental.

## If it refuses

r5.py refuses to start, and says why, when for example: another evaluation, pytest, `claude -p` or `codex exec` is
running on the machine; the checkout has uncommitted changes in tracked files or new files in `ccx/`, `scripts/`,
`config/` or `skills/`; the `ccx` arm has no `--codex-home` or it has no login; the canary lead sees your own
instructions. `-- --force-unclean` runs anyway and marks every row `env_clean: false`, so the table leaves them out.

## Licence and what is copied

This repository's tasks and everything in `bench/` are MIT, like the rest of relayline. The external tasks are only
pointers: repository URL, the full commit, the test file's path. Nothing of humanize (MIT) or itsdangerous
(BSD-3-Clause) is copied here; r5.py fetches them from GitHub when you run, and their code and tests stay under their
own licences. The hidden tests are public, as they always were in each commit's history: an agent that may look the
commit up can find the answer, which is why the evaluation denies its agents Claude's web tools and the copies of the other repositories.

## Files

| Path | What |
|---|---|
| `tasks/holdout/*.md`, `tasks/r5/*.md` | one task per file, written by `make_tasks.py` from `scripts/eval/tasks_holdout.py` and `tasks_r5.py` (the source of truth; the tests check they agree) |
| `run.py` | `run` (calls r5.py) and `table` |
| `results/*.jsonl`, `results/*-summary.json` | our published rows and r5.py's summary of them, scrubbed |
| `runs/` | your rows (git-ignored) |
