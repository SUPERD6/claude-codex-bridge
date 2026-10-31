# External benchmark pg1: 30 polyglot Python exercises, self vs ccx vs direct (2026-10-31)

English · [中文](2026-10-31-polyglot-pg1.zh.md) · back to [research reports](README.md) · the
[plan](2026-10-30-polyglot-slice-plan.md) (rules fixed before the run)

**On 30 polyglot Python exercises (one round, hidden tests, one try), a Sonnet lead delegating through ccx to the
cheapest tier was right 12/30 against 25/30 doing it itself, at about 3× the cost per success and about 5× the wall
time. Sending the same tier the work directly, with no lead, was cheaper per success than self but right only 9/30.
Small strict-interface tasks are not worth delegating; so far a saving has been seen only on repository tasks that
are costlier to do yourself (hc1), not here.**

Three findings (counts over all 30 exercises unless a line says clean):

1. **On small single-file exercises, handing the work to the cheapest tier through the lead was both less often
   right and about 3× dearer per success.** This does not say ccx got worse overall. Our reading, not a tested
   result, is that it does not contradict [hc1](2026-10-29-hc1-holdout.md): delegating saves money only when doing
   it yourself is expensive *and* the sub-agent is as right; hc1's repository tasks met both, pg1 met neither. hc1
   and pg1 are not paired (different tasks, ccx 527982e vs 5d4bd01).
2. **Even if every unit had been right, delegating would have been dearer: 82 % of ccx2's spend was on the lead's
   side.** If all 30 had been right, ccx2 would have cost $0.046 per success against self's measured $0.037. The
   lead's side alone had a median of $0.0346 per task against $0.0275 for self doing the whole task, and was dearer
   than self's whole task on 24 of 30. Of the 3.1× per success, about half comes from fewer right answers (spend
   1.5× × successes 25/12 ≈ 2.1×). The 30 exercises are all one file, so pg1 cannot say whether size or difficulty
   drives this.
3. **Review and fix rounds caught no interface error, and the tier never climbed.** ccx2's check ran the
   sub-agent's own `test_own.py`; its final check passed in 30 of 30 units, including all 18 whose hidden tests
   failed, so the check told nothing apart. What review and rework added to correctness was not measured: 3 of the
   7 reworked units ended right. Every route was Codex gpt-6-luna low.

The cost against self depends on the path: delegated through the lead (ccx2) cost 3.1× self per success; the same
tier with no lead (direct) cost 0.57× self ($0.021 vs $0.037; 95 % CI 0.37–1.14 over all 30, 0.34–0.99 over the
28 clean pairs), at the price of 9/30 right.

## Method

- **Tasks**: 30 Python exercises of aider's polyglot benchmark (commit 7e0611e, 2024-12-22), chosen without looking
  at any solution: aider's 225 hardest exercises (solved by at most 3 of 7 models in 2024) include 34 in Python; the
  4 lowest by (Exercism difficulty, number of tests) were dropped. The list and the reason for each is
  `scripts/eval/polyglot_selection.json`; the task set is `scripts/eval/tasks_polyglot.py`.
- **What a unit sees**: a fresh one-commit repository with the solution stub only (no tests, `.meta/` or history),
  the exercise's own instructions and a short addendum (which file, keep the names, standard library only, the tests
  are hidden). The exercises have no tests of their own in the unit, so in ccx2 the check is a test file the
  sub-agent wrote.
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

| Row left out of the clean count | Right | Why left out |
|---|---|---|
| `pg-book-store` self | yes | other processes seen during the unit |
| `pg-book-store` ccx2 | no | other processes seen during the unit |
| `pg-scale-generator` direct | no | other processes seen during the unit |

So the clean count has 29 units per arm, 29 self–ccx2 pairs and 28 pairs for each pair with direct.

**How the numbers were computed.** Every number below comes from `.ccx/eval/r5/pg1-results.jsonl` (one row per
unit, kept on the machine that ran it, not in the repository), recomputed with a separate script that does not import
`scripts/eval/r5.py`:

```bash
python scripts/research/polyglot_pg1.py .ccx/eval/r5/pg1-results.jsonl --out docs/research/data/2026-10-31-polyglot-pg1.json
```

