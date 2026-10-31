# External benchmark pg1: 30 polyglot Python exercises, self vs ccx vs direct (2026-10-31)

English · [中文](2026-10-31-polyglot-pg1.zh.md) · back to [research reports](README.md) · the
[plan](2026-10-30-polyglot-slice-plan.md) (rules fixed before the run)

**On 30 polyglot Python exercises, delegating to the cheapest tier passed 12/30 vs 25/30 self, ~3× cost/success.
Don't delegate small strict-interface tasks; savings appear only on costlier repo tasks.**

Three findings:

1. **On small single-file exercises, handing the work to the cheapest tier was both less often right and about 3×
   dearer per success.** This does not say ccx got worse overall, and it does not contradict
   [hc1](2026-10-29-hc1-holdout.md): delegating saves money only when doing it yourself is expensive *and* the
   sub-agent is as right. hc1's repository tasks met both; pg1 met neither.
2. **It was dearer because the tasks are small, not because they are hard.** 82 % of ccx2's spend was on the lead's
   side (writing the brief, the call that waits, accepting the result). The lead's side alone had a median of $0.035
   per task, already above self doing the whole task ($0.027). Even if the sub-agent had been right every time,
   ccx2 would have cost $0.046 per success against self's $0.037. No feature that can be computed before handing the
   work over predicted which exercises the sub-agent would fail.
3. **Review and fix rounds did not help, and the tier never climbed.** ccx2's check ran the sub-agent's own
   `test_own.py`: it passed in 30 of 30 units, including all 18 whose hidden tests failed. Every route was Codex
   gpt-6-luna low.

## Method

- **Tasks**: 30 Python exercises of aider's polyglot benchmark (commit 7e0611e, 2024-12-22), chosen without looking
  at any solution: aider's 225 hardest exercises (solved by at most 3 of 7 models in 2024) include 34 in Python; the
  4 lowest by (Exercism difficulty, number of tests) were dropped. The list and the reason for each is
  `scripts/eval/polyglot_selection.json`; the task set is `scripts/eval/tasks_polyglot.py`.
- **What a unit sees**: a fresh one-commit repository with the solution stub only (no tests, `.meta/` or history),
  the exercise's own instructions and a short addendum (which file, keep the names, standard library only, the tests
  are hidden).
- **Arms**, all with the same instructions, hidden tests and clean room:

