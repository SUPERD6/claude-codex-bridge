# The seven cores: real-run A/B tests and functional checks (round 1: Claude Code + Codex)

English · [中文](2026-10-24-seven-cores-ab.zh.md) · 2026-10-24 · ccx 0.4.x (A/B on main `e94b670` + this branch's scripts; discuss on main `f6fbc7d`) · claude 2.1.309 · codex-cli 0.164.0 · Windows 11

Plan (checks and decision rules written down first): [2026-10-24-seven-cores-plan.md](2026-10-24-seven-cores-plan.md). Round 2 (Gemini, DeepSeek) will be appended as section 6.

## Verdicts

| # | Core | Verdict | Evidence in one line |
|---|---|---|---|
| 1 | Agents lead each other | **works** (Claude ↔ Codex); Gemini/DeepSeek **not tested yet** | Claude lead → Codex sub-agent delegated 21/21; Codex lead → Claude sub-agent done right (with the user's own sandbox setting). A Codex lead in Windows `workspace-write` can't delegate: cause found, the `ccx doctor` check is in #28 |
| 2 | Two models talk directly | **works** (n = 1) | `ccx discuss`: 5 turns between two vendors, Claude's specific objections were taken up by Codex in the next round, the conclusion was right. It cost about 8× its estimate |
| 3 | Shared memory | **partly** | Project memory reaches the sub-agent and is followed: with the note 9/9 right, without 0/9 (McNemar p = 0.004, Holm 0.016). Writing to shared memory after the user agrees (H5) and hub memory via start hooks were not tested |
| 4 | Working together is better | **no evidence it is better this round** | Routing picked the same model as the fixed arm 21/21 times (sonnet medium) and only added ~9 s; independent review made it 34× the cost and 3.2× the time, pass rate 18/21 vs 19/21, and missed the same real bug 3 times |
| 5 | Cheaper, efficient | **partly** | After delegating, the lead made 1 request fewer on every task (21/21), but total spend was the same (ratio 1.02, p = 1), total tokens 3.3×, 23 s slower, and the cheap sub-agent got one medium task wrong 3/3. It only saves when the lead is a long conversation: at the real median context, ~352k fewer tokens read per task (~$0.07) |
| 6 | Gets more accurate with use | **not tested yet** | No design over time. Only signal: this round's verdicts raised routing's predicted p for sonnet from 0.93 to 0.945; the pick didn't change |
| 7 | Nothing lost, no mess, in control | **partly** | undo restores byte for byte ✓; killed halfway, `task resume` continues the same session and finishes ✓; the spend cap really triggered on Codex ✓; killed before the session began, resume did nothing (found → fixed in #26); a killed run's spend is missing from the ledger; ccx said "passed" while the hidden test failed 14 times |

Round 1 spent about **$5.80** (A/B $5.16, pilot $0.32, discuss $0.28, functional checks ~$0.03), within $10.

## 1. Method

- **A/B**: `scripts/eval/seven_ab.py`. 4 comparisons, 3 rounds per task per comparison; within a round the task order and each task's arm order are random (seed 7); same comparison, round and task = one pair: 72 pairs, 144 units. Every arm is a fresh scratch git repo and a fresh session. Right or wrong is decided by a hidden acceptance test the agents never see, recorded with `ccx verify`. Every `ccx run` has `--no-ab`, labels `eval-7c:*`, apart from the running H11 week-long trial (`ccx trial`).
- **Tasks**: 7 core tasks (4 small + 3 new medium ones: inventory touches two files, csvstats, lru) and 3 memory tasks (the brief leaves out one project convention that the hidden test checks). `tests/test_eval_tasks.py` confirms that all 15 tasks' start code fails the hidden test and the reference solution passes.
- **The independent unit is the task** (core n = 7, memory n = 3): a task's 3 paired differences are averaged, then a sign test and a bootstrap 95% interval run over tasks. Intervals and p in the tables are pair level (n = 21 / 9) unless marked, descriptive only. The 4 primary tests are Holm corrected.
- **Functional checks**: `scripts/eval/seven_func.py` (codex-lead, resume, undo, budget), one real scenario each, judged by files and the hidden test. `ccx discuss` ran from main.
- The pilot (`pilot`, 8 units) found a script bug: the project memory was never written (no `ccx ctx init` first). Fixed before the real run; pilot data are not in the results.

## 2. A/B results (round 1, `--tag r1`)

### 2.1 Primary tests

| Exp | Primary metric | Effect (treatment − control) | task-level p | Holm | Verdict |
|---|---|---|---|---|---|
| (a) self → delegate to Codex | total spend | +$0.0005/task (ratio 1.02) | 1.0 | 1.0 | no saving (small lead) |
| (b) fixed sonnet → routed | total spend | +$0.0014/task (ratio 1.03) | 0.45 | 1.0 | no difference (same model picked) |
| (c) no review → review | pass rate | 19/21 → 18/21 | 1.0 (McNemar) | 1.0 | not better |
| (d) no memory → memory | pass rate | 0/9 → 9/9 | 0.004 (McNemar) | **0.016** | works |

### 2.2 (a) The lead does it vs delegates to Codex (core 5)

Lead = fresh headless Claude sonnet (medium, slim start); sub-agent = gpt-6-luna low, `--review off`.

| Metric | self (median) | delegate (median) | median paired diff [95% CI] | sign test p (pair / task) |
|---|---|---|---|---|
| right | 21/21 (Wilson 0.85–1.0) | 18/21 (0.65–0.95) | discordant 3 : 0 for self | McNemar 0.25 |
| lead requests | 3 | 2 | −1 [−1, −1] | <0.001 / 0.016 |
| lead tokens read + written | 35,637 | 24,319 | −11,129 [−11,398, −11,049] | <0.001 / 0.016 |
| lead spend | $0.0344 | $0.0323 | −$0.0019 [−$0.0036, −$0.0015] | <0.001 / 0.125 |
| **total spend (lead + sub-agent)** | $0.0344 | $0.0351 | +$0.0005 [−$0.0011, +$0.0015] | 0.66 / 1.0 |
| **total tokens** | 35,637 | 119,010 | +83,226 [+82,537, +88,943] (3.3×) | <0.001 / 0.016 |
| wall time | 10.9 s | 33.7 s | +22.6 s [+21.5, +24.2] | <0.001 / 0.016 |
| lead reading at real context (352k/request), extrapolated | 1.056M | 0.704M | −352k | — |

| Task | right self/del | requests self/del | total $ self/del | s self/del |
|---|---|---|---|---|
| slugify | 3/3 · 3/3 | 3 / 2 | $0.030 / $0.034 | 9 / 32 |
| duration | 3/3 · 3/3 | 3 / 2 | $0.034 / $0.035 | 11 / 34 |
| intervals | 3/3 · 3/3 | 3 / 2 | $0.036 / $0.034 | 11 / 33 |
| cli-json | 3/3 · 3/3 | 3 / 2 | $0.034 / $0.036 | 11 / 36 |
| inventory | 3/3 · **0/3** | 5 / 2 | $0.049 / $0.037 | 15 / 37 |
| csvstats | 3/3 · 3/3 | 3 / 2 | $0.036 / $0.036 | 12 / 33 |
| lru | 3/3 · 3/3 | 3 / 2 | $0.034 / $0.036 | 10 / 35 |

- The lead always called `ccx run` once and answered when the check had passed, without editing anything itself (0 rework), as sonnet did last round: agent-delegate's "the check passed, don't re-run it" works.
- **Only the lead's own requests are saved**: the sub-agent reads 90–100k tokens of its own (mostly cached), so total tokens are 3.3×; at API prices the ~$0.002 the sonnet lead saves is eaten by the ~$0.002 sub-agent.
- **Where delegating got worse**: inventory was wrong in all 3 rounds, each time luna low made `low_stock` return Item objects instead of SKUs (the brief says "the SKUs"). The lead trusted ccx's check (the visible test only checks summary) and didn't notice.
- **Extrapolation**: a real lead re-reads 352k tokens per request (median, J0, last 7 days). One request fewer ≈ 352k tokens ≈ $0.07 at Opus cache-read price ($0.2/M), minus ~$0.002–0.004 for the sub-agent: ~$0.07 saved per small task, ~23 s more waiting, possibly wrong. Estimated, not measured in a long conversation.

### 2.3 (b) One fixed model vs routing (core 4: division of labour)

| Metric | fixed sonnet medium | routed (`--to auto --minutes 5/15`) | median paired diff [CI] | p (pair / task) |
|---|---|---|---|---|
| right | 21/21 | 21/21 | — | — |
| picked | sonnet medium | **sonnet medium 21/21**, no escalation | — | — |
| total spend | $0.0462 | $0.0475 | +$0.0014 [+$0.0002, +$0.0032] | 0.08 / 0.45 |
| total tokens | 44,288 | 58,560 | +14,497 [+155, +15,377] | 0.03 / 0.45 |
| wall time | 13.2 s | 21.8 s | +9.0 s [+7.7, +9.6] | <0.001 / 0.016 |

- Routing picked sonnet medium for 5-minute (b ≈ 2.3) and 15-minute (b ≈ 3.9) tasks alike (predicted success 0.93–0.99), the same model as the fixed arm, so this comparison **cannot show the value of dividing work**; it only measured routing's own overhead: the sub-agent took the same time in both arms (e.g. slugify 8.9 s vs 9.5 s), the extra ~8 s is ccx choosing the route.
- Secondary comparison (not randomised within one experiment, but same round and task): routed (sonnet) vs a cheap fixed model ((c)'s no-review arm, luna low): right 21/21 vs 19/21, about **22× the spend** (+$0.045/task, task-level CI [+$0.042, +$0.053], p = 0.016). Routing chose the expensive, safe rung; on these tasks the cheap model was wrong only on inventory.
- `ccx route "…" --minutes 5` gives haiku low on this machine, `ccx run --to auto` gave sonnet medium (the run adds facts read from the repo and the lead bias). Not investigated.

### 2.4 (c) No review vs independent review (core 4)

Sub-agent luna low, no escalation. ccx picked the reviewer: **claude sonnet medium every time**.

| Metric | no review | review | median paired diff [CI] | p (pair / task) |
|---|---|---|---|---|
| right | 19/21 (0.71–0.97) | 18/21 (0.65–0.95) | discordant 1 : 0 for no review | McNemar 1.0 |
| total spend | $0.0022 | $0.0802 | +$0.078 [+$0.071, +$0.083] (**34×**) | <0.001 / 0.016 |
| total tokens | 94,175 | 233,206 | +132,858 (2.3×) | <0.001 / 0.016 |
| wall time | 25.1 s | 85.5 s | +60.4 s | <0.001 / 0.016 |

- The first review said "issues" 15/21 times, almost always "the new behaviour is untested", so one fix round followed (tests added) and the second review passed every time (21/21 "pass" in the end). **The fix round turned no wrong result into a right one** (0 times).
- inventory was wrong in all 3 rounds (the same Item-vs-SKU bug); all three reviews only asked for tests and never named it; the added tests encoded the wrong behaviour and "passed". ccx said "passed" while the hidden test failed: 3 times in the review arm, 2 in the no-review arm.
- On tasks like these the review is an expensive test-writer, not a bug finder; 97% of the cost is the reviewer (sonnet) itself.

### 2.5 (d) No memory vs project memory (core 3)

| Task | Convention the hidden test checks | no memory | memory |
|---|---|---|---|
| mem-errors | raise `errors.AppError`, message starts with the function name | 0/3 | 3/3 |
| mem-money | money returned as integer cents | 0/3 | 3/3 |
| mem-log | one line on the `app` logger per call | 0/3 | 3/3 |

McNemar p = 0.004 (9 : 0), Holm corrected 0.016. Cost: ~$0.0007 and ~2 s more per task (one more file read). The effect is partly built in (without the note the convention can't be known); what it shows is that **project memory in `.ccx/context.md` is pointed out to the sub-agent by ccx, and a real sub-agent (luna low) reads it and follows it**: 3 conventions, 9 out of 9.

Not tested: H5's "suggest → user agrees → written to shared memory" (writes to the user's real hub, needs their yes), hub shared memory reaching Codex/Claude sub-agents via start hooks, I6's notes in the brief for tools without a start hook (Gemini etc., round 2).

## 3. Functional checks

| Core | Check | Result | Evidence |
|---|---|---|---|
| 1 | Claude lead → Codex sub-agent | ✓ | (a): 21/21 really delegated (ledger `caller=claude`, `to=codex`) |
| 1 | Codex lead (`codex exec`, luna low) → `ccx run --to claude` (haiku) | ✓ (the user's own sandbox setting) | hidden test passed; 2 ledger rows `caller=codex, to=claude`. Codex's first try failed on PowerShell quoting; after the working one it **delegated the same work again** ($0.004 extra) |
| 1 | same, `-s workspace-write` | ✗ → cause found | failed twice: `ccx run` could not write the hub's runs folder (WinError 5). The coordinating session found on the real machine that under Windows workspace-write a Claude sub-agent's every edit is refused, writable_roots doesn't help, only danger-full-access works; the `ccx doctor` check is in #28. Not a ccx bug |
| 2 | `ccx discuss` (two vendors, up to 3 rounds) | ✓ | below |
| 7 | killed halfway → `ccx task resume` | ✓ (mechanism) | killed after 15 s with the hidden test failing; resume continued **the same Codex session** (same session id) and finished, check passed. The hidden test still failed (the inventory Item/SKU error again: the model, not the resume) |
| 7 | killed before the session began → resume | ✗ → **fixed in #26** | killed at 10 s, no session id yet; resume only said "do this step yourself" and returned 0. Since #26 it restarts the step from the saved brief (verified by the coordinating session, real run killed after 4 s) |
| 7 | killed too late | — | at 20 s the sub-agent had already finished; shows only that resume doesn't redo work |
| 7 | `ccx undo --apply` | ✓ | the run changed `textutil.py`; after undo every file's hash equals the one before the run |
| 7 | spend cap `--budget 0.0001` + `--parallel`, Codex luna low | ✓ | Codex followed F14's explicit request and started sub-agents of its own; stopped as soon as they spent, `kind = over_budget`, with the `ccx resume --budget` hint |
| 7 | same, Claude haiku low | **not tested** | with the Task tool and an explicit request, haiku wrote everything with Bash and started no sub-agent, so the cap had no chance to trigger |
| 7 | ccx said passed, hidden test failed | 14 times | (c) 5, (d) no-memory arm 9 (by design: the check only runs the visible test); (a)(b) 0 |

**The `ccx discuss` run** (question: string price to integer cents with `int(float(p)*100)` / `round(float(p)*100)` / `int(Decimal(p)*100)` / splitting the string; known: `int(float('0.29')*100)` = 28 is wrong):

| Round | Role | Who | What it said |
|---|---|---|---|
| 1 | propose | Codex gpt-6.1-sol | Decimal, validate first, reject more than two decimals; A gives 28 for 0.29 |
| 1 | critique | Claude sonnet | `[must]` Decimal accepts NaN, Infinity, 1e2, full-width digits: strict regex first; `[must]` default 28-digit precision |
| 2 | propose | Codex | switched to splitting the string (D), adopted the strict regex |
| 2 | critique | Claude | agree |
| 2 | judge | Codex (two vendors only: the proposer also judged, the result says so) | D; 0.29→29, -3.10→-310, reject more than two decimals |

Right conclusion; the critic's specific points changed the proposal. Problems: **it cost $0.283, `--dry-run` estimated $0.036 (~8×)**; the default tier T2 put Codex on gpt-6.1-sol (Codex quota is tight this week; every other run used luna). n = 1.

## 4. Problems found

| # | Problem | Found by | Status |
|---|---|---|---|
| 1 | killed before its session began, `task resume` returned 0 and did nothing | resume (10 s) | **fixed** (#26) |
| 2 | a Codex lead in Windows `workspace-write` can't use ccx | codex-lead | **cause found**: the sandbox itself, only danger-full-access works; `ccx doctor` check in #28 |
| 3 | the reviewer is picked as claude sonnet medium, $0.04–0.09 a review, 20–40× a luna low sub-agent; reviews mostly ask for tests and missed the real bug 3 times | (c) | not fixed. Suggest: pick the reviewer by price (sonnet only after haiku fails), make "untested" a `[note]`, have the review check return values item by item against the task |
| 4 | `ccx discuss` underestimates spend ~8×; the default T2 ignores quota | discuss | not fixed. Suggest: estimate from the context each turn will read; step down when quota is tight |
| 5 | `--to auto` routing adds ~8 s per run | (b) | not fixed, not investigated |
| 6 | `ccx run --to auto` and `ccx route` give different rungs for the same brief (sonnet medium vs haiku low) | (b) pilot | not investigated |
| 7 | a killed run has no attempt record: what it spent before the kill is missing from the ledger | resume | not fixed |
| 8 | `ccx undo --apply` records the run as wrong even when it was right, which feeds routing | undo (I set it back with `--ok 1`) | not fixed. Suggest: record "undone" without a verdict, or ask |
| 9 | the spend-cap message rounds to "$0.00 (cap $0.00)" | budget | not fixed (cosmetic) |
| 10 | a Codex lead delegated the same work twice after it had succeeded | codex-lead | not fixed; agent-delegate could say "once you have a run_id and a check, don't delegate again" |
| 11 | haiku low with the Task tool and an explicit parallel request still starts no sub-agent | budget-claude | not fixed; the Claude-side cap is still untested |

## 5. Limitations

- **The lead is not a real one**: headless, slim start, ~12k tokens of context; a real lead is a long conversation (median 352k tokens/request) on Opus. Core 5's dollar figure is extrapolated.
- **Small tasks**: 3–5 requests done by yourself, 2 at least when delegated, so at most 1–3 requests can be saved. Large real tasks were not tested.
- **The cheapest sub-agent only** (luna low, this week's Codex quota); the routing comparison's fixed arm used sonnet. Stronger sub-agents would change (a)'s and (c)'s pass rates.
- **Sample**: the independent unit is the task, core n = 7, memory n = 3; a task's 3 rounds are repeated measures. "Not better" in (c) and "no difference" in (b) are not proof of no effect.
- **(d)'s effect is partly built in**: it shows delivery and compliance, not that memory makes a model smarter.
- **Wall time**: functional checks ran for a few minutes alongside the A/B, a small disturbance.
- **Core 6 has no controlled design**: it needs verdicts piling up over time, comparing early vs late prediction accuracy (Brier score); this round is one day.

## 6. Round 2 (to be appended)

Gemini and DeepSeek (`--provider deepseek-codex` is merged; the DeepSeek Harness adapter has not been run for real) as sub-agents: (a)'s delegate arm and (d) (Gemini has no start hook, so it tests I6's notes in the brief), plus core 1's functional check. Budget: the remaining ~$4, DeepSeek at most $1 a day.

## 7. Reproduce

```
python scripts/eval/seven_ab.py plan --rounds 3 --seed 7
python scripts/eval/seven_ab.py run --rounds 3 --seed 7 --tag r1 --budget 6
python scripts/eval/seven_ab.py summary --tag r1
python scripts/eval/seven_func.py undo | resume --kill-after 15 | budget --budget-to codex | codex-lead
python ccx.py discuss --question-file q.txt [--dry-run]
```

Raw data in `.ccx/eval/seven/` (`results.jsonl` 144 rows, `pilot.jsonl`, `func.jsonl`, `discuss-r1.json`, `summary-r1.json`), not in git (local paths); a de-identified summary is [data/2026-10-24-seven-cores-r1.json](data/2026-10-24-seven-cores-r1.json). Verdicts are in the ccx ledger under `eval-7c:*`.
