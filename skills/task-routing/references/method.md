# Method: how task-routing quantifies "which model for this task"

English · [中文](method.zh.md)

Short version: **difficulty vs ability → success probability → cost per success → cheapest option that is likely enough to succeed**, then learn from every outcome.

## 1. Task difficulty b (0–10)

The lead agent scores five observable items (rubric in SKILL.md). The points add up linearly:

| item | points |
|---|---|
| files touched | 1 → 0 · 2–3 → 1 · 4–8 → 2 · 9+ → 3 |
| coupling | one module 0 · cross-module 1 · system-wide 2 |
| clarity | spec + test 0 · clear goal 1 · unknown cause 2 |
| risk | low 0 · user-visible 1 · critical 2 |
| novelty | existing pattern 0 · new design 1 |

The items follow the profile dimensions used by explainable agentic routers (required skill/complexity,
quality sensitivity — Topaz, Okamoto et al. 2026) and the "estimate scope first" step of E3 (Yin & Feng 2026).
The equal weights are a starting assumption. Once enough outcomes are recorded, refit them with a
logistic regression of outcome on item scores.

### 1b. The standard unit: human minutes (2026-10-24)

Rubric points are our own scale. A shared one is **how long a skilled engineer would need**, the unit METR uses to
measure AI agents (the task length a model completes with 50% chance). `--minutes N` gives it; b = log2(N), so
1 minute is 0, 8 minutes 3, an hour about 6 and 17 hours 10, and a rung's 50% task length is 2^theta minutes (shown
as `h50_minutes`). With the rubric too, b = 0.6 · minutes-b + 0.4 · rubric-b. That b = log2(minutes) matches our old
scale is an assumption until outcomes say otherwise; METR's own horizons (in the Epoch data) stop at April 2026, so
for current models h50 is converted from the merged ability, not measured. task-split already sizes pieces with the
same kind of curve.

Two things keep it honest:
- **Objective signals** (`ccx/signals.py`): the files the brief names that exist, their lines, how many top-level
  folders they span, whether tests mention them. They fill rubric items the lead left out (files, coupling) and
  are shown next to the lead's, so anyone rerunning gets the same numbers.
- **Lead bias**: after each recorded outcome the lead's offset moves by 0.1 · (predicted − actual) — a lead whose
  tasks fail more than predicted is underestimating, and its b goes up. The log also keeps estimate vs real time
  and the rubric items; `task_routing.py refit` (with ≥ 30 outcomes) fits a logistic regression and suggests item
  weights. Advice only: the weights in use change only when you decide.

## 2. Success probability (Item Response Theory, 2PL)

```
P(success | rung r, task b) = 1 / (1 + exp(-a · (θ_r − b)))
```

- θ_r = ability of a rung (agent × model × effort), on the same 0–10 scale. The priors are dated guesses in `data/priors.toml`.
- a = slope (1.2). θ − b = 0 gives 50%; +1.2 gives about 81%; +2 gives about 92%.
- IRT-Router (Song et al., ACL 2025) uses the same idea, with learned multidimensional abilities and difficulties
  on 20 LLMs. We use the 1-D version because one person's log is too small to fit more parameters.

## 3. Cost of one attempt (API-equivalent USD)

```
turns   = 4 + 1.5·b
input   = turns·startup + ctx_tokens + turns·3000      (cached share 85%)
output  = 1500·(1 + b/2)·effort_mult                  (low 0.5, medium 1, high 1.9, xhigh 4, max 13)
USD     = (fresh·P_in + cached·P_cached + output·P_out) / 1e6
```

- Claude startup ≈ 48k tokens per turn, measured once; Codex startup is a placeholder guess.
- A headless `claude -p` start writes those ~48.7k tokens to the **1-hour** prompt cache, which Anthropic bills at
  2× input (5-minute entries: 1.25×). On a tiny haiku run this was ~90% of the bill (measured 2026-10-22). Repeat
  delegations within the hour read the cache at 0.1×, so batching delegations is cheaper. ccx's measured
  per-attempt cost (AE$, including this premium) feeds the per-rung cost factor below, so the estimate converges
  on the real number.
