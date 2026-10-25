# Test plan for the seven cores (A/B and functional checks)

English · [中文](2026-10-24-seven-cores-plan.zh.md) · 2026-10-24 · written before the real runs; results in [2026-10-24-seven-cores-ab.md](2026-10-24-seven-cores-ab.md)

## 0. Purpose and principles

Answer with real runs whether each of relayline's (`ccx`) seven cores **works / partly / doesn't / not tested yet**:

- **No self-assessment**: right or wrong is decided by a hidden acceptance test the agents never see, not by an
  agent's or ccx's own "done". ccx's own judgement (`check`, `ok`) is kept separately, to count how often ccx said
  "passed" when the work was wrong.
- **Decision rules written down first** (section 3) and applied as written.
- **Negative results and untested parts are reported.**
- Kept apart from the running H11 one-week trial (`ccx trial`, until 2026-10-31): every `ccx run` here has
  `--no-ab`, so the trial never samples it; labels are `eval-7c:*`, and the trial only counts runs carrying its id.

## 1. A/B design

Script: `scripts/eval/seven_ab.py` (tasks in `scripts/eval/tasks.py`).

### 1.1 Tasks

| Set | Tasks | Notes |
|---|---|---|
| Core (A/B/C) | slugify, duration, intervals, cli-json (small, used before); inventory, csvstats, lru (medium, new) | medium tasks have 3+ requirements; inventory touches two files |
| Memory (D) | mem-errors, mem-money, mem-log | the brief **leaves out** one project convention (error type, money in integer cents, a log line per call); the hidden test checks it |

Each task is a scratch git repo with start code, a visible test and a hidden acceptance test. `tests/test_eval_tasks.py`
confirms on an untouched copy that the hidden test **fails**, and that the reference solution passes (all 15 tasks).

### 1.2 Four comparisons (B − A, i.e. treatment − control)

| Exp | Control A | Treatment B | Held fixed | Measured | Core |
|---|---|---|---|---|---|
| (a) deleg | the lead does it itself | the lead hands it to Codex via `ccx run` | lead = fresh headless Claude sonnet (medium, slim start); sub-agent gpt-6-luna low; `--review off` | total tokens (lead read + output + sub-agent), total spend, wall time, first-time pass rate; lead requests × real context (352k) extrapolated | 5 |
| (b) route | one fixed model: Claude sonnet medium, no escalation | `--to auto --minutes M`: task-routing picks vendor, model, effort; may escalate | same `--check`; no lead, `ccx run` directly | pass rate, spend, time, what was picked | 4 |
| (c) review | `--review off` | `--review on`: another vendor's cheap model reads the diff; issues go back for one fix round | sub-agent gpt-6-luna low, no escalation | pass rate (primary), spend, time, review verdicts | 4 |
| (d) memory | the repo without the convention | the convention in the project memory (`ccx ctx add` → `.ccx/context.md`, pointed to in the brief) | sub-agent gpt-6-luna low, no escalation | pass rate (primary), spend | 3 |

(d)'s effect is partly built in (without the note the convention can't be known). What it really tests is whether
**memory reaches a real sub-agent and the sub-agent follows it**. Not in this experiment: H5's "suggest → user
agrees → written to shared memory" (a functional check once the critical-path session's H7 is confirmed), and the
shared hub memory in the Codex/Claude start hooks (it would write to the user's real hub; not this round).

### 1.3 Assignment and repetition

- **3 rounds** per task per experiment. Within a round the task order is random and each task's arm order is random;
  seed `--seed 7`, reproducible (`seven_ab.py plan` prints the whole order). Rounds are the outer loop, so a batch
  cut short still has every experiment's first rounds.
- **Pairs**: same experiment, round and task. Every arm gets a fresh scratch repo and a fresh session.
- Each unit is appended to `.ccx/eval/seven/results.jsonl` as soon as it ends (git-ignored: local paths); running
  again skips finished units. The hidden-test verdict is recorded with `ccx verify`.

### 1.4 Experimental unit and statistics

- **The independent unit of the main analysis is the task** (n = 7 core, n = 3 memory): the paired differences of a
  task's 3 rounds are averaged, then a sign test and a bootstrap 95% interval run over tasks. A task's 3 rounds are
  repeated measures, not independent samples.
- Pair level (n = 21 / 9): median difference, interval and sign test, descriptive only.
- Pass rates: Wilson 95% interval per arm; exact McNemar on the discordant pairs.
- Effect sizes: median and mean paired difference, median B/A ratio; difference in pass rate.
- Multiple comparisons: 4 primary tests ((a) total spend, (b) total spend, (c) pass rate, (d) pass rate), Holm
  corrected; everything else is descriptive.
- Small tasks, small samples (with n = 7 the smallest sign-test p is 0.016): not significant is not "no
  difference"; significant holds for this kind of task and these models, not for long real conversations.

## 2. Functional checks (cores 1, 2, 7)

| Core | Check | Raw evidence |
|---|---|---|
| 1 lead and sub-agent both ways | Claude lead → Codex sub-agent ((a)'s delegate arm); Codex lead (`codex exec`) → `ccx run --to claude`; hidden test passes | ledger `caller`/`to`, hidden test |
| 1 (round 2) | Gemini, DeepSeek as sub-agents once their adapters are merged | same |
| 2 two models talk directly | `ccx discuss` (after PR #23 merges): at least two vendors speak, answer each other's points, reach a conclusion | the transcript |
| 7 nothing lost | a sub-agent killed halfway; `ccx task resume` picks it up and finishes | task file, both runs, hidden test |
| 7 in control: undo | a write run, then `ccx undo --apply`: files byte-identical to before | hashes before/after |
| 7 in control: spend cap | a tiny `--budget` with a parallel request: the sub-agent's own sub-agents are stopped once they spend, `kind = over_budget` | run record |
| 7 no mess | across all A/B units, how often ccx said "passed" but the hidden test failed | results.jsonl |

## 3. Decision rules (fixed in advance)

| Verdict | Condition |
|---|---|
| **works** | primary test Holm-corrected p < 0.05, in the favourable direction; pass rate not lower (no more discordant pairs against B than for it) |
| **partly** | favourable direction but the interval includes 0; or only for some tasks, one kind of lead, or after extrapolation; or a functional check partly passes |
| **doesn't** | unfavourable direction with the interval excluding 0, or a functional check fails |
| **not tested yet** | no data (dependency not merged, quota, ...), with the reason |

Core 5 ("saves") is read from (a), both total spend and total tokens; if small leads don't save and only the
extrapolation to a real context does, it is "partly". Core 6 ("gets more accurate with use") needs data over time
(more verdicts → better routing); there is no controlled design this round, so only the ledger's verdict counts and
the overturn rate of automatic verdicts are reported ("not tested yet" or "partly").

## 4. Spend

At most $10 in total (API-equivalent dollars: Claude's own `total_cost_usd` from `claude -p`, sub-agents' AE$ from
the ledger), summed before each unit; the script stops at `--budget`. Round 1 gets $6, round 2 (Gemini/DeepSeek) the
rest; DeepSeek at most $1 a day. Codex quota is tight this week: gpt-6-luna low only.

## 5. Reproduce

```
python scripts/eval/seven_ab.py plan --rounds 3 --seed 7
python scripts/eval/seven_ab.py run --rounds 3 --seed 7 --tag r1 --budget 6
python scripts/eval/seven_ab.py summary --tag r1
```
