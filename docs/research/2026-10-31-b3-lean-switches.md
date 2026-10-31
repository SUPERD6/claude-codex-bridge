# B3 lean sub-agent switches: what the measurement showed (2026-10-31)

English · [中文](2026-10-31-b3-lean-switches.zh.md) · back to [research reports](README.md) · the
[plan](2026-10-30-b3-lean-switches-plan.md) (rule fixed before the runs)

**Verdict: all three `[subagent]` switches stay off by default and stay experimental.**

- `codex_memories = false` (nomem): **Unknown**.
- `clean = true`: **Fail**.
- `codex_lean_tools = true` (leantools): **Unknown** under the registered rule.

We are not re-running. A top-up could settle at most the right-answer count, and no switch showed a token saving big
enough to turn it on by default (see [Why no re-run](#why-no-re-run)).

## Method

All four arms are ccx2 runs with the person's daily setup copied into a per-unit home (see the plan's
[arms](2026-10-30-b3-lean-switches-plan.md#the-arms-opt-in---arms-)):

- `ccx2daily`: the baseline;
- `ccx2daily_nomem`, `ccx2daily_clean`, `ccx2daily_leantools`: one arm per switch.

A pair is the baseline and one switch arm on the same (tag, round, task). The token measure is the same for every
switch: `sub_usage.prompt`, the input + cached tokens of ccx's work runs, without reviews.

The data comes in two halves:

| Half | Tasks | Units per arm | Clean | Role |
|---|---|---|---|---|
| m1h2 (2026-10-30) | hold-out, 10 tasks × 3 rounds | 30 | yes, every row `env_clean` | the registered rule |
| m1r5 (2026-10-30/31) | round-5 dev set, 10 tasks × 2 rounds, balanced arm order | 20 | **no**, every row `env_clean = false` | supplementary only |

The plan registered 50 clean pairs per arm, both halves together. Every m1r5 row is unclean, so the rule runs on the
30 m1h2 pairs only. m1r5 is shown alongside it and never enters the rule.

How the numbers were computed:

- Every number below was recomputed from `.ccx/eval/r5/m1h2-results.jsonl` and `m1r5-results.jsonl`, using the
  fields `ok`, `sub_usage.prompt`, `daily.sha256` and `env_clean`.
- The script that did this is separate and does not import `scripts/eval/r5.py`.
- The m1h2 values match what `r5.py summary` prints (`.ccx/eval/r5/m1-summary.txt`).
- The bootstrap CIs come from that summary (2000 resamples, seed 30); I did not recompute them.
- Medians are true medians.
- Some facts come from the two verifiers' checks of the run logs and earlier runs, not from these jsonl files. Each
  one says so where it appears: the `MEMORY.md` reads, the real-ledger writes, the hc1 / r6a / r5g failures and
  the review prefix sizes.
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
| leantools | 30 | 30 / 29 | 1 / 0 | 922,188 → 495,898 | 0.538 (0.296–0.987) | 0.47 | 1.056 | 0.882 | script: fail; registered: **Unknown** |

- **nomem** passes all four conditions on 29 pairs. In the 30th pair (round 3, `doctor-codex-sandbox`) the two units
  ran on different daily snapshots (`daily.sha256`). The plan's rule leaves such a pair out and turns a pass into
  Unknown. Both units of that pair were right.
- **clean** loses 3 pairs, and the rule allows at most 2. More pairs can only add lost pairs, so this Fail stands.
- **leantools**: `r5.py summary` prints "fail on 30 pairs", because the switch got 29 right against the baseline's
  30, which breaks "right not lower". But the rule was registered on 50 clean pairs and only 30 exist, so it cannot be
  applied as registered: **Unknown**. On all 50 pairs, unclean half included, the switch is right 49 times against
  48 (table below), so the 30 clean pairs alone do not settle it.
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

If nomem's left-out pair is counted, nomem has 50 pairs:

- right 48 / 50;
- ratio of medians 0.757;
- share lower 0.52;
- total ratio 1.009.

An earlier draft of the verdict gave 45 % and 1.08 for nomem's 50 pairs. Those are the m1h2-only values.

**The median and the pairs disagree.**

- On m1h2 every switch's median prompt is 35–46 % lower. Yet in about half of the pairs (45–57 %) the switch is not
  lower, and two of the three total ratios are above 1.
- On m1r5 no ratio of medians is below 0.96.
- The medians pass mainly because the baseline's m1h2 median is high: the baseline had more units with several runs.

So treat the token condition's pass as unproven.

## Failed units

- **m1h2, 4 failures**, each with one hidden test failing:
  - clean: `discuss-auto-tier` rounds 1 and 2, `doctor-codex-sandbox` round 3;
  - leantools: `discuss-auto-tier` round 2.

  The verifier found that the same two tasks failed the same way in hc1's arm without switches, so an unstable task is likely. But the units'
  working folders were deleted after the run, so the cause is **Unknown**, not "the task, not the switch".
- **m1r5, 4 failures**, all on the same test:
  - baseline: `q-resume-session` round 1, `mem-report` round 2;
  - clean: `mem-report` round 1, `q-resume-session` round 2.

  The verifier found that these two tasks also failed in the isolated r6a / r5g runs, and the failures appear in the baseline as well as in
  clean. So they point at the tasks, not at a switch. This half is unclean.

## Did the switches apply

- **m1r5**: `switches_applied.match` is true on all 80 rows. The verifier also checked the run logs; this is not in
  the jsonl. nomem's sub-agents read `MEMORY.md` 0 times in 78 runs; the baseline's read it 6 times in 75.
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

The re-runs (review fix rounds, retries) are the big part. That is why B3's next step is fewer runs, not leaner starts.

Post-hoc, not registered: prompt per run (`sub_usage.prompt / sub_usage.runs`).

| Switch | m1h2 ratio of medians | m1h2 total ratio | 50 pairs ratio of medians | 50 pairs total ratio |
|---|---|---|---|---|
| nomem | 1.08 | 1.28 | 0.94 | 1.11 |
| clean | 1.09 | 1.30 | 1.05 | 1.16 |
| leantools | 0.72 | 0.92 | 0.84 | 0.88 |

Only leantools is lower per run in both. Even so, its share lower is at most 0.62, so this is a hint, not a result.

## Limits

1. The daily arms use Codex's **unelevated** Windows sandbox (`daily.windows_sandbox` on all 200 rows). The
   person's real setup and hc1 use the elevated one.
2. The baseline's Codex home already has apps / plugins / remote_plugin off, so that part of leantools was **not
   measured**.
3. clean removes only `~/.agents/skills` on Codex and about 300 tokens on the Claude review side, so what it tested
   is a small change.
4. One lead model (Sonnet, medium). The Codex sub-agents ran on gpt-6-luna: low in 321 of 338 routes, high in 17.
5. Dollar amounts are API-equivalent prices (about $20 for the four arms over both halves), not what a subscription
   costs.
6. Every m1r5 row is `env_clean = false`. While it ran, other sessions were running pytest, `ccx run`, `claude -p` and
   `codex exec`: 13 rows carry `between_units` findings (69 in all), and the real ledger was written 8 times (verifier). So m1r5
   is left out of the rule.
7. m1h2 has no frozen snapshot: there are two different `daily.sha256` values (89 rows and 31 rows), and no
   `switches_applied`.
8. m1h2's failed units' folders were deleted. In `m1r5-results-artifacts/`, only 4 of the 21 folders belong to this
   run. The other 17 are left over from the run stopped at 18:55–19:02.
9. The rule's median condition and the paired statistics point opposite ways (see above).
10. The number of requests per sub-agent run is not recorded (`req=` in the log counts the lead's requests).
11. The samples are small: 10 tasks × 3 rounds plus 10 tasks × 2 rounds. Near a 95 % baseline, 50 pairs can only show
    a drop of about 10 points or more.

## Why no re-run

A clean re-run of the r5 half for the baseline and leantools would be 40 units, about $4.8. At most it would settle
leantools' right-answer condition.

The person's rule changes a default only if the switch is right no less often **and** saves something real. On r5
no switch's ratio of medians reaches 0.85, and the paired statistics are about 1 for all three. A clean re-run would
not clear that bar.

So the budget goes to fewer runs per unit (B3 §2.2) instead.

## Decision

All three switches stay at today's behaviour by default and are marked experimental in `config/tiers.toml` and on
the [features](../features.md#experimental-lean-sub-agent-switches-subagent-off-until-measured) page:

- nomem: Unknown;
- clean: Fail;
- leantools: Unknown under the registered rule.

See [DECISIONS](../DECISIONS.md).

Anyone can still turn a switch on in `hub/ccx/tiers.toml`. This report shows neither that a switch costs right
answers, except clean on the hold-out half, nor that it saves tokens.
