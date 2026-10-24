# claude-codex-bridge — instructions for coding agents (Claude Code, Codex, Gemini CLI)

`ccx` lets Claude Code and Codex (and Gemini CLI) be each other's lead / sub-agent, with shared skills, MCP,
incremental memory, resumable runs and token accounting. Python 3.11+, standard library only.

**Start here:** read `docs/STATUS.md` (what is done, how sure we are, the prioritized next steps), then
`.ccx/handoff.md` if it exists (personal, local notes from the previous session). Keep docs/STATUS.md and
docs/STATUS.zh.md up to date as you finish or discover items.

## Layout
- `ccx/` — the CLI (`python ccx.py -h`): `cli.py` (parser + `main`), `commands/` (one module per command group,
  each with `register(sub)`: `delegation`, `memory`, `install`, `records`; shared helpers in `common`),
  `setup.py` (the `ccx setup` wizard), `delegate.py` (run loop), `runners.py` (per-agent argv + parsers),
  `learn.py` (bridge to the skills), `memory.py` / `project.py` (shared + project memory, handoff),
  `sync.py` (wiring into both tools), `ledger.py` / `usage.py` / `report.py` (accounting, dashboard),
  `archive.py` (session archiving), `doctor.py`.
- `skills/` — standalone skills: `agent-delegate`, `task-routing`, `task-split`, `task-checkpoint`.
- `config/tiers.toml` — defaults (tiers, permissions, slim start-up, sessions, providers).
- `tests/` — fake CLIs in `tests/fakes/`; never call real CLIs in tests.
- `docs/` — DESIGN, DECISIONS (bilingual table), STATUS (progress + next steps), research.

## Rules
- Run `python -m pytest -q tests` before every commit; all must pass (CI: Linux/Windows/macOS × 3.11–3.13).
- Generic only: no personal paths, names or data in the repo. Personal things live in the user's hub.
- Docs are bilingual: `x.md` (English) + `x.zh.md` (Chinese), linking to each other. Update CHANGELOG.md and,
  for real decisions, docs/DECISIONS.md.
- Verify external CLI facts against `--help` / official docs before relying on them; note the version checked.
- Never touch credentials; never hand-edit the tools' config files outside ccx's marked blocks.
- Small commits with clear messages; bump `ccx/__init__.py` and `pyproject.toml` for releases.