The output, with one scrubbed row per unit (no paths), is
[data/2026-10-31-polyglot-pg1.json](data/2026-10-31-polyglot-pg1.json); two runs give byte-identical files. The
clean-count values match what `r5.py summary --taskset polyglot --tag pg1` prints. Sign tests are exact two-sided
binomial tests on the discordant pairs (McNemar's exact test). The cost bootstrap resamples the 29 (or 30) tasks,
2000 times, seed 31; the AUC bootstrap resamples tasks 4000 times, seed 7; both intervals are percentile intervals
without interpolation (the values at index ⌊q·(n−1)⌋ of the sorted resamples). Wall times are rounded half up to
0.1 s. Three things are not fields of the rows and say so where they appear: the failure coding (from each unit's
hidden-test output), what the verifiers read in the run logs, and the grep of the final diffs. The **verifiers**
are the two reviewers who independently rechecked this run's numbers and logs before the report was written.

**Tampering check.** All 90 `final.diff` files (kept on the machine that ran it) were searched: none touches
`sys.modules`, `builtins`, a `conftest.py`, `monkeypatch` or `importlib` (the one hit for `builtins` is a local set of
Forth words in `forth.py`). self and direct changed only the solution file; ccx2 also added `test_own.py` and
`brief.md`, where pytest appears only as ordinary use (`import pytest`, `pytest.raises`, `parametrize`).

## Results

| Arm | Right, all 30 (Wilson 95 %) | Right, clean | Total spend, all / clean | Cost per success, all / clean | Wall time, median, all / clean |
|---|---|---|---|---|---|
| self | **25/30** (0.66–0.93) | 24/29 | $0.915 / $0.871 | **$0.037** / $0.036 | 11.1 s / 10.8 s |
| ccx2 | 12/30 (0.25–0.58) | 12/29 | $1.381 / $1.341 | $0.115 / $0.112 | 57.4 s / 57.4 s |
| direct | 9/30 (0.17–0.48) | 9/29 | $0.187 / $0.175 | $0.021 / $0.019 | 44.3 s / 43.9 s |

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
- On the 28 clean direct–ccx2 pairs the two arms came out opposite in 10 (8 of 26 without direct's two `blocked`
  runs). They share the model and tier but not the conditions (ccx2 has the lead's brief, a self-written check and
  fix rounds), so this cannot be read as pure run-to-run noise.

### Cost and wall time against self (paired by task)

| | ccx2, clean 29 pairs | ccx2, all 30 | direct, clean 28 pairs | direct, all 30 |
|---|---|---|---|---|
| Total spend ÷ self (95 % CI by task) | **1.54** (1.35–1.75) | 1.51 (1.32–1.71) | 0.20 (0.17–0.23) | 0.21 (0.18–0.24) |
| Cost per success ÷ self (95 % CI) | **3.08** (2.12–5.16) | 3.14 (2.21–5.43) | 0.51 (0.34–0.99) | 0.57 (0.37–1.14) |
| Tasks where the arm cost more than self | 27 of 29 | 27 of 30 | 0 of 28 | 0 of 30 |
| Tasks where the arm was slower than self | 29 of 29 | 30 of 30 | 26 of 28 | 28 of 30 |
| Wall time, median of per-task differences | +46.3 s | +46.8 s | +31.3 s | +33.5 s |

`r5.py summary` agrees on direct: on the 28 clean pairs its cost-per-success difference direct − self is −$0.0178
(95 % CI −0.0265 to −0.0011), wholly below 0. So the "about 3× dearer" is the lead-delegated path (ccx2); without a
lead the same tier was cheaper per success than self, but right on 9 of 30.

## Why ccx2 was dearer: the lead's side

Fields: `lead_usd` and `usd` (= `lead_usd` + `ccx_usd`) of each ccx2 row; self's `usd` is all lead. `lead_usd` is
all of the lead's Claude spend in the unit, including writing the brief, the turn that waits and accepting the
result; it is higher in the 7 reworked units (median $0.048 against $0.034 in the other 23). The reviews' cost is in
`ccx_usd`, not here.

| | All 30 | Clean 29 |
|---|---|---|
| ccx2: lead's side ÷ total spend | 1.135 / 1.381 = **82.2 %** | 1.101 / 1.341 = 82.1 % |
| ccx2: lead's side, median per task | $0.0346 | $0.0350 |
| self: whole task, median | $0.0275 | $0.0274 |
| Tasks where ccx2's lead side alone cost more than self's whole task | 24 of 30 | 24 of 29 |
| ccx2 cost per success if every unit had been right (total ÷ units) | $0.046 | $0.046 |
| self cost per success, as measured | $0.037 | $0.036 |

On a one-file exercise the lead's side (including the brief, the wait and the acceptance) costs about as much as
doing it. A cheaper or better sub-agent cannot remove that part.

**Post-hoc exploration: no feature we tried showed predictive power.** The plan did not include this analysis. AUC
of each feature for "the unit failed" (0.5 = no signal; features from `polyglot_selection.json`; in sample; 95 % CI by
task, 4000 resamples, seed 7), on 18 ccx2 and 21 direct failures:

| Feature | ccx2 failed | direct failed |
|---|---|---|
| Exercism difficulty | 0.57 (0.35–0.77) | 0.54 (0.32–0.76) |
| Number of hidden tests | 0.51 (0.28–0.74) | 0.38 (0.16–0.61) |
| Length of the instructions | 0.34 (0.14–0.56) | 0.62 (0.37–0.84) |

All six intervals contain 0.5: with 18 and 21 failures, the three features we tried show no predictive power. Diff
size cannot be known before the work. Using the expected cost of doing it yourself (files to read and change,
expected requests) as the routing proxy is a hypothesis drawn from the 82 % above; pg1 cannot test it, since every
exercise is one file. A weak, in-sample, post-hoc observation in its favour: the 3 exercises where ccx2 cost less
than self (`paasio`, `book-store`, `sgf-parsing`) are at the top of self's cost order (26th, 28th and 30th of 30).

## Why it failed

**Interface guesses.** One of us coded each of ccx2's 18 failures from the first error lines of its hidden-test
output. This is a single coder with no agreement check, and the raw hidden-pytest output is not in the repository
(the coding and a one-line reason per unit are in the data file):

| Kind | Count | Examples |
|---|---|---|
| Interface: does the job, but not in the shape the hidden tests expect | **14** | returns a list where a string is expected (`grep`) or the reverse (`food-chain`); takes a string where the tests pass a list (`forth`); raises where the tests expect `False` (`grade-school`); missing constants or methods (`go-counting`, `phone-number`); different error text (`tree-building`, `pov`) |
| Logic: the behaviour is wrong | 4 | `bowling`, `hangman`, `connect`, `paasio` |

The instructions only say to match the hidden tests (keep the names); they give no concrete shape or error text.
The Codex model guessed wrong on both of its paths (ccx2 and direct); the Sonnet lead got them right far more often
(perhaps partly from remembering Exercism's conventions, see limit 4).

- **All three arms wrong (5)**: `pov`, `dot-dsl`, `go-counting`, `paasio`, `tree-building`.
- **ccx2 wrong where direct was right (4)**: `bowling`, `connect`, `food-chain`, `zipper`. In `zipper` and
  `food-chain` the sub-agent wrote `test_own.py` against an interface it invented (tuple trees; one string instead
  of a list of lines). The check passed on those tests and the review let it through, which locked the wrong
  interface in.
- **ccx2 right where direct was wrong (7)**: 2 were direct's 4-second `blocked` runs (`zebra-puzzle`,
  `bottle-song`), 1 an unclean direct row (`scale-generator`, where ccx2 also had a fix round), 3 ccx2 got right on
  its first try (`two-bucket`, `beer-song`, `sgf-parsing`), 1 after a second attempt (`wordy`). At most 2 of the 7
  have anything to do with rework.

## Review and fix rounds caught no interface error; the check told nothing apart; the tier never climbed

- **Check**: `ccx_check_passed` (the final check) is true in 30 of 30 ccx2 units; 18 of them failed the hidden
  tests, so every failure was reported as a passed check (18 of 18) and the check separated nothing. The check was
  the sub-agent's own test file. In 3 units (`wordy`, `react`, `pig-latin`) the first attempt's check failed and ccx
  retried on the same rung; why it retried rather than climbed was not looked into here.
- **Climbing**: every route of every unit was `codex:gpt-6-luna:low` (`ccx_routes`). The save tier climbs when
  ccx's check fails, and the sub-agent's own tests always passed in the end.
- **Fix rounds and second attempts**: 4 ccx2 units had a fix round and 6 a second attempt (7 units with either).
  The second attempts came from two places: 3 the lead sent back with `ccx resume` (`pov`, `dot-dsl`, `forth`) and 3
  ccx retried after its own check failed (`wordy`, `react`, `pig-latin`). 3 of the 7 ended right: `wordy` (second
  attempt), `scale-generator` (fix round) and `pig-latin` (both; right in every arm anyway); the other 4 (`pov`,
  `dot-dsl`, `forth`, `react`) ended wrong. On `wordy` and `scale-generator` direct was wrong, but `scale-generator`'s
  direct row is unclean; what rework added to correctness was not measured.
- **Review**: every ccx2 unit was reviewed. The rows do not hold ccx2's review verdicts; the verifiers' reading of
  the run logs found no review that named an interface mismatch, but how often a review was wrong was not measured
  (limit 11). In direct, whose rows keep the verdicts, 18 of its 19 failures that were not `blocked` ended with a
  review verdict of `pass`.

## Limits

1. One round per arm. direct and ccx2 came out opposite in 10 of 28 clean pairs (8 of 26 without direct's `blocked`
   runs); their conditions differ (brief, self-written check, fix rounds), so this is not a measure of pure noise,
   and how much one round varies is unknown.
2. Python only. The selection leans hard: aider's exercises that at most 3 of 7 models solved, minus the 4 easiest.
   All 30 are one file.
3. The hidden tests get one try, so the rates cannot be compared with aider's published pass rates.
4. The hidden tests are Exercism's public tests and a model may have seen them. Self was right 5 times with only
   Read and Write (no Bash call at all); the verifiers counted 6 by a stricter reading of what counts as running a
   check (a Bash call that only writes a file is not one). That favours a model that remembers Exercism's
   conventions, so "contamination is the same for every arm" does not hold.
5. The sub-agent was measured only as Codex gpt-6-luna low and the lead only as Sonnet medium; no unit climbed.
6. ccx2's check was the sub-agent's own tests; all 18 failures were reported as a passed check.
7. The lead's instructions were the eval script's fixed `HOW_CCX2`, not the published skill's text; the lead rewrote
   the addendum and added the goal "write test_own.py".
8. 3 rows are unclean (`book-store` self and ccx2, `scale-generator` direct); both counts are given everywhere. Why
   direct's 2 units stopped as `blocked` after 4 s was not recorded.
9. Codex's sandbox ran unelevated (the pg0 pre-run was elevated); Windows only; amounts are API-equivalent prices.
10. The routing analysis (the AUCs) is post hoc and in sample. hc1 (ccx at 527982e) and pg1 (5d4bd01) ran different
    versions on different tasks: comparing them is not a paired comparison.
11. How often the review was wrong was not measured: no snapshot between attempts was kept. It could be checked with
    `scripts/eval/fixround_replay.py`.
12. The failure coding is one person's, with no agreement check; the raw hidden-test output and the final diffs are
    not in the repository.

## What it means for the product

1. **Direction, not yet implemented: small jobs stay with the lead.** pg1 supports doing small jobs yourself, but
   `config/tiers.toml [routing] small_self` still ships off: on hc1, doing ≤ 1-file tasks yourself cost 5 % more,
   the opposite direction to pg1, and the switch waits for the P0-6 measurement. The routing proxy would be the
   expected cost of doing it yourself (a hypothesis, see above), not diff lines or instruction length. The shipped
   size rule (DECISIONS, 2026-10-26) calls a task large when its brief has ≥ 180 words, and balanced sends large
   tasks to ccx2; by a rough whitespace word count of the `brief.md` files in the final diffs, 27 of pg1's 30 ccx2
   briefs had ≥ 180 words, although every exercise is one file. Recorded as a direction in
   [DECISIONS](../DECISIONS.md).
2. **A sub-agent's own tests are not evidence that the check passed.** Receipts say which test files a passed check
   covered and which of them the agent wrote or changed (#211, already in pg1's ccx at 5d4bd01, but display only: it
   does not change whether the check passed), and since this run the review rubric treats the agent's own tests as
   its yardstick, not evidence (#212 in `ccx/review.py`, not in pg1's ccx). Today that rule acts only through
   #212's review rubric: neither the check nor climbing uses it.
3. **What to measure next**: first make climbing triggerable when the agent's own tests all pass but the task is
   not done, then re-run ccx2 (about $1.4). A re-run on today's main would not test climbing (it climbs only when the
   check fails, and the check still runs `test_own.py`); it could instead show whether #212's review catches the
   interface mismatches and opens fix rounds. Either is worth more than a direct run at a stronger tier (Codex luna
   medium or Sonnet direct, about $0.5–1), which would measure the tier's own ability.
