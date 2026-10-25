- DeepSeek as the fourth vendor: an adapter for DeepSeek's own agent, DeepSeek Harness (`--to dsh`; headless
  profile, `--json` events, model in a `--patch` overlay, sandbox in `DSH_PERMISSION_MODE`, session-log upload and
  telemetry turned off; checked against dsh-v0.2.1-rc.3 source, not run for real), and DeepSeek through Codex
  (`--provider deepseek-codex`, a `-c model_providers.deepseek` override with `env_key`; run for real). Provider runs
  on Codex disable `apps` and `plugins` (219k vs 10k input tokens per request, measured) and Codex's own sub-agents.
- Smaller APIs through Claude Code as providers, each with `daily_usd = 1.0` and taking part only when its key is
  set: `kimi`, `glm`, `qwen` (base URL from `DASHSCOPE_ANTHROPIC_BASE_URL`), `openrouter`. A provider can carry its
  own `prices`; a pay-per-token model with no price is refused, since its daily cap could not hold.
- Pay-per-token agents are never a quota fallback or a reviewer unless pinned; `ccx agents` shows `ready`,
  `needs_env` and `daily_usd`; `ccx report` counts every DeepSeek route as one stream and other providers as one more.
