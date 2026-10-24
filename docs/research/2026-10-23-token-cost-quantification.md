# Research: quantifying token savings (2026-10-23)

[中文](2026-10-23-token-cost-quantification.zh.md)

These notes come from one research pass over papers, official pricing pages and engineering blogs. The full source list is at the end.

## Conclusions

1. **Use one unit: API-equivalent USD (AE$).** Never compare raw token counts.
   - Cache reads cost 1–10% of fresh input.
   - Claude's tokenizer produces about 30% more tokens than OpenAI's for the same text.
   - Codex credits equal AE$ × 25. This is derived from the current GPT-6 price table.
   - Claude subscription weighting is not published, so AE$ is only a proxy there. Calibrate it with `/usage` snapshots.
2. **The headline metric is cost per success (CPS)**, measured against a baseline where the lead does everything itself.
   - Savings = 1 − CPS_ccx / CPS_baseline. Always report it with the success-rate delta and a 95% CI.
   - Secondary metrics: cache-read ratio (≥ 80%), escalation rate, overhead ratio, strong-model cost share, time per success and quota share.
3. **Self vs delegate can be computed.**
   - Delegation saves mostly through context the lead never carries. Tokens the lead reads are re-read on every later turn.
   - It costs startup overhead, the brief, the readback, and rework when a sub-task fails. Claude Code headless startup measured about 48k tokens per turn, mostly cache reads.
4. **Cascade rule**: start cheap and escalate on verified failure. This is better only if C_low < p_low · C_high, and only when failure is detectable. Anthropic reports that low effort with re-runs at high effort costs about 40% less at the same pass rate.
5. **Baselines, from most to least rigorous**:
   - randomized A/B, where the lead does 10–20% of delegable tasks itself;
   - a paired replay suite;
   - proxy repricing.

   Always label which method produced a number.
6. **Adaptive routing on little data**:
   - Keep Beta success counts per (task class, rung).
   - Pick the cheapest rung that is confidently good enough.
   - Explore one rung cheaper about 10% of the time.
   - Decay old counts ×0.95 per week.
   - Avoid trained routers until there are hundreds of runs; RouterBench found they often fail to beat a simple mix.

## Formulas

Claude (`input_tokens` excludes cache):

```
AE$ = (in·P_in + w5m·1.25·P_in + w1h·2·P_in + cache_read·k·P_in + out·P_out) / 1e6
```

k = 0.1 by default, 0.05 for Opus/Sonnet 5.5, and 0.025 for Fable 5.1.

Codex (cached input is a subset of `input_tokens`):

```
AE$ = ((in − cached)·P_in + cached·P_cached + out·P_out) / 1e6
```

Self vs delegate:

```
C_self  = own work + ctx_tokens · (P_write + T_rem · P_read)
C_deleg = brief + startup + sub work + readback · (P_write + T_rem · P_read) + (1 − p̂) · rework
delegate iff C_deleg < 0.85 · C_self
```

## Prices (USD per 1M tokens, read 2026-10-23; the official pages win)

| model | input | cache read | output |
|---|---|---|---|
| Claude Opus 5.5 | 4 | 0.20 | 20 |
| Claude Sonnet 5.5 | 2 | 0.10 | 10 |
| Claude Haiku 5.5 (≤100k) | 0.10 | 0.01 | 0.50 |
| gpt-6-astra | 10 | 1.00 | 50 |
| gpt-6.1-sol | 2 | 0.10 | 10 |
| gpt-6-luna | 0.10 | 0.01 | 0.50 |

## Caveats

- Prices and model lineups change monthly. Pin the price-table version in every log row so old costs can be recomputed.
- The literature numbers (FrugalGPT up to 98%, RouteLLM >2×) come from single-call QA benchmarks. Expect much smaller gains for multi-turn coding agents, and validate on your own tasks.
- Claude subscription weighting is undisclosed.

## Sources

- RouteLLM — https://arxiv.org/pdf/2406.18665
- FrugalGPT — https://arxiv.org/pdf/2305.05176
- RouterBench — https://www.alphaxiv.org/abs/2403.12031
- AI Agents That Matter — https://agents.cs.princeton.edu/
- Anthropic, optimizing for cost and intelligence — https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- Anthropic pricing — https://platform.claude.com/docs/en/about-claude/pricing
- OpenAI models & pricing — https://developers.openai.com/api/docs/models
- Codex rate card — https://help.openai.com/en/articles/20001106-codex-rate-card
- Claude Code cost tracking — https://code.claude.com/docs/en/agent-sdk/cost-tracking
- Claude Code sub-agents — https://code.claude.com/docs/en/sub-agents
- Claude Code with Pro/Max — https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
