# Polyglot slice: an outside benchmark with a difficulty spread (plan, 2026-10-30)

English · [中文](2026-10-30-polyglot-slice-plan.zh.md) · back to [research reports](README.md)

**Status: plan and harness only; no number below is a result.** The pre-run (one unit, to prove the chain) is
recorded at the end.
When results exist they go in this file, and any number quoted elsewhere carries "outside benchmark, 30 exercises,
one round".

## Why

On the hold-out run hc1 ccx2 was as right as doing it yourself (29/30) and about 30 % cheaper, but "more right" had no
evidence: every task was one the cheap model already solved, so routing, review and climbing a rung had nothing to
show. This slice adds tasks that are known to be hard for some models, from a benchmark ccx was not built on.

## Source and licence (checked 2026-10-30)

| | |
|---|---|
| Benchmark | aider's polyglot benchmark, [Aider-AI/polyglot-benchmark](https://github.com/Aider-AI/polyglot-benchmark) |
| Pinned commit | `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f` (2024-12-22, the head of `main` on 2026-10-30) |
| How aider chose its 225 | of 697 Exercism exercises in six languages, those solved by 3 or fewer of 7 models in 2024 ([aider blog, 2024-12-21](https://aider.chat/2024/12/21/polyglot.html)) |
| Licence | the repository has no LICENSE file; its README says the exercises are copyright Exercism and used under Exercism's open-source licences. The Python track ([exercism/python](https://github.com/exercism/python)) is MIT. Nothing of the exercises is copied into this repository: they are fetched when a run starts |

## The 30 exercises and how they were chosen

All 34 Python exercises of the benchmark, minus the 4 lowest by (Exercism difficulty, number of tests): list-ops,
robot-name, proverb, transpose. The list, each exercise's difficulty, test count and reason, and the dropped four are
in [`scripts/eval/polyglot_selection.json`](../../scripts/eval/polyglot_selection.json). The choice read only each
exercise's `.meta/config.json`, its test files (to count tests), its instructions' length and Exercism's difficulty
rating; no `.meta/example.py` or `.approaches/` (the solutions) was opened.

Python only: Go and Node.js are not installed on the machine that runs the eval, so a JS or Go part could not be
pre-run; it is left for later.

**The difficulty spread is a hypothesis, not a measurement.** aider publishes pass rates per model, not per exercise,
so no exercise's rate for today's cheap models is known. The `direct` arm (Codex gpt-6-luna low, no lead) measures it
in the first run. Pre-registered: if `direct` gets 27/30 or more, this slice is at the ceiling as well, and we say so
instead of claiming anything about routing.

## What a unit sees

- The repository: the exercise's solution stub(s) only, in a fresh one-commit repository (no `.meta/`, `.approaches/`,
  `.docs/`, tests or history).
- The brief: the exercise's own instructions (introduction, instructions, instructions.append, in aider's order) and
  an addendum like aider's: which file to change, keep the names, standard library only, the tests are hidden and
  only the solution file is scored.
- Before a run, `python scripts/eval/polyglot_check.py` checks that every exercise's hidden tests can grade it,
  scored exactly as a unit is: the untouched stub must fail and the exercise's own example solution must pass (the
  checker reads the example out of a temporary clone; it never reaches a unit).
- The hidden test: the exercise's test files. Scoring copies only the solution files into a fresh folder with the
  tests and its own `pytest.ini`, so nothing else the agent wrote (its own tests, `conftest.py`, pytest settings,
  modules that shadow the standard library) applies. Right means pytest's summary shows exactly the exercise's
  number of tests passed and nothing skipped, failed or errored (a solution that skips the module or exits 0 at
  import is not right). A missing solution file is a failure. 300 s limit.
- The rest is round 5's clean room as for the hold-out set's other repositories: one clone before the canary, read
  into memory and removed; the copies and Claude's web tools denied; pip has no index; the audit flags fetch commands
  that name exercism, problem-specifications or the benchmark repository.

Unlike aider (two tries, the second shown the test errors), there is one try and the tests stay hidden, so rates are
closer to aider's first-try rate.

## Arms (the default for `--taskset polyglot`)

| Arm | Who does the work |
|---|---|
| `self` | the lead (Claude Code, Sonnet medium) does it |
| `ccx2` | the same lead hands it to ccx as the agent-delegate skill says (save tier: Codex gpt-6-luna low first, climbs a rung when ccx's `--check` fails) |
| `direct` | no lead: `ccx run` straight to Codex gpt-6-luna low with review, `--minutes 60`, no `--check`, no climbing (round 5's direct arm unchanged) |

The same instructions, the same hidden tests and the same clean room for all three; the lead prompt names no
benchmark. What differs is how the work is done, which is the point:

- An exercise has no test files for ccx2's `--check` to name, so for exercises its lead is told to have the
  sub-agent write a test file of its own next to the solution and pass that as `--check` (e.g.
  `python -m pytest -q test_own.py`). That check is the sub-agent's own, so it can pass on a wrong answer; self's
  lead, told by the addendum to "write and run checks of your own", is in the same position.
- ccx2's lead passes the brief with `--brief-file` (the instructions are long and full of backticks and `$`, which a
  shell expands inside double quotes); the sub-agent gets the lead's copy of the instructions, as in every ccx2 run.
- direct has no lead, so it gets the instructions as its brief without the lead prompt's two lines about the folder.

## The first run (scheduled by the lead session, not run yet)

```bash
python scripts/eval/polyglot_check.py                       # every exercise grades right (free)
python scripts/eval/r5.py run --taskset polyglot --rounds 1 --tag pg1 --arm-order balanced --budget 15 \
    --codex-home <eval codex home>
python scripts/eval/r5.py summary --taskset polyglot --tag pg1
```

90 units. The dry run estimates about $11 from round 5's per-unit means, which came from tasks in a whole code base;
an exercise is one file, so it should cost less (the pre-run unit is the first measurement). `--budget 15` leaves
room so that a budget stop does not leave unfinished pairs; with `--arm-order balanced` each exercise's three units
run one after another.

Pre-registered (written before the run, not changed afterwards):

- Primary metrics, as for hc1: right/30 per arm (hidden tests, Wilson 95 % interval), $ per success, median wall time.
- Ceiling: `direct` ≥ 27/30 means this slice shows nothing about routing; report it and stop there.
- "Routing adds correctness" may be written only if ccx2's right count is above direct's and the paired McNemar
  test (Holm over the three pairs, as `r5.py summary` prints) has p < 0.05; otherwise report the counts and
  intervals as a direction, not a finding. ccx2 vs self is reported the same way (no claim of more right than self
  without that test).
- Cost and wall time are reported, not tested. One round is a signal, not proof.

## Limits (quote them with any number)

1. Exercism exercises and their solutions are public and probably in every model's training data; all arms alike.
2. 30 exercises, one language, one round, one lead model.
3. The difficulty spread is unknown until `direct` has run (see above).
4. A solution file runs in the scoring process: one that patches the test framework at import could cheat. Every
   exercise unit keeps its final diff (right or not, under the results file's `-artifacts/` folder), so such a case
   can be found by reading them.
5. Amounts are API-equivalent prices.

## Pre-run

(To be filled: the one unit run to prove the chain, its result and cost.)
