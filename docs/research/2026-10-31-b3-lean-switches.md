# B3 lean sub-agent switches: what the measurement showed (2026-10-31)

English · [中文](2026-10-31-b3-lean-switches.zh.md) · back to [research reports](README.md) · the
[plan](2026-10-30-b3-lean-switches-plan.md) (rule fixed before the runs)

**Decision: all three `[subagent]` switches keep today's behaviour by default and stay experimental. The lean side
of each stays off.**

| Switch | Registered rule, as written and implemented, on the 30 clean pairs | Our reading |
|---|---|---|
| `codex_memories = false` (nomem) | **Unknown**: all four conditions pass, but one pair ran on two daily snapshots | Unknown |
| `clean = true` | **Fail**: 3 pairs lost, at most 2 allowed | Fail |
| `codex_lean_tools = true` (leantools) | **Fail**: right 29 vs 30 | Undecided, **post-hoc**: only 30 of the 50 registered pairs are clean |

No re-run. A clean re-run could make leantools pass the registered rule. Even then we would not turn it on: the
registered rule is a necessary condition, not a sufficient one, and the paired statistics show no reliable saving (see
[Why no re-run](#why-no-re-run)). That is a decision beyond the rule, and we say so here.

## Method

All four arms are ccx2 runs with the person's daily setup copied into a per-unit home (see the plan's
[arms](2026-10-30-b3-lean-switches-plan.md#the-arms-opt-in---arms-)):

- `ccx2daily`: the baseline;
- `ccx2daily_nomem`, `ccx2daily_clean`, `ccx2daily_leantools`: one arm per switch.

A pair is the baseline and one switch arm on the same (tag, round, task). The token measure is the same for every
switch: `sub_usage.prompt`, the input + cached tokens of ccx's work runs, without reviews.

The data comes in two halves:

| Half | Tasks | Units per arm | Clean | Arm order | Role |
|---|---|---|---|---|---|
| m1h2 (2026-10-30) | hold-out, 10 tasks × 3 rounds | 30 | yes, every row `env_clean` | shuffled, not balanced | the registered rule |
| m1r5 (2026-10-30/31) | round-5 dev set, 10 tasks × 2 rounds | 20 | **no**, every row `env_clean = false` | balanced | supplementary only |

The plan registered 50 clean pairs per arm, both halves together. Every m1r5 row is unclean, so the rule runs on the
30 m1h2 pairs only, as `r5.py summary` does. m1r5 is shown alongside and never enters the rule.

How the numbers were computed:

- Every number below was recomputed from `.ccx/eval/r5/m1h2-results.jsonl` and `m1r5-results.jsonl`.
- Fields used: `ok`, `sub_usage.prompt`, `sub_usage.runs`, `daily.sha256`, `daily.windows_sandbox`, `env_clean`,
  `ts`, `hidden_failed`, `ccx_routes`, `between_units`, `switches_applied`, `codex_home_after.features_off` and `usd`.
- The script that did this is separate and does not import `scripts/eval/r5.py`. Two reviewers recomputed them again
  with scripts of their own.
- The m1h2 values match what `r5.py summary` prints (`.ccx/eval/r5/m1-summary.txt`).
- The bootstrap CIs come from that summary (2000 resamples, seed 30) and were not recomputed.
- Medians are true medians, rounded to whole tokens in the tables.
- A few facts come from the verifiers' checks of the run logs, not from these files: the `MEMORY.md` reads, the
  real-ledger writes, the review prefix sizes and that the same test failed. Each says so where it appears.
- The raw rows live only on this machine and are not in the repository.

What the columns mean:

| Column | Meaning |
|---|---|
| *right* | right answers, baseline / switch |
| *lost* / *won* | lost: pairs where the baseline was right and the switch wrong; won: the reverse |
| *ratio of medians* | median switch prompt ÷ median baseline prompt; the rule's token condition is ≤ 0.85 |
| *share lower* | share of pairs where the switch's prompt is lower |
| *per-pair median* | median over pairs of switch ÷ baseline |
| *total ratio* | sum over the switch's units ÷ sum over the baseline's |

## Results

### Hold-out half m1h2 (clean; the rule)

| Switch | Pairs | Right | Lost / won | Median prompt (base → switch) | Ratio of medians (95% CI by task) | Share lower | Per-pair median | Total ratio | Rule |
|---|---|---|---|---|---|---|---|---|---|
| nomem | 29 (+1 left out) | 29 / 29 | 0 / 0 | 864,392 → 557,538 | 0.645 (0.443–1.163) | 0.45 | 1.068 | 1.082 | **Unknown** |
| clean | 30 | 30 / 27 | 3 / 0 | 922,188 → 521,270 | 0.565 (0.386–1.006) | 0.57 | 0.927 | 1.100 | **Fail** |
| leantools | 30 | 30 / 29 | 1 / 0 | 922,188 → 495,898 | 0.538 (0.296–0.987) | 0.47 | 1.056 | 0.882 | **Fail** (our reading: undecided) |

- **nomem** passes all four conditions on 29 pairs.
  - In the 30th pair (round 3, `doctor-codex-sandbox`) the two units ran on different daily snapshots
    (`daily.sha256`), and both were right.
  - The rule that leaves such a pair out and turns a pass into Unknown was added on 2026-10-30, after m1h2 had been
    seen ([DECISIONS](../DECISIONS.md)). It is the conservative direction.
  - Without that pair nomem would still not be a full pass: like leantools, it has 30 of the 50 registered pairs.
- **clean** loses 3 pairs, and the rule allows at most 2. More pairs can only add lost pairs, so this Fail stands.
  - The plan also says an arm "on the edge (2–3 pairs lost)" gets 50 more units. That clause conflicts with "at most
    2" and was not carried out. The evaluation-script follow-up is to make the plan say which one holds.
  - 3 lost and 0 won is a rule result, not a significant drop: the exact two-sided McNemar p is 0.25.
- **leantools**: `r5.py summary` prints "fail on 30 pairs", because the switch got 29 right against the baseline's
  30, which breaks "right not lower". That is what the registered rule gives, as written and as implemented: only a
  one-sided missing pair, a missing token count or a snapshot mismatch makes it Unknown, and the 20 m1r5 pairs are
  missing on both sides.
  - Our reading, **decided after seeing the data**: the rule was registered on 50 clean pairs, and a 1-pair gap in
    right answers could close or flip over the 20 missing pairs, unlike clean's lost-pair count. So we do not treat
    this Fail as settled.
  - Either way the switch stays off, so the reading does not change the decision.
- `token_effect` is "not shown" for all three. It is report-only and needs three things: the rule's token condition
  passes, the total ratio is ≤ 0.85, and the share lower is ≥ 0.6.

### Round-5 half m1r5 (unclean; supplementary, not in the rule)

| Switch | Pairs | Right | Lost / won | Median prompt (base → switch) | Ratio of medians | Share lower | Per-pair median | Total ratio |
|---|---|---|---|---|---|---|---|---|
| nomem | 20 | 18 / 20 | 0 / 2 | 1,093,566 → 1,117,098 | 1.022 | 0.65 | 0.867 | 0.949 |
| clean | 20 | 18 / 18 | 2 / 2 | 1,093,566 → 1,078,595 | 0.986 | 0.50 | 1.017 | 1.109 |
| leantools | 20 | 18 / 20 | 0 / 2 | 1,093,566 → 1,050,537 | 0.961 | 0.60 | 0.839 | 0.879 |

### Both halves together (50 pairs; supplementary, not in the rule)

| Switch | Pairs | Right | Lost / won | Ratio of medians | Share lower | Per-pair median | Total ratio |
|---|---|---|---|---|---|---|---|
| nomem | 49 (+1 left out) | 47 / 49 | 0 / 2 | 0.753 | 0.53 | 0.962 | 1.008 |
| clean | 50 | 48 / 45 | 5 / 2 | 0.745 | 0.54 | 0.927 | 1.105 |
| leantools | 50 | 48 / 49 | 1 / 2 | 0.693 | 0.52 | 0.899 | 0.880 |

If nomem's left-out pair is counted, nomem has 50 pairs: right 48 / 50, ratio of medians 0.757, share lower 0.52,
total ratio 1.009.

These 50 pairs mix two task sets (hold-out and dev) whose baseline medians differ (0.92M and 1.09M), and 20 of them
are unclean. Read them as context only.

**The median and the pairs disagree.**

- On m1h2 every switch's median prompt is 35–46 % lower. Yet only 45–57 % of the pairs are lower, and two of the three
  total ratios are above 1. leantools' total is about 12 % lower (0.88), short of 0.85.
- On m1r5 no ratio of medians is below 0.96.
- The m1h2 baseline had more units with several sub-agent runs: 16 of 30, against nomem 9, clean 7 and leantools 14.
  This probably lifts its median. But the number of runs may itself depend on the switch, and leantools has 14
  multi-run units yet the lowest ratio, so this explains only part of it.

So the token condition's pass should not be taken as shown.

## Failed units

- **m1h2, 4 failures**, each with one hidden test failing:
  - clean: `discuss-auto-tier` rounds 1 and 2, `doctor-codex-sandbox` round 3;
  - leantools: `discuss-auto-tier` round 2.

  Both tasks have failed before without these switches:
  - in hc1, `discuss-auto-tier` failed one test in the ccx2 arm, round 3 (a clean row);
  - `doctor-codex-sandbox` failed one test in the builtin arm, round 2 (an unclean row).

  hc1 did not record which test failed, so "the same failure" cannot be checked. The m1h2 units' working folders were
  deleted after the run. The cause is **Unknown**.
- **m1r5, 4 failures**, each task failing the same test in the baseline and in clean:
  - `q-resume-session`: `test_resume_puts_interrupted_items_back` (baseline round 1, clean round 2);
  - `mem-report`: `test_who_wrote_who_used_report` (clean round 1, baseline round 2).

  The baseline fails as often as clean, and the verifier found that these two tasks also failed in the isolated
  r6a / r5g runs. That points at the tasks, not at a switch. This half is unclean.

## Did the switches apply

- **m1r5**:
  - `switches_applied.match` is true on all 80 rows. It is worked out from each run's run.json (`argv_recorded` is
    false), not read back from the command line.
  - The verifier checked the run logs; this is not in the jsonl. nomem's sub-agents read `MEMORY.md` 0 times in 78
    runs; the baseline's read it 6 times in 75.
- **clean** changes very little:
  - Claude review sub-agent: the prefix is only about 300 tokens shorter (15,688 vs 15,991, the verifier's count);
  - Codex: only `~/.agents/skills` is removed, by design (see the
    [features](../features.md#experimental-lean-sub-agent-switches-subagent-off-until-measured) page).
- **leantools**: its apps / plugins part did nothing here. The per-unit Codex home already turns apps, plugins and
  remote_plugin off (`codex_home_after.features_off` on every row).
- **m1h2**: the rows have no `switches_applied` and no frozen snapshot, so whether the switches applied there
  **cannot be checked**.

## Where the tokens go

The more sub-agent runs a unit has, the bigger its prompt:

- the correlation of runs with log(prompt) is 0.55 on m1h2 and 0.68 on m1r5;
- on m1h2 the median prompt is 360k for a unit with one run (74 units) and 1.26M for a unit with more (46 units).

The prompt rises strongly with the number of runs (`sub_usage.runs` does not tell review fix rounds from retries).
That is why B3's next step is fewer runs, not leaner starts.

Post-hoc, not registered: prompt per run (`sub_usage.prompt / sub_usage.runs`), with nomem's split pair left out as
above.

| Switch | m1h2 ratio of medians | m1h2 total ratio | m1h2 share lower | 50 pairs ratio of medians | 50 pairs total ratio | 50 pairs share lower |
|---|---|---|---|---|---|---|
| nomem | 1.07 | 1.29 | 0.45 | 0.91 | 1.11 | 0.49 |
| clean | 1.09 | 1.30 | 0.47 | 1.05 | 1.16 | 0.48 |
| leantools | 0.72 | 0.92 | 0.63 | 0.84 | 0.88 | 0.62 |

Only leantools is lower per run in both halves, but its total ratio (0.92 / 0.88) does not reach 0.85. It is a hint,
not a result.

## Limits

1. The daily arms use Codex's **unelevated** Windows sandbox (`daily.windows_sandbox` on all 200 rows). The person's
   real setup uses the elevated one (from the plan; hc1's rows do not record it).
2. The baseline's Codex home already has apps / plugins / remote_plugin off, so that part of leantools was **not
   measured**.
3. clean removes only `~/.agents/skills` on Codex and about 300 tokens on the Claude review side, so what it tested
   is a small change.
4. One lead model (Sonnet, medium). The Codex sub-agents ran on gpt-6-luna: low in 321 of 338 routes, high in 17.
5. Dollar amounts are API-equivalent prices (about $20 for the four arms over both halves), not what a subscription
   costs.
6. Every m1r5 row is `env_clean = false`. The machine was already busy when it started, and stayed busy: other
   sessions ran pytest, `ccx run`, `claude -p` and `codex exec`. 13 rows carry `between_units` findings (69 in all),
   and the verifier found the real ledger written 8 times. So m1r5 is left out of the rule.
7. m1h2 has no frozen snapshot: there are two different `daily.sha256` values (89 rows and 31 rows), and no
   `switches_applied`.
8. m1h2's failed units' folders were deleted. In `m1r5-results-artifacts/`, only 4 of the 21 folders belong to this
   run. The other 17 are left over from the run stopped at 18:55–19:02.
9. The rule's median condition and the paired statistics point opposite ways (see above).
10. The number of requests per sub-agent run is not recorded (`req=` in the log counts the lead's requests).
11. The samples are small: 10 tasks × 3 rounds plus 10 tasks × 2 rounds.
    - Near a 95 % baseline, the plan's 50 pairs only show a drop of about 10 points or more.
    - The rule ran on 30 pairs, where the detectable drop is larger still.
    - The m1h2 baseline was right 30 of 30.

Threats found in review, beyond the 11:

- **m1h2's arm order was shuffled, not balanced.** By `ts`, the baseline ran first in 16, 20 and 17 of the 30
  nomem / clean / leantools pairs. m1r5 is balanced (10 of 20 each).
- **One shared baseline.** All three switches are compared with the same baseline units. A baseline that happens to
  be high makes all three medians pass together (0.54–0.65 at once), so the three results are not independent.
- **Two task sets.** The 50-pair figures mix the hold-out set and a dev set used while building ccx.

## Why no re-run

A clean re-run of the r5 half for the baseline and leantools would be 40 units, about $4.8. If it came out like the
unclean m1r5 half, leantools could pass the registered rule on 50 pairs:

- right 49 vs 48, 1 pair lost;
- ratio of medians 0.693.

We still do not run it, and this is a decision beyond the registered rule:

- The plan says a default changes **only if** the rule passes. The rule is a necessary condition, not a sufficient one.
- The person's own rule adds that a default is turned on only if it is no less right **and** brings a real saving.
- The report-only paired statistics do not show that saving for leantools:
  - share lower 0.47 (m1h2) and 0.52 (50 pairs);
  - total ratio 0.88, short of 0.85;
  - `token_effect` not shown.
- The r5 numbers behind this are from the unclean half and are context, not evidence.

So the budget goes to fewer runs per unit (B3 §2.2), which the token data above points at.

## Decision

All three switches keep today's behaviour by default and are marked experimental in `config/tiers.toml` and on the
[features](../features.md#experimental-lean-sub-agent-switches-subagent-off-until-measured) page:

- nomem: Unknown;
- clean: Fail;
- leantools: Fail under the registered rule on the clean pairs, undecided in our post-hoc reading.

See [DECISIONS](../DECISIONS.md).

Anyone can still turn a switch on in `hub/ccx/tiers.toml`. This report does not show that any switch saves tokens.
On right answers:

- clean did not pass the rule on the hold-out half (3 lost, 0 won), and why it lost is Unknown;
- nothing here shows the other two cost right answers.