- The 84% cache-read median comes from Anthropic's agent measurements.
- The effort multipliers come from a third-party Sonnet 5.5 benchmark: medium $0.59, high $1.12, max $7.67 per task.
- All of these are replaced by measured averages once ccx has logged runs.
- Compare in USD, never in raw tokens: tokenizers differ, and cached tokens are 10–40× cheaper.

## 4. Choosing: cascade vs single shot

When a check can tell success from failure (`verifiable`), start cheap and escalate up the same agent's ladder
(at most 2 steps) **in the same session**:

```
E[cost | start at r] = C_r + (1 − P_r)·C_{r+1} + (1 − P_r)(1 − P_{r+1})·C_{r+2}
P(chain succeeds)    = 1 − Π (1 − P_i)
cost per success     = E[cost] / P(chain succeeds)
pick = argmin cost-per-success  subject to  P(chain succeeds) ≥ τ
```

- Starting low beats starting high iff C_low < p_low · C_high (cascade rule; FrugalGPT, Chen et al. 2023).
  Example: luna costs about 1/20 of sol, so starting with luna pays off whenever luna succeeds more than ~5% of the time.
- Anthropic's guidance reports that "low effort, re-run failures at high" cost about 40% less at the same pass rate.
  That holds only when failure is detectable, which is why `--not-verifiable` turns the cascade off.
- Not verifiable → single shot: cheapest rung with P ≥ τ.

τ comes from the tradeoff knob: save 0.70 · balanced 0.80 · fast 0.90 (no cascade on fast), or a number
k ∈ [0, 1] with τ = 0.70 + 0.20·k and the cascade on while k < 0.75 (balanced = 0.5).

Guards:
- b ≤ 1 → do it yourself.
- Best chain P < 0.5 → split the task (E3: "minimum-sufficient execution"; expand only when verification fails).

## 5. Self vs delegate

```
C_self  ≈ own work + ctx_tokens · (P_write + T_rem · P_read)      # what you read stays in your context every later turn
C_deleg ≈ brief·P_out + E[sub cost] + readback · (P_write + T_rem · P_read)
delegate iff C_deleg < 0.85·C_self and P(chain) ≥ 0.6
```

## 6. Learning (online IRT / Elo update)

After each verified outcome y ∈ {0, 1}:

```
θ_r ← θ_r + η · (y − P)      η = 0.25
```

Offsets decay ×0.95 per week toward the prior, because models and prices change. This is the Elo/Rasch online update.
It needs no training set and behaves sensibly with a handful of outcomes. Bandit routers (MetaLLM, LLM Bandit) and
trained routers (RouteLLM) need hundreds to thousands of labelled runs. RouterBench found that trained routers often
don't beat a simple cost-quality mix.

## 7. Why not call an existing router library directly

- RouteLLM (lm-sys) and IRT-Router ship routers trained on chat/QA data (Chatbot Arena, MMLU, GSM8K, …).
- They need embedding models or API keys.
- They don't know the GPT-6 / Claude 5.5 families or agentic coding tasks.
- Their published gains were measured on single-call benchmarks: RouteLLM reports 35–85% savings vs GPT-4-only.

We reuse their **methods** (IRT, cascades, cost per success, Pareto view), not their trained weights. If a router trained
on agentic coding outcomes appears, it can replace step 2 behind the same interface.

## 8. Calibrating a new rung: DeepSeek (2026-10-24)

A new model enters with a guessed theta. Before routing relies on it, run a handful of real, checkable tasks and
set its theta from them; after that the online update (section 6) takes over.

