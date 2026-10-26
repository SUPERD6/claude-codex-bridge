- Evaluations start from a clean room: `scripts/eval/preflight.py` checks the machine before `r5.py run` (another eval,
  pytest, `ccx run`, `codex exec` or `claude -p` running, modified code, a dedicated Codex home, the work dir and the
  folders above it, a canary lead that must see only the project's instructions and must fail to read a denied
  folder) and refuses to start on any problem unless `--force-unclean`, which every row records; checking alone
  changes nothing on disk. Each unit gets an allow-listed environment, its own TMP / git identity / CCX_CONFIG /
  DSH_HOME / home for Codex and dsh, Claude without user settings, hooks, CLAUDE.md, skills or auto-memory (deny rules
  in the `//c/...` form for the real homes, every project's memory and transcripts, `~/.agents`), Codex in a dedicated
  CODEX_HOME; its processes start suspended in a Job Object and leftovers are killed and logged. Rows carry
  `fingerprint` (commit, task-file and tiers hashes, CLI versions, models, python / pytest / OS, isolation,
  concurrency, preflight result), `audit`, `leftovers` and `env_clean`; commit, versions and the machine are
  re-checked between units. `r5.py summary --tag` / `export --tag` keep rounds apart.
- New opt-in knobs for sub-agents, unchanged by default: `CCX_CLAUDE_SETTING_SOURCES` (`--setting-sources`),
  `CCX_CLAUDE_SETTINGS` (a JSON file merged into `--settings`), `CCX_CLAUDE_NO_SKILLS=1` (`--disable-slash-commands
  --strict-mcp-config` at every effort), `CCX_CODEX_ISOLATE=1` (`--ignore-user-config --ignore-rules`, Codex memories
  off, at every effort), `CCX_AGENT_HOME` (HOME / USERPROFILE of Codex and dsh sub-agents).
