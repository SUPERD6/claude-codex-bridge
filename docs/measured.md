# Measured

English · [中文](measured.zh.md) · back to the [README](../README.md) · all [research reports](research/README.md)

## Behind the README's four numbers

| Pillar | Number | Source | Limits |
|---|---|---|---|
| Save money | 63 % less spend in all; 0 reworks vs 29 | [shared-context A/B](research/2026-10-25-shared-context-ab.md) (2026-10-25, Codex luna low + DeepSeek flash low, 42 pairs) | tasks built to need the lead's context: the feature's best case by design |
| More accurate | first try right 36/36 vs 7/36 (McNemar p ≈ 4e-9) | same A/B | same; on the neutral task both arms were 6/6 |
| Split the work | the lead made one request fewer on every task, 21/21 | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.2 | total spend about even (ratio 1.02), 3.3× tokens, ~23 s slower; a short headless lead |
| Share | project note followed: 9/9 right vs 0/9 (McNemar p = 0.004, Holm 0.016) | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.1 | 3 tasks × 3; hub memory through start hooks not tested |

## Round 5: large real tasks (2026-10-26/27, dev set)

Ten real changes from this repository × 2, a sonnet-medium lead, hidden tests; details and every arm in the
[round-5 report](research/2026-10-26-r5.md). **Dev set, signal only**: the tasks were also used while fixing ccx,
and this run came before the clean-environment checks ([r5 plan §8](research/2026-10-26-r5-plan.md)). It does not
change the four numbers above.

| Run | Arm | Right | Cost per success | Wall, median |
|---|---|---|---|---|
| r5h | ccx2 (ccx as the agent-delegate skill teaches it) | 19/20 | $0.135 | 236 s |

For comparison, the first run in the report: the lead doing it itself 19/20, $0.211, 94 s; the built-in sub-agent
19/20, $0.155, 278 s. The report's §7 table stops at r5f; the r5h row uses its definitions (total spend of the 20
units / units right; plain median of the 20 walls) on the same results file, and r5h is covered by the
[harness audit](research/2026-10-28-harness-audit.md).

## Measured (2026-10-24, ccx 0.4.0)

All from real runs on a real machine; method, raw tables and limits in the
[measurement report](research/2026-10-24-h11-e8-f9-measurements.md) and the
[seven-cores A/B](research/2026-10-24-seven-cores-ab.md). **The unfavourable results are here too.** The last column says whether a number is
measured or extrapolated.