| Arm | Who does the work |
|---|---|
| `self` | the lead, Claude Code Sonnet medium, does it itself |
| `ccx2` | the same lead hands it to ccx (save tier: Codex gpt-6-luna low first, climbs a rung when ccx's `--check` fails); an exercise has no test file to name, so the lead has the sub-agent write `test_own.py` and passes that as `--check`; another vendor's model reviews |
| `direct` | no lead: `ccx run` straight to Codex gpt-6-luna low with review, no `--check`, no climbing |

- **One round** (tag `pg1`, run 20261031-145737Z, ccx pinned at 5d4bd01, codex-cli 0.164.0, Claude Code 2.1.309), 90
  units, `--arm-order balanced` (each exercise's three units one after another). Codex's Windows sandbox ran
  **unelevated** (the one-unit pre-run pg0 was elevated); this setting is from the run's set-up, the rows do not
  record it. An earlier, aborted attempt (sandbox credentials no longer valid) is not used.
- **Scoring**: the exercise's test files are hidden; only the solution file is copied into a fresh folder with them.
  Right means pytest passed exactly the exercise's number of tests. **One try**: unlike aider (two tries, the second
  shown the errors), nothing sees the hidden tests before scoring.
- **Two counts** everywhere: all 30 exercises, and the clean rows only (`env_clean`, what `r5.py summary` counts).
  Three rows are not clean, because other processes on the machine (other sessions' tests and ccx runs) were seen
  while they ran:

| Row left out of the clean count | Right | Effect |
|---|---|---|
| `pg-book-store` self | yes | timing only; grading is the same |
| `pg-book-store` ccx2 | no | timing only |
| `pg-scale-generator` direct | no | timing only |

So the clean count has 29 units per arm, 29 self–ccx2 pairs and 28 pairs for each pair with direct.

**How the numbers were computed.** Every number below comes from `.ccx/eval/r5/pg1-results.jsonl` (one row per
unit, kept on the machine that ran it, not in the repository), recomputed with a separate script that does not import
`scripts/eval/r5.py`:

```bash
python scripts/research/polyglot_pg1.py .ccx/eval/r5/pg1-results.jsonl --out docs/research/data/2026-10-31-polyglot-pg1.json
```

The output, with one scrubbed row per unit (no paths), is
[data/2026-10-31-polyglot-pg1.json](data/2026-10-31-polyglot-pg1.json). The clean-count values match what
`r5.py summary --taskset polyglot --tag pg1` prints. Sign tests are exact two-sided binomial tests on the discordant
pairs (McNemar's exact test); the bootstrap resamples the 29 (or 30) tasks, 2000 times, seed 31. Two things are not
fields of the rows and say so where they appear: the failure coding (from each unit's hidden-test output) and what
the verifiers read in the run logs.

## Results

| Arm | Right, all 30 (Wilson 95 %) | Right, clean | Total spend, all / clean | Cost per success, all / clean | Wall time, median, all / clean |
|---|---|---|---|---|---|
| self | **25/30** (0.66–0.93) | 24/29 | $0.915 / $0.871 | **$0.037** / $0.036 | 11.1 s / 10.8 s |
| ccx2 | 12/30 (0.25–0.58) | 12/29 | $1.381 / $1.341 | $0.115 / $0.112 | 57.4 s / 57.4 s |
| direct | 9/30 (0.17–0.48) | 9/29 | $0.187 / $0.175 | $0.021 / $0.019 | 44.2 s / 43.9 s |

The plan's ceiling rule (direct ≥ 27/30 means the slice shows nothing about routing) did not fire: direct was 9/30.

### Paired right answers

| Pair | All 30: only A / only B (p) | Clean: only A / only B (p) | Holm over the three pairs, all / clean |
|---|---|---|---|
| self vs ccx2 | 13 / 0 (p = 2.4e-4) | 12 / 0 of 29 (p = 4.9e-4) | 4.9e-4 / 9.8e-4 |
| self vs direct | 16 / 0 (p = 3.1e-5) | 14 / 0 of 28 (p = 1.2e-4) | 9.2e-5 / 3.7e-4 |
| direct vs ccx2 | 4 / 7 (p = 0.55) | 4 / 6 of 28 (p = 0.75) | 0.55 / 0.75 |

- Self was right on every exercise either delegated arm got right, plus 13 (16) more.
- **ccx2 vs direct is no finding.** ccx2 got three more right (12 vs 9), but p = 0.55. Two of direct's failures
  (`pg-zebra-puzzle`, `pg-bottle-song`) were runs that stopped as `blocked` after 4 s; why is not recorded. Without
  those two it is 4 / 5 (p = 1.0); without them and the unclean row as well, 4 / 4 (p = 1.0). By the plan's rule
  "routing adds correctness" cannot be written.
- On the 28 clean direct–ccx2 pairs, the two arms with the same model and tier came out opposite in 10. One round
  of this is mostly chance.

### Cost and wall time, ccx2 against self (paired by task)

| | Clean, 29 pairs | All 30 |
|---|---|---|
| Total spend, ccx2 ÷ self (95 % CI by task) | **1.54** (1.35–1.75) | 1.51 (1.32–1.71) |
| Cost per success, ccx2 ÷ self (95 % CI) | **3.08** (2.12–5.16) | 3.14 (2.21–5.43) |
| Tasks where ccx2 cost more | 27 of 29 | 27 of 30 |
| Tasks where ccx2 was slower | 29 of 29 | 30 of 30 |
| Wall time, median of per-task differences | +46.3 s | +46.8 s |

## Why it was dearer: the lead's fixed cost

Fields: `lead_usd` (the lead's own model spend) and `usd` (= `lead_usd` + `ccx_usd`, ccx's work runs and reviews) of
each ccx2 row; self's `usd` is all lead.

| | All 30 | Clean 29 |
|---|---|---|
| ccx2: lead's side ÷ total spend | 1.135 / 1.381 = **82.2 %** | 1.101 / 1.341 = 82.1 % |
| ccx2: lead's side, median per task | $0.0346 | $0.0350 |
| self: whole task, median | $0.0275 | $0.0274 |
| Tasks where ccx2's lead side alone cost more than self's whole task | 24 of 30 | 24 of 29 |
| ccx2 cost per success if every unit had been right (total ÷ units) | $0.046 | $0.046 |
| self cost per success, as measured | $0.037 | $0.036 |

On a one-file exercise, writing the brief, waiting and accepting costs the lead about as much as doing it. A
cheaper or better sub-agent cannot remove that: the saving has to come from tasks where doing it yourself is
expensive.

**No feature known before handing work over predicted the failures** (AUC of the feature for "the unit failed",
0.5 = no signal; features from `polyglot_selection.json`; computed in sample):

| Feature | ccx2 failed | direct failed |
|---|---|---|
| Exercism difficulty | 0.57 | 0.54 |
| Number of hidden tests | 0.51 | 0.38 |
| Length of the instructions | 0.34 | 0.62 |

Longer instructions went with fewer ccx2 failures but more direct failures: the direction does not even hold
across the two arms with the same model. Diff size cannot be known before the work. So for routing, the useful
proxy is the expected cost of doing it yourself (files to read and change, expected requests), not diff lines or
instruction length.

## Why it failed

**Interface guesses.** We coded each of ccx2's 18 failures from the first error lines of its hidden-test output
(the coding is ours and is listed in the data file):

| Kind | Count | Examples |
|---|---|---|
| Interface: does the job, but not in the shape the hidden tests expect | **14** | returns a list where a string is expected (`grep`) or the reverse (`food-chain`); takes a string where the tests pass a list (`forth`); raises where the tests expect `False` (`grade-school`); missing constants or methods (`go-counting`, `phone-number`); different error text (`tree-building`, `pov`) |
| Logic: the behaviour is wrong | 4 | `bowling`, `hangman`, `connect`, `paasio` |

These conventions are in the hidden tests only, not in the instructions. The Codex model guessed wrong on both of its
paths (ccx2 and direct); the Sonnet lead guessed right far more often.

- **All three arms wrong (5)**: `pov`, `dot-dsl`, `go-counting`, `paasio`, `tree-building`.
- **ccx2 wrong where direct was right (4)**: `bowling`, `connect`, `food-chain`, `zipper`. In `zipper` and
  `food-chain` the sub-agent wrote `test_own.py` against an interface it invented (tuple trees; one string instead
  of a list of lines). The check passed on those tests and the review let it through, which locked the wrong
  interface in.
- **ccx2 right where direct was wrong (7)**: 2 were direct's 4-second `blocked` runs (`zebra-puzzle`,
  `bottle-song`), 1 an unclean direct row (`scale-generator`, where ccx2 also had a fix round), 3 ccx2 got right on
  its first try (`two-bucket`, `beer-song`, `sgf-parsing`: chance between two runs of one model), 1 after a second
  attempt (`wordy`). At most 2 of the 7 have anything to do with rework.

## Review did not help; the tier never climbed

- **Check**: `ccx_check_passed` is true in 30 of 30 ccx2 units; 18 of them failed the hidden tests. Every one of the
  18 failures was reported as a passed check (false passes 18 of 18). The check was the sub-agent's own test file.
- **Climbing**: every route of every unit was `codex:gpt-6-luna:low` (`ccx_routes`). The save tier climbs only when
  ccx's check fails, and the sub-agent's own tests never failed at the end.
- **Fix rounds**: 4 ccx2 units had a fix round and 6 a second attempt (7 units with either). 3 of them ended right:
  `wordy` (second attempt), `scale-generator` (fix round) and `pig-latin` (both; right in every arm anyway); the
  other 4 (`pov`, `dot-dsl`, `forth`, `react`) ended wrong.
- **Review**: every ccx2 unit was reviewed. The rows do not hold ccx2's review verdicts; the verifiers' reading of
  the run logs found no review that named an interface mismatch, but how often a review was wrong was not measured
  (limit 11). In direct, whose rows keep the verdicts, 18 of its 19 failures that were not `blocked` ended with a
  review verdict of `pass`.

## Limits

1. One round per arm. The direct and ccx2 arms, with the same model and tier, came out opposite in 10 of 28 clean
   pairs: chance between runs is large.
2. Python only. The selection leans hard: aider's exercises that at most 3 of 7 models solved, minus the 4 easiest.
3. The hidden tests get one try, so the rates cannot be compared with aider's published pass rates.
4. The hidden tests are Exercism's public tests and a model may have seen them. Self was right 5 times with only
   Read and Write (no command run at all; the verifiers counted 6 by a looser reading of what counts as running a
   check). That favours a model that remembers Exercism's conventions, so "contamination is the same for every arm"
   does not hold.
5. The sub-agent was measured only as Codex gpt-6-luna low and the lead only as Sonnet medium; no unit climbed.
6. ccx2's check was the sub-agent's own tests; all 18 failures were reported as a passed check.
7. The lead's instructions were the eval script's fixed `HOW_CCX2`, not the published skill's text; the lead rewrote
   the addendum and added the goal "write test_own.py".
8. The 3 unclean rows (`book-store` self and ccx2, `scale-generator` direct) affect timing only. Why direct's 2
   units stopped as `blocked` after 4 s was not recorded.
9. Codex's sandbox ran unelevated (the pg0 pre-run was elevated); Windows only; amounts are API-equivalent prices.
10. The routing analysis (the AUCs) is computed in sample. hc1 (ccx at 527982e) and pg1 (5d4bd01) ran different
    versions: comparing them is not a paired comparison.
11. How often the review was wrong was not measured: no snapshot between attempts was kept. It could be checked with
    `scripts/eval/fixround_replay.py`.

## What it means for the product

1. **Small jobs stay with the lead.** This supports doing small jobs yourself, with the routing proxy being the
   expected cost of doing it yourself (files to read and change, expected requests), not diff lines or instruction
   length. Recorded in [DECISIONS](../DECISIONS.md).
2. **A sub-agent's own tests are not evidence that the check passed.** Receipts say which test files a passed check
   covered and which of them the agent wrote or changed (#211, already in pg1's ccx at 5d4bd01, but display only: it
   does not change whether the check passed), and since this run the review rubric treats the agent's own tests as
   its yardstick, not evidence (#212, not in pg1's ccx). Climbing
   must also be triggered when the agent's own tests all pass but the task is not done; that is the next item.
3. **What to measure next**: ccx2 re-run on main with #212 (about $1.4), to see whether climbing now fires; it
   is worth more than a direct run at a stronger tier (Codex luna medium or Sonnet direct, about $0.5–1), which would
   measure the tier's own ability.
