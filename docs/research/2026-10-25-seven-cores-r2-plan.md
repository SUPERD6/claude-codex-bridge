# Seven cores, round 2: does dividing the work beat one model, and is it cheaper? (plan)

English · [中文](2026-10-25-seven-cores-r2-plan.zh.md) · 2026-10-25 · written before any real run

Round 1 report: [2026-10-24-seven-cores-ab.md](2026-10-24-seven-cores-ab.md). This round covers core 4 (dividing the work does better), 5 (cheap and efficient), 6 (more accurate with use) and 7 (nothing lost, under control), with the defaults merged since round 1: `tradeoff = save` and escalation when the acceptance check fails (#34), the review on the other vendor's cheapest tier, item by item against the requirements (#31), weak evidence reviewed automatically (#41/#65), killed runs counted (#54), faster `--to auto` (#57), shared memory for every sub-agent (#36).

## 0. Rules for every group

- Script: `scripts/eval/r2.py` (tasks in `scripts/eval/tasks_r2.py`; round 1's `common.py` and the statistics in `seven_ab.py` are reused).
- **Every unit gets a fresh throwaway hub** (`CCX_HUB`): `ab_self_rate = 0`; the DeepSeek cap raised to $1000 (the person chose no cap for now, but every cent is still counted); Codex tiers T2–T4 set to `gpt-6-luna low`, and `gpt-6.1-sol` / `gpt-6-astra` marked unavailable to routing; `CCX_NO_QUOTA_PROBE=1` (each new hub would probe Claude's quota again, adding the same noise to every unit).
- Every `ccx run` has `--no-ab` and the label `eval-r2:<tag>:<group>:<round>:<task>:<arm>`; `ccx way` gains `--label` in this PR so its build steps carry an `eval-` label too.
- **Known deviation**: routing can hold back a model but not an effort, so routed arms may still pick `gpt-6-luna high`. Reported if it happens.
- A hidden acceptance test the agents never see decides right or wrong; it is recorded with `ccx verify` in the unit's hub.
- Task order and arm order are shuffled per round (seed 26). **Each group re-runs its own baseline arm on the same code; the report never compares directly with round 1.**
- Spend = API-equivalent dollars from the ledger (Codex and Claude at API prices, DeepSeek real money). Before each unit the script adds up all results and **stops at $6**; going past $6 needs the person's yes in the chat. The running total is reported after each group.
- Statistics: the independent unit is the task (a task's paired differences are averaged over its rounds first); exact McNemar for right/wrong; for spend, tokens and time the median paired difference, a bootstrap 95% interval and the sign test; the primary tests (4-C on vs off, 4-B single vs way and single vs draft, all on correctness) are Holm-adjusted. Small groups are descriptive only. Negative results are reported as they are.
- Timing: everything runs before 10/31 (11/1–11/7 is the J0 after-window: no real runs). Scrubbed data (no paths, no session ids) goes to `docs/research/data/`.

## 1. Tasks

- **Trap tasks (10, `TRAPS`)**: medium tasks whose brief states several requirements while the visible test checks only the main path; the hidden test checks the one that is easy to skip (rounding mode, no mutation, ordering, boundaries, error cases). `inventory` comes from round 1 (luna low got it wrong 6/6 times there, always the same way); new: merge, version, wrap, groupby, cart (two files, half-up rounding), ini, coerce (zip codes with a leading zero), bytes, retry. `tests/test_eval_tasks.py` checks that every start fails its hidden test and every reference solution passes.
- **Small tasks**: round 1's slugify, duration, intervals, cli-json, csvstats, lru.
- **PAR10**: ten unrelated small modules (m01–m10), one function and one hidden test each, plus `tests/test_mNN.py` to write for each.
- **QUEUE**: four pieces with dependencies (b uses a, c uses b, d stands alone).

## 2. Groups (in priority order)

| # | Group | Arms | Tasks × rounds | Decision rule (fixed in advance) | Est. spend |
|---|---|---|---|---|---|
| 1 | 4-A `ccx way` smoke | visible, critical (`--yes`) | inventory, cart, merge × 1 each = 6 runs | Per run: the plan has ≥1 `[step]` and ≥1 `[accept]` item; the acceptance verdict parses as pass/issues; for critical, `PICK: A/B` parses. Any format miss → lenient parsing in the parsing part of `ccx/ways.py`, then the failed runs again (marked as such) | ~$0.6 |
| 2 | Screen | luna low alone | 10 traps × 2 | Counts in no comparison; only picks 4-B's tasks: the ≥7 the cheap model got wrong most (if fewer than 7 failed, the 7 with most failures, said so) | ~$0.05 |
| 3 | 4-C review again | off / on / auto (all luna low, no escalation) | 10 traps + slugify, duration, lru = 13 × 3 rounds | Primary: correctness on vs off (McNemar, 39 pairs, Holm). "Review makes results more correct" only if on is higher and Holm p < 0.05. Also: spend ratio, first reviews that found issues, fix rounds that turned wrong into right, "ccx said ok but the hidden test failed"; for auto, how often the automatic review fired | ~$0.8 |
| 4 | 4-B divided vs one model | single (luna low alone) / way (`ccx way --risk visible`: claude plans, codex builds, the planner accepts, at most one fix round) / draft (claude sonnet drafts the plan → codex luna low reads and checks the draft → codex luna low builds from the draft and the check, no acceptance) | the ≥7 screened tasks × 2 rounds | Primary: single vs way and single vs draft on correctness (McNemar, Holm). "Dividing does better" needs Holm p < 0.05 in the positive direction; otherwise direction and interval only. Also rework (way's fix rounds), total tokens, total spend (ratio + task-level sign test), time. **Bias note**: tasks are picked because the cheap model fails them, so in the real run the single arm regresses toward its mean (looks better than in the screen); this works against the divided arms, not for them | ~$2.1 |
| 5 | Parallel scale | p1 (one Codex does all ten, `--no-subagents`) / p3, p10 (`ccx batch` with 3 and 10 runs side by side, one worktree each, merged back one by one) / native (one Codex with `--parallel`: told to use its own sub-agents) | PAR10 × 2 rounds | Descriptive (n = 2): wall time, total tokens, total spend, pieces right out of 10, merge conflicts. Fit tokens = a + b × runs over p1/p3/p10 and extrapolate the share of start-up cost (b × 100) at 100 runs. "Faster" = faster in both rounds; "cheaper" = less in both rounds | ~$0.15 |
| 6 | 4-H own sub-agents on/off | Codex: p1 vs native (above); Claude haiku low: c_off (`--no-subagents`) vs c_on (`--parallel`) | PAR10 × 2 rounds | Record whether they really started any (Codex child session files, Claude `subagents/*.jsonl`); compare spend, time, correctness (descriptive) | ~$0.05 |
| 7 | (b') routing | fixed (claude sonnet medium, no escalation) / warm (`--to auto` with a **copy** of the routing-state of the person's default hub, SHA-256 recorded before the run) / cold (`--to auto`, empty hub) | 12 (4 small + csvstats, lru + the first 6 traps) × 1 | Correctness (McNemar), spend ratio, time, which tiers were picked, escalations, "check passed but the hidden test failed". n = 12: descriptive | ~$0.8 |
| 8 | 4-D tiers by difficulty | `ccx route` (no model call) at 5 / 15 / 30 minutes × 3 briefs × warm/cold | — | "Tiering works" if, warm, at least 2 of the 3 briefs get ≥2 different tiers across the three difficulties | $0 |
| 9 | More accurate with use | one hub that keeps learning (from the same copy): the 12 tasks twice (phase1, phase2), each verified by its hidden test; the frozen arm is group 7's warm arm (same state, same code, a fresh copy per unit) | 12 × 2 | phase2 (learning) vs frozen: Brier (routing's predicted success vs the hidden result) and correctness. "More accurate with use" only if Brier is lower and correctness not lower; n = 12, descriptive | ~$0.4 |
| 10 | F11 + 4-I | F11: claude sonnet with `--parallel --budget 0.0001`: does Claude's sub-agent cap really fire; 4-I: QUEUE through `ccx q run`, its process tree killed once one piece is done, then `ccx q resume` | 1 each | F11: `kind = over_budget` and sub-agents really started; 4-I: after resume all 4 pieces done, hidden test passes, no finished piece done again | ~$0.1 |

Estimated total about $5.0; run in priority order and stop to ask at $6.

## 3. Not in this round

- Gemini (not installed here); DeepSeek as the lead (the ccx-vendors session covers it).
- How much a long real lead conversation saves (round 1 only extrapolated; not measured here either).
- Writing shared memory (H5), which would write the person's real hub.

## 4. Change log (design changes before the runs, in order)

- **10/25, after group 1 and the screen**: luna low got 19/20 of the first ten trap tasks right — too easy. Two more batches: `TRAPS2` (the trap sits in the code the change must fit into: a second copy of the logic, a cache, a helper with the wrong rounding, a subclass override, bool being an int, a slice before the filter; 8 + inventory) 16/18 right (only inventory failed, 2/2); `COMPOUND` (inventory's shape: three numbered requirements over three files; 4) 8/8 right. Over the three batches luna low was right 47 times out of 49; only inventory fails.
- So: 4-B uses, by the fallback rule fixed in section 2, the 7 most-failed tasks of `screen2` (inventory + dupparse, cache, rounding, exporter, tags, config); 4-C uses the 9 `TRAPS2` tasks + 3 of the first batch as controls (merge, version, ini), 12 × 3 rounds; the 6 trap tasks among the 12 of (b') and "more accurate with use" become the first 6 of `TRAPS2`. Correctness in these groups will likely sit near the ceiling, so spend and time carry most of the information; the report says so and does not read it as "dividing never helps".
- 4-A: 6/6 formats right; `ccx/ways.py`'s parsing was not changed.
