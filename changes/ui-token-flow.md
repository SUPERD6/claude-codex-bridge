- `ccx ui` has a new page, "Measured & where tokens go" (read only). It shows the published numbers (hold-out and
  round-5 tables with their limits, from `ccx/data/measured.json`; the hold-out's external-repository rows as their
  own table; a test checks every cell, by arm and run, against the tables in docs/measured.md and measured.zh.md),
  your own runs from your ledger (labelled not a controlled comparison), one ledger across Claude and Codex grouped
  by task with each run's own child sessions (Codex `codex_children`, Claude `<session>/subagents/*.jsonl`) and their
  share (a resumed or continued run shows only what its children added; a Claude session used by several runs is
  split by each run's time window; the share is not capped), and, when opened, a lead conversation's per-part
  re-read and cache breaks from the same functions as `ccx lead --breakdown` / `--cache`. Two new read-only
  endpoints, `/api/tokens` and `/api/leadcost`, capped in size. ccx's run behaviour and defaults are unchanged.
- README: one line on the one ledger across vendors (every sub-agent run and its own child sessions; checked live
  2026-10-30 with codex-cli 0.164.0) and what Claude Code's own `/context` and `/cost` already show.
