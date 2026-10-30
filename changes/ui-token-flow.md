- `ccx ui` has a new page, "Measured & where tokens go" (read only). It shows the published numbers (hold-out and
  round-5 tables with their limits, from `ccx/data/measured.json`; a test checks every number against
  docs/measured.md), your own runs from your ledger (labelled not a controlled comparison), one ledger across Claude
  and Codex grouped by task with each run's own child sessions (Codex `codex_children`, Claude
  `<session>/subagents/*.jsonl`) and their share, and, when opened, a lead conversation's per-part re-read and cache
  breaks from the same functions as `ccx lead --breakdown` / `--cache`. Two new read-only endpoints, `/api/tokens` and
  `/api/leadcost`, capped in size. ccx's run behaviour and defaults are unchanged.
- README: one line on the one ledger across vendors (lead, sub-agents and their own child sessions; checked live
  2026-10-30 with codex-cli 0.164.0) and what Claude Code's own `/context` and `/cost` already show.
