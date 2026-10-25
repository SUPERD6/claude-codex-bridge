# Seven cores, round 2: does dividing the work beat one model, and is it cheaper? (report)

English · [中文](2026-10-25-seven-cores-r2.zh.md) · 2026-10-25 · ccx 0.4.0 (main `3932bf9` + this PR's lenient `review.verdict`) · claude 2.1.309 · codex-cli 0.164.0 · Windows 11

Plan (written before the runs, with its change log): [2026-10-25-seven-cores-r2-plan.md](2026-10-25-seven-cores-r2-plan.md). Scrubbed data: [data/2026-10-25-seven-cores-r2.json](data/2026-10-25-seven-cores-r2.json). Nothing here is compared directly with round 1; every group re-ran its baseline arm on the same code.

## Findings first

| # | Question | Verdict | Evidence in one line |
|---|---|---|---|
| 4-A | Does `ccx way` work | **Yes** | 6/6 finished: every plan had `[step]` and `[accept]` items, every acceptance parsed as pass, all 3 `PICK`s parsed. $0.08–0.12 and 50–58 s each |
| 4-C | Does review make results more correct | **Right direction, not significant** | off 33/36, on 36/36 (discordant 0 : 3, McNemar p = 0.25, Holm 0.75). All three differences are the one real bug in inventory, which the review caught every time. Cost: 3.9× spend (+$0.004 per task), +20 s |
| 4-C | The new default `--review auto` | **Same as no review in this design** | Never fired in 36 runs: "weak evidence" needs the same check command in the same folder to have let wrong work through before, and a fresh repo has no history |
| 4-B | Is dividing the work more correct than one cheap model | **Right direction, not significant** | luna low alone 12/14, `ccx way` 14/14, draft + checked draft 14/14 (0 : 2 each, p = 0.5, Holm 1.0). Again all differences are inventory |
| 4-B / 5 | Is dividing cheaper | **No, much dearer** | `ccx way` 38.7× spend (+$0.089 per task), +34 s; draft + check 20× (+$0.045), +25 s; way's acceptance passed in the first round all 14 times, no rework |
| 5 | Is splitting into many parallel runs faster and cheaper | **Faster, not cheaper** | Ten pieces: 1 run 68–83 s, 3 runs 47–52 s, 10 runs 29–31 s; tokens 210k → 400k → 980k. Each extra run costs about 93k start-up tokens; at 100 runs start-up is about 100% of all tokens (extrapolated) |
| 4-H | Told explicitly, do agents start their own sub-agents | **None did** | Codex luna low 2/2 and Claude haiku low 2/2 did not (Claude had the Task tool and an explicit request) |
| 4 / 5 | Auto routing vs fixed sonnet | **Equally right; the saving comes from the test setup** | 36/36 right. Routing picked deepseek-flash for the 4 five-minute tasks (about 25× cheaper), total spend 0.69–0.74×; but only because the hub did not know Claude's quota: with the quota known and below 70%, the same tasks got sonnet (seen in group 9) |
| 4-D | Tiers by difficulty | **Only two tiers** | 5 min → deepseek-flash low, 15 and 30 min both sonnet medium; the brief's content changes nothing; luna low, right 97% of the time on 15-minute tasks here, was never picked |
| 6 | More accurate with use | **No evidence** | The learning hub ran sonnet all 24 times, all right; Brier 0.005 → 0.003, but with everything right Brier only measures how far the prediction is from 1 |
| 7 | F11 Claude-side cap, 4-I queue killed and resumed | **Not run** | The first eight groups cost $5.89, leaving $0.11; waiting for the person's decision |

**Total spend $5.89** (4-A $0.58, three screens $0.11, 4-C $0.59, 4-B $2.00, parallel + 4-H $0.18, routing $1.33, learning $1.09), under the $6 cap.

**The most important result**: on medium tasks with a clear brief, the cheap model (gpt-6-luna low) is already near the ceiling: screening three batches of 22 purpose-built "trap" tasks, it was right 47 times out of 49, and only inventory trips it. So every "dividing / reviewing makes it more correct" comparison this round turns on one task, too small a sample to be significant; what is certain is the price: review 3.9×, dividing 20–39×. On this kind of task, **a cheap model plus the other vendor's cheapest review** ($0.006 per task) matched the divided arms' correctness at about 7% of `ccx way`'s cost.

## 1. Method

- Script `scripts/eval/r2.py`, tasks `scripts/eval/tasks_r2.py`. Every unit gets a fresh repo and a fresh throwaway hub (`CCX_HUB`): A/B self-runs off, the DeepSeek cap raised but still counted, Codex only gpt-6-luna (T2–T4 set to luna low, sol/astra marked unavailable to routing), the quota probe off. Every run has `--no-ab` and an `eval-r2:` label.
- A hidden acceptance test the agents never see decides right or wrong; it is recorded with `ccx verify` in the unit's own hub. Spend is API-equivalent dollars from the ledger (DeepSeek is real money).
- Statistics: the task is the independent unit; exact McNemar for right/wrong; median paired difference, task-level bootstrap 95% interval and sign test for spend, tokens and time. The three primary tests (4-C on vs off, 4-B single vs way, single vs draft) are Holm-adjusted.

## 2. Results by group

### 2.1 4-A `ccx way` smoke (n = 6)

| Task | Risk | Result | plan `[step]` / `[accept]` | Acceptance / pick | Spend | s |
|---|---|---|---|---|---|---|
| cart | visible | right | 7 / 4 | pass | $0.108 | 50 |
| inventory | visible | right | 6 / 2 | pass | $0.091 | 57 |
| merge | visible | right | 4 / 4 | pass | $0.079 | 54 |
| cart | critical | right | — | PICK B (A and B both right) | $0.123 | 54 |
| inventory | critical | right | — | PICK B (only B right: A, Codex's, returned Items again) | $0.098 | 58 |
| merge | critical | right | — | PICK B (both right) | $0.083 | 52 |

- Formats held, so `ccx/ways.py`'s parsing was not changed. But 4-C found the reviewer (haiku) sometimes writes its summary in Chinese without the `REVIEW:` line, and `ccx way`'s acceptance uses the same `review.verdict`, so this PR makes that parsing lenient (see 2.2).
- With two vendors installed, the judge for critical is the second builder's vendor (Claude), and it picked Claude's own version B all 3 times. For inventory B really was the only right one; in the other two both were right, so no bias can be seen. n = 3, recorded only.

### 2.2 4-C review again

Tasks: the 9 traps (TRAPS2) plus 3 easy ones from the first batch as controls, 3 rounds each; sub-agent luna low, no escalation. The reviewer was claude haiku low every time.

| Metric | off | on | auto |
|---|---|---|---|
| Right | 33/36 (Wilson 0.78–0.97) | **36/36** (0.90–1.0) | 31/36 (0.71–0.94) |
| ccx said ok, hidden test failed | 3 | 0 | 5 |
| Median spend | $0.0021 | $0.0063 | $0.0022 |
| Median time | 19.9 s | 42.7 s | 19.1 s |

- on vs off: discordant 0 : 3, McNemar p = 0.25 (Holm 0.75). Paired difference: spend +$0.0040 (task-level interval [+$0.0038, +$0.0075], sign test p < 0.001), +63k tokens, +20 s. Of the on arm's $0.31, the reviewer is $0.22.
- The first review said issues 7 times: inventory 3 times (exactly the bug the off arm got wrong 3/3: low_stock returns Items, not SKUs), all right after the fix round; tags twice and merge twice, all right after the fix too, but whether those four were wrong before the fix was not tested separately, so they count neither as catches nor as false alarms.
- auto vs off: the automatic review never fired in 36 runs, so the two arms are the same thing; auto's 2 extra misses (tags) are luna low's own variance (off got tags 3/3). Why: see the findings table; weak evidence needs history, and a fresh repo has none.
- **The 31 units before the fix** (tag `r2-prefix`, not in the comparison): 2 of the 10 on-arm reviews ended `unclear`, one of them inventory — haiku wrote its summary in Chinese and listed the real bug as `[must]`, but without `REVIEW: issues`, so no fix round ran and the result stayed wrong. This PR changes `review.verdict`: without a `REVIEW:` line, a `[must]` item means issues and only `[note]` items mean pass, marked `format: lenient`; the prefix also tolerates markdown and a full-width colon. The whole group was re-run after the fix; the table shows the re-run.

### 2.3 4-B divided vs one model

Tasks chosen by the fallback rule fixed in advance (fewer than 7 tasks fail the cheap model): inventory, dupparse, cache, rounding, exporter, tags, config, 2 rounds each.

| Metric | single (luna low alone) | way (claude sonnet plans → codex luna builds → claude accepts) | draft (claude sonnet drafts → codex luna checks the draft, read-only → codex luna builds) |
|---|---|---|---|
| Right | 12/14 (0.60–0.96) | 14/14 (0.78–1.0) | 14/14 (0.78–1.0) |
| Discordant (vs single) | — | 0 : 2, p = 0.5, Holm 1.0 | 0 : 2, p = 0.5, Holm 1.0 |
| Median spend | $0.0024 | $0.0916 (38.7×) | $0.0474 (20.0×) |
| Paired difference (task interval) | — | +$0.089 [+$0.080, +$0.098], p = 0.016 | +$0.045 [+$0.042, +$0.048], p = 0.016 |
| Median total tokens | 94k | 213k | 172k |
| Median time | 18.8 s | 50.5 s | 43.9 s |
| Rework | — | 0 (acceptance passed in round 1, 14/14) | the draft check raised `[must]` 5 times |
| ccx said ok, hidden test failed | 2 | 0 | 0 |

- Both divided arms differ from single only on inventory (single 2/2 wrong, both divided arms 2/2 right). way vs draft: both 14/14; way 1.9× dearer and 9 s slower.
- Draft + checked draft (a light version of the person's "talk first, then hand out") is as right as way at half the cost; but both are far dearer than "single + review" (4-C's on arm also fixed inventory 3/3, at about $0.006).
- **Bias note**: the tasks were picked because the cheap model fails them, but only one does; correctness sits near the ceiling, so this holds for "medium tasks with a clear brief" only. Vague briefs, large codebases or really hard tasks were not tested.

### 2.4 Parallel scale (PAR10: ten unrelated small modules, 2 rounds)

| Arm | Pieces right | Merge conflicts | Wall time | Total tokens (work only) | Spend (work only) | Spend incl. automatic review |
|---|---|---|---|---|---|---|
| p1: one Codex does all ten | 10/10, 10/10 | 0 | 83 / 68 s | 172k / 132k | $0.0049 / $0.0039 | $0.0094 / $0.0093 |
| p3: 3 runs in parallel (`ccx batch`, one worktree each) | 10/10, 10/10 | 0 | 52 / 47 s | 296k / 316k | $0.0080 / $0.0086 | $0.019 |
| p10: 10 runs in parallel | 10/10, 10/10 | 0 | 29 / 31 s | 977k / 981k | $0.023 / $0.025 | $0.023 / $0.025 |
| native: one Codex told to use its own sub-agents | 10/10, 10/10 | 0 | 71 / 71 s | 129k / 126k | $0.0036 / $0.0039 | $0.0095 / $0.0098 |

- Fit: tokens ≈ 45k + **93k × runs**. Every Codex run starts by reading about 90k tokens (mostly cached) of system prompt and tool definitions. Extrapolated: start-up is about 67% of tokens at 1 run, 95% at 10, about 100% at 100 (9.3M tokens, about $0.23 at luna low; the ten pieces themselves need about 45k).
- Wall time: 10 runs are about 2.5× faster than 1, but already at the floor of "a run takes at least 20–30 s"; 100 runs would not be much faster, and `max_parallel`, quota and rate limits apply. Merging 10 worktrees took about 4.5 s with no conflicts (the pieces touch disjoint files).
- Verdict (must hold in both rounds): p3 and p10 are **faster**; neither is **cheaper** (2.3× and 7.4× the tokens). p1's automatic review (fires at ≥ 50 changed lines) is half its total spend; p10's pieces are small and were not reviewed.

### 2.5 4-H own sub-agents on / off

| Pair | Started any? | Right | Time | Spend |
|---|---|---|---|---|
| Codex luna low: p1 (`--no-subagents`) vs native (`--parallel`) | native 2/2 **did not** (no `spawn_agent`) | both 10/10 | 76 vs 71 s | same |
| Claude haiku low: c_off vs c_on (`--parallel`) | c_on 2/2 **did not** (Task in its tool list, an explicit request, used only Read/Write/Bash) | both 10/10 | 42–61 vs 42–47 s | same |

In round 1 Codex luna low did start sub-agents on an explicit request (the spending-cap test); this time, with ten small functions, it wrote them itself. n = 2, recorded only.

### 2.6 (b') routing: fixed sonnet vs auto (warm / cold)

- The warm hub used a frozen copy of the routing-state of the person's default hub (SHA-256 `c8749b59…`, copied 10/25 14:17; it was `2a353b8a…` when group 1 started, updated meanwhile by other sessions' real runs).
- 12 tasks × 1 round: 36/36 right, "ccx said ok but the hidden test failed" 0 times, no escalation.
- Picks: warm and cold **identical**: the 4 five-minute tasks → deepseek-flash low ($0.001–0.005), the 8 fifteen-minute tasks → sonnet medium (the fixed arm's model). Total: fixed $0.548, warm $0.404 (0.74×), cold $0.379 (0.69×); median task-level difference near 0 (8/12 picked the same model); no difference in time.
- **But this saving comes from the test setup**: each unit had a fresh hub with the quota probe off, so routing did not know Claude's quota and also weighed pay-per-token DeepSeek. The long-lived hub of group 9 had the quota on record (30% of five hours, 38% of the week) and picked sonnet for the same small tasks (ccx weighs pay-per-token providers only from 70% quota use). In real use with quota to spare, auto routing is about the same as fixed sonnet.

### 2.7 4-D tiers by difficulty (`ccx route`, no model call)

| Difficulty | warm | cold |
|---|---|---|
| 5 min | deepseek-flash low (p 0.92) | deepseek-flash low (p 0.81) |
| 15 min | sonnet medium (p 0.90) | sonnet medium (p 0.95) |
| 30 min | sonnet medium (p 0.74) | sonnet medium (p 0.84) |

The three different briefs (slugify, csvstats, cart) got exactly the same picks: only the minutes matter. By the rule fixed in advance this counts as "tiering works" (≥2 tiers), but 15 and 30 minutes are not told apart, and at 30 minutes the predicted success falls to 0.74 without moving up; meanwhile luna low was right 97% of the time on 15-minute tasks here and was never picked (its prior for b ≈ 3.9 is about 52% success).

### 2.8 More accurate with use

| | phase1 (the learning hub) | phase2 (same hub, again) | frozen (= 2.6's warm arm) |
|---|---|---|---|
| Tier picked | 12/12 sonnet medium | 12/12 sonnet medium | 8 sonnet + 4 deepseek-flash |
| Right | 12/12 | 12/12 | 12/12 |
| Brier | 0.005 | 0.003 | 0.0085 |

- The routing state changed after every `ccx verify` (hash changed 24/24 times), the picks did not. With everything right, Brier only measures how far the prediction is from 1; 0.005 → 0.003 just means sonnet's prediction rose from about 0.93 to about 0.95. The frozen arm picked other tiers and is not directly comparable. By the rule fixed in advance: **no evidence of becoming more accurate with use**. A real test needs tasks that fail (so routing sees failures) and more time.

### 2.9 F11 + 4-I

Not run. The first eight groups spent $5.89, leaving $0.11; F11 needs Claude sonnet to really start sub-agents and 4-I is a four-piece queue, together an estimated $0.08–0.3 that may cross $6, so by the rules the person decides first.

## 3. Problems found

| # | Problem | How found | Status |
|---|---|---|---|
| 1 | A reviewer without a `REVIEW:` line (Chinese summary) ended `unclear`, so a real bug it listed as `[must]` got no fix round | 4-C before the fix, inventory | **Fixed in this PR** (lenient parsing, `format: lenient`); `ccx way`'s acceptance benefits too |
| 2 | The weak-evidence review needs history in the same folder; new repos / new tasks never trigger it, so `--review auto` equalled no review all 36 times | 4-C auto arm | Not fixed. Suggestion: with no history, use this check command's record elsewhere, or "the visible test touches only part of the changed files" as weak evidence |
| 3 | About 90k start-up tokens per run when parallel; at 10 runs that is 95% | parallel scale | Not fixed. Suggestion: `ccx batch` / `q run` merge very small pieces (say under 5 minutes) into a few runs; `task-split` estimates with this number |
| 4 | Told explicitly, luna low and haiku low do not start their own sub-agents | 4-H | Recorded; F14's wording does nothing for small pieces |
| 5 | Without the quota routing picks pay-per-token DeepSeek, with it not: the same task is routed differently in a new and an old hub | (b') vs learning | By design (pay-per-token only from 70%), but evaluations must mind it; suggestion: don't turn off the quota probe in eval scripts, or write a fixed quota into the hub |
| 6 | Routing picks sonnet medium at 15 and 30 minutes and never luna low, which is right 97% of the time on these tasks | 4-D, screens | Not fixed. luna low's prior (about 52% at b ≈ 3.9) is far below what was measured here; these verdicts need to reach learning (this round ran in throwaway hubs and did not touch the person's routing state) |
| 7 | `scripts/eval/common.read_jsonl` used `splitlines()`; a U+2028 inside a JSON string cut a row in two | 4-C stopped mid-way | **Fixed in this PR** |
| 8 | Read-only git files left by a killed unit made deleting its folder fail on re-run | 4-C | **Fixed in this PR** (eval script) |

## 4. Uncertainty

- Only "medium tasks with a clear brief" were tested, where the cheap model is already near the ceiling. With vague briefs, large codebases or many files, the value of dividing and reviewing may differ; not tested.
- 4-B has n = 14 per arm over 7 tasks, and only one task separates the arms; 4-H, parallel scale, routing and learning are small descriptive samples.
- The critical judge shares a vendor with the second builder (only two vendors installed) and may favour its own version.
- Spend is at API-equivalent prices; under subscriptions the real cost differs.