| Question | Result | How sure |
|---|---|---|
| Does handing small tasks to Codex save anything? ([seven-cores A/B](research/2026-10-24-seven-cores-ab.md) round 1: 7 Python tasks (4 small, 3 medium) × 3, sonnet lead does it itself vs delegates to Codex luna low, paired) | **Total spend about even: ratio 1.02** (median $0.0344 → $0.0351; sign test over tasks p = 1). **Total tokens 3.3×** (35.6k → 119k), **about 23 s slower** (10.9 → 33.7 s). The lead made **one request fewer on every task** (3 → 2, 21/21). Right 21/21 done by the lead, 18/21 delegated (the cheap sub-agent got one medium task wrong 3/3). An earlier batch (PR #6): a haiku lead that reran the tests after delegating saved no request and paid more. | **Measured**; 5–15-minute tasks, a short headless lead |
| And with a real, long-conversation lead? | One request fewer ≈ 352k tokens not re-read (the median below) ≈ **about $0.07 saved per small task at Opus cache-read price, about 23 s more waiting**, possibly wrong; a lead that doesn't save the request pays about $0.003 more. | **Extrapolated, not measured** ([A/B](research/2026-10-24-seven-cores-ab.md) §2.2) |
| Where does the money actually go? (real sessions on this machine, 7 days) | The Claude lead re-reads a median **352k tokens, $0.11 per request**, 99% cache reads; all ccx sub-tasks in the same week: $0.42. So the lead's own re-reading is what to cut. | **Measured** (a reading of session files, 2026-10-17–24) |
| Do Codex's own sub-agents get used? | On gpt-6-luna low, **0 of 5 runs started one**, even when asked explicitly; on vs. off differ within noise. Higher models not tested. | Sure for luna low only |
| From a handoff alone, can the next agent say where things stand? | 3/3 in controlled runs (including one killed midway); a real long session failed at first (the plan was read stale), right after the fix. | One real session |
| Slim start of a Claude sub-agent | Fixed context per request 46k → **13.6k** tokens | Single run |
| Accounting vs. Codex's own weekly quota | **$2.8–4.4** API-equivalent per 1%, stable across 4 windows | 4 windows |
| Tests | 268, on Linux, Windows and macOS × Python 3.11–3.13 | Logic only, not real CLIs |

## How savings are measured

- **AE$ (API-equivalent USD):** tokens × list price, per bucket (fresh input, cache write, cache read, output).
  Subscriptions don't bill per token, so AE$ is the common yardstick. Against one real run it was 1.5% from
  Claude's own reported cost.
- **Estimated saving per delegated run:** the same tokens at the lead model's price, minus what the sub-agent cost,
  minus the brief/review overhead. Reported with a bootstrap 95% CI.
- **Measured A/B:** about 10% of tasks that would have been delegated are randomly handed back to the lead
  (`defaults.ab_self_rate`; 0 turns it off). Costs are compared at the same difficulty, which tests the estimate
  above.
- **The lead's own usage** is read from each tool's session logs (Claude `~/.claude/projects`, Codex
  `~/.codex/sessions`). Sub-agent sessions are excluded so nothing is counted twice.

## Tests

```bash
python -m pytest -q tests        # or: python -m unittest discover -s tests
```

The tests drive fake codex/claude/gemini CLIs (`tests/fakes/`). They cover:
- argv and stream parsing;
- escalation, resume, quota fallback and timeouts;
- the depth guard and incremental memory;
- sync idempotence and backups;
- the learning loop and the dashboard.

GitHub Actions runs them on Linux/Windows/macOS × Python 3.11–3.13. **The tests prove the logic, not that the real
CLIs work on your machine.** Run `ccx selftest` there; the acceptance list is in
[docs/DESIGN.md](DESIGN.md#acceptance).

## External facts checked (2026-10-22/24)

- **codex-cli 0.164.0** `exec --help`: `--json`, `-m`, `-c`, `--output-schema`, `-o`, `--ignore-user-config`, `--ephemeral`, `exec resume <id>`. A lean start (`--ignore-user-config`) must keep the user's `windows.sandbox`, or read-only rejects every command on Windows.
  `resume` takes no `-s`, so the sandbox is set with `-c sandbox_mode=…`.
- **Claude Code 2.1.309** `--help`: `-p --output-format json|stream-json` (stream-json requires `--verbose`),
  `--model`, `--effort low..max`, `--json-schema`, `--resume`, `--strict-mcp-config`. Measured:
  - the first event carries session_id;
  - the final result event carries `structured_output`, `usage`, `total_cost_usd`;
  - `--resume` reports per-call usage;
  - a headless start with default flags is ~46k tokens, written to the 1-hour cache; with ccx's slim flags ~20k, and a repeat start (any project, within the hour) writes only ~0.65–2k.
- **OpenAI GPT-6 docs:** `gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-luna`; 6.1-sol efforts low/medium/high/xhigh/max.
- **Codex hooks docs:** `[[hooks.SessionStart]]`; stdout is injected as developer context; new hooks must be trusted
  in `/hooks`.
- **Gemini CLI 0.65.0** `--help` and bundled source:
  - `-p` runs headless, appended after stdin;
  - `-o stream-json` emits init / message / tool_use / tool_result / error / result events;
  - also `--approval-mode plan|auto_edit`, `--session-id`, `--resume <uuid>`;
  - model aliases `flash-lite / flash / pro`.
- **DeepSeek docs:** Claude Code uses `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` and the key; ccx passes
  it as `ANTHROPIC_API_KEY` with `--bare`, so the caller's own Claude login never reaches DeepSeek (2026-10-24).
  Peak prices per 1M tokens (input / cache hit / output), off-peak half:
  - deepseek-flash $0.30 / $0.006 / $1.20;
  - deepseek-v4-pro $1.32 / $0.044 / $3.96.
- **DeepSeek Harness** (`dsh`, github.com/deepseek-ai/deepseek-harness, tag dsh-v0.2.1-rc.3, source read 2026-10-24,
  not installed here): `dsh --profile headless "task"` (or `-` for stdin) runs one task; `--json` prints
  session / status (step_end usage, turn_end reason) / text / tool_call / tool_result / final / error events;
  `--session-id <id>` continues a session. Token counts are disjoint (input excludes cache reads). No model or
  permission flag in rc.3: the model goes in a `--patch` overlay (`agent-default-model` row), the sandbox in
  `DSH_PERMISSION_MODE`. The base profile uploads session logs with DeepSeek requests by default.
- **Codex model providers** (Codex config reference, read 2026-10-24): `model_provider` + `[model_providers.<id>]`
  with `base_url`, `env_key`, `wire_api` (only `"responses"`); `openai`, `ollama`, `lmstudio` are reserved. DeepSeek's
  Codex page uses `base_url = "https://api.deepseek.com/"`, `wire_api = "responses"`. Measured with codex-cli 0.164:
  through a custom provider, `apps` and `plugins` send every connector's tool list (219k input tokens for "reply OK",
  10k with `--disable apps --disable plugins`), so ccx disables both, and Codex's own sub-agents, for provider runs.
  Codex warns "Model metadata for `deepseek-flash` not found" and uses fallback metadata; the runs still finish.
- **Smaller APIs** (Anthropic-compatible endpoints for Claude Code, read 2026-10-24; none run for real):
  - Kimi: `https://api.moonshot.ai/anthropic`, `kimi-k3.1-pro`; prices not readable (the table is rendered by script),
    so ccx refuses it until you add a price;
  - GLM (Z.ai): `https://api.z.ai/api/anthropic`; GLM-5.3-Flash $0.15 / $0.03 / $0.50, GLM-5.3 $1.4 / $0.26 / $4.4;
  - Qwen (Alibaba Model Studio, pay as you go): `https://{WorkspaceId}.<region>.maas.aliyuncs.com/apps/anthropic`, so
    ccx reads it from `DASHSCOPE_ANTHROPIC_BASE_URL`; qwen3.7-plus $0.4 / $1.6, qwen3.7-max $2.5 / $7.5 (Singapore,
    no cache price given: counted at the input price);
  - OpenRouter: `https://openrouter.ai/api`; no default model, give `--model` and its price.
  - Their pages set the key as `ANTHROPIC_AUTH_TOKEN`; ccx runs Claude Code with `--bare`, which reads only
    `ANTHROPIC_API_KEY` (sent as `x-api-key`). DeepSeek accepts that; for the others it is not yet confirmed.
- **Gemini pricing** (ai.google.dev/pricing), per 1M tokens (input / cached / output):
  - 3.5-flash-lite $0.30 / $0.03 / $2.50;
  - 3.8-flash $0.75 / $0.075 / $3.75 (until 2026-12-31);
  - 3.1-pro-preview $2.00 / $0.20 / $12.00.