deepseek-flash (through Claude Code with `--bare`, effort low): 10 tasks in a throw-away clone of this repository,
each with an automatic check written before the run (it failed on the untouched clone): a docstring, a new test, a
seeded bug behind a failing test (b 2), a new function to a spec with a test (b 3), type hints, a read-only question,
extracting a constant, a CHANGELOG line, a seeded accounting bug across modules (b 5) and a new CLI flag with a test
(b 4). Result: 10/10 passed on the first attempt; total $0.054 at peak price (the day was off-peak: about half was
billed); 11–202 s each. With prior N(3.5, 1.5²) the posterior mode is 5.3 (80%: 4.3–6.8); priors of 2.5 / 4.5 give
5.0 / 5.75. The priors first used **4.5**, the low end, because the tasks were small and chosen by us. Since the
public benchmarks arrived (section 10) the hand-set value is back to a guess (3.5) and the ten results are recorded
as ordinary outcomes, so they correct the benchmark-based ability instead of replacing it (offset +0.83). v4-pro was
never needed (no failure to escalate). Ten successes say little about where it starts to fail.

## 9. Public benchmark data (weekly)

`task_routing.py refresh` (or `ccx bench refresh`) downloads three open sources into `benchmarks.json` next to the
learned state; with ccx it runs by itself at session start, in a detached process, when the copy is a week old
(a source that failed is retried after 6 hours; offline, the old copy stays). Nothing is redistributed.

| Source | What | Licence |
|---|---|---|
| Epoch AI, epoch.ai/benchmarks | Epoch Capabilities Index (with interval), GPQA Diamond, SWE-bench Verified, SimpleQA Verified; external: FrontierCode and Terminal-Bench (by harness and effort), METR time horizons, WebDev Arena, HLE | CC BY 4.0 for Epoch's runs and ECI; `_external` files keep their own licences |
| LMArena, huggingface.co/datasets/lmarena-ai/leaderboard-dataset | human ratings: text, factuality, agent task outcome, tool hallucination, bash reliability, search factuality | CC BY 4.0 |
| models.dev | prices per million tokens, long-prompt tiers | MIT |

Credit them whenever you show their numbers (`task_routing.py sources` prints the lines). Model names stay as each
source writes them; section 10 (the merge) maps them to rungs. Artificial Analysis is not among the defaults: its
terms forbid scraping and limit the free API to the user's own internal use, so it can only be added locally with
the user's own key.

**Your own sources.** Any `<state dir>/bench-sources/*.py` with `NAME`, `CREDIT`, `fetch(get)` returning score rows,
optionally `available()` and `KIND_WEIGHTS {kind: {benchmark: weight}}`, is fetched with the others and merged the
same way. It lives on your machine only — the place for data whose terms allow only your own use (for example
Artificial Analysis with your key). A source that isn't set up (`available()` false) is skipped, not counted as a
failure.

## 10. Merging the benchmarks into abilities

`scripts/merge.py`, used by `route`, `three_way` and `record` whenever the cache exists:

1. **Match rows to rungs.** Each source's model name is reduced to letters and digits after splitting off the
   effort ("claude-haiku-5-5_max", "Claude Haiku 5.5 (High)" → `claudehaiku55`, max / high). `[aliases]` in the
   priors maps every rung's model to these names, with weight 1 for the exact version and less for an older one.
   A row without an effort is taken as the model's best setting (max).
2. **One estimate per benchmark.** Fit a straight line score → theta on the anchors: Claude and Codex rungs of the
   exact version, their hand-set theta moved to the row's effort with an effort-shift table (max 0, xhigh −0.3,
   high −0.8, medium −1.5, low −2.8 — hand-set round numbers, to be refitted). At least 4 anchors and a rising line,
   otherwise the benchmark is skipped. Every matched rung reads its theta off the line, moved back to its own effort.
3. **Combine.** Weight = relevance of the benchmark for the kind of work ÷ squared fit error; a different version or
   effort halves it; no benchmark above half the total. Kinds: `code` (FrontierCode, SWE-bench Verified,
   Terminal-Bench, LMArena agent outcome and bash reliability, ECI…), `read` (ECI, GPQA, HLE…), `research`
   (SimpleQA, LMArena factuality…), `write` (LMArena text, ECI…). The kind comes from `--kind`, else read-only runs
   count as `read` and the rest as `code`.
