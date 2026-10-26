- Evaluations start from a clean room: `scripts/eval/preflight.py` checks the machine before `r5.py run` (another eval
  or pytest running, modified tracked files, a dedicated Codex home, the work dir, a canary lead) and refuses to start
  on any problem unless `--force-unclean`, which every row records. Each unit gets an allow-listed environment, its
  own TMP / git identity / CCX_CONFIG / DSH_HOME, Claude without user settings, hooks, CLAUDE.md or auto-memory (deny
  rules for the real homes), Codex in a dedicated CODEX_HOME; its processes run in a Job Object and leftovers are
  killed and logged. Rows carry `fingerprint`, `audit`, `leftovers` and `env_clean`.
- New opt-in knobs for sub-agents, unchanged by default: `CCX_CLAUDE_SETTING_SOURCES` (`--setting-sources`),
  `CCX_CLAUDE_SETTINGS` (a JSON file merged into `--settings`), `CCX_CODEX_ISOLATE=1` (`--ignore-user-config
  --ignore-rules`, Codex memories off, at every effort).