4. **Blend with the hand-set prior** (its sd 1.5) by inverse variance; learned offsets from recorded outcomes apply
   on top, learned against the `code` blend.

First run (2026-10-24, code): GPT-6 Astra max 9.2 → 7.9, Sol medium 5.5 → 6.3, Opus max 9.0 → 8.5, DeepSeek flash
low 4.5 → 2.5 before the local outcomes; Haiku and luna at low effort stay near 2.2–2.8.

## 11. Choosing by total cost (2026-10-24)

Money and quota are not the same currency, and time and risk matter too. Each option (a start rung with its
escalation chain, the lead itself, the lead's built-in sub-agent) gets one figure in dollars:

- **money** — pay-per-token agents (`[cash]`, e.g. DeepSeek): their expected API cost;
- **quota** — subscription agents: expected API-equivalent cost × λ, the quota's shadow price. λ is 0.3 while
  the window has room (quota is worth keeping for the lead and hard work), rises linearly to 1.0 between 60% and
  100% used, and is 2.0 beyond. The lead's own quota pays for doing it yourself, for its built-in sub-agents and
  for the brief/read-back/review overhead;
- **time** — expected minutes (measured per rung once recorded, else by effort and difficulty) × the value of a
  minute: $0.005 (save), $0.02 (balanced), $0.10 (fast);
- **risk** — chance the whole chain still fails × the cost of a wrong result: $0.5 (risk low), $3 (visible),
  $20 (critical). Doing it yourself counts one self-check and redo.

**Used means projected (ccx, `ccx quota`).** The share λ is priced from is not the share used now but the share
the window will have used at its reset: the last 48 hours' rate, within the current window only (a later reset
time or a drop in use starts a new window — a plan change does both), projected to the reset; with under six hours
of readings it is too early and today's share stands. Every window counts (Claude 5 hours and 7 days; Codex's weekly
and, on plans that have it, 5 hours) and the tightest one decides. Codex's readings come from its own logs at every
call; Claude's only from a Claude run's events, so ccx keeps them and, when the newest is over an hour old and
Claude is a candidate, sends one tiny request to read them.

The cheapest option whose chain reaches the success target wins (staying with the lead inside a 15% margin). A
pay-per-token agent is no longer held back by a quota threshold: its money competes with the quota's shadow price;
the daily cap still applies. All the numbers are in `[total_cost]`-style defaults in the script and can be set in
the priors.

## Limits (say these out loud)

- Priors are guesses until outcomes are recorded. The first weeks are uncalibrated.
- The rubric is a coarse 1-D summary; two tasks with equal b can differ a lot.
- Cost estimates are ±2× until replaced by measured averages.
- Success means "the check passed", which is only as good as the check.

## References

- Song et al., *IRT-Router: Effective and Interpretable Multi-LLM Routing via Item Response Theory*, ACL 2025 — https://aclanthology.org/2025.acl-long.761 · code https://github.com/Mercidaiha/IRT-Router
- Ong et al., *RouteLLM: Learning to Route LLMs with Preference Data*, ICLR 2025 — https://arxiv.org/pdf/2406.18665
- Chen, Zaharia, Zou, *FrugalGPT* — https://arxiv.org/pdf/2305.05176
- Hu et al., *RouterBench* — https://www.alphaxiv.org/abs/2403.12031
- Kapoor, Narayanan et al., *AI Agents That Matter* — https://agents.cs.princeton.edu/
- Yin & Feng, *Do AI Agents Know When a Task Is Simple?* (E3), 2026 — https://arxiv.org/abs/2607.13034
- Okamoto, Erol, Riedl, *Explainable Model Routing for Agentic Workflows* (Topaz), 2026 — https://arxiv.org/html/2604.03527v1
- Anthropic, *Optimizing for cost and intelligence* — https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- Prices: https://platform.claude.com/docs/en/about-claude/pricing · https://developers.openai.com/api/docs/models (read 2026-10-23)
