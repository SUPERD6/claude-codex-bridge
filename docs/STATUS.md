# Status

English · [中文](STATUS.zh.md) · updated 2026-10-24 · version 0.4.0 · 241 tests

One page on purpose: whatever an agent reads at start-up it re-reads on every later turn. Older notes, the full
confidence table, acceptance checks and the done list are in [STATUS-archive.md](STATUS-archive.md); what changed
is in [CHANGELOG.md](../CHANGELOG.md). Keep this page short: when something is done, say so in one line here and
put the detail in the changelog.

## Now

The order comes from the shared plan (proposals F–J, all approved). **J13** moved the lead-cost items first,
because nearly all spend is the lead re-reading its own conversation (sub-agents: $0.34 in 30 days; a median lead
turn re-reads ~220k tokens):

| Step | State |
|---|---|
| H13 verdicts without asking | ✅ PR #2 |
| H10 the lead's own context (`ccx lead`, per-turn hint) | ✅ PR #3 |
| H11 week-long comparison: the tool (`ccx trial`) | ✅ PR #5 — the week of data is collected by the eval session (PR #6, with J0, E8, F9) |
| J1 + J2 what a turn re-reads, where the cache broke (`ccx lead --breakdown`, `--cache`) | ✅ PR #8 |
| J3 long output cut down before the lead reads it (`ccx sum`) | ✅ PR #9 |
| J6 this page down to one page | ✅ PR #10 |
| J8–J10 official codex-plugin-cc, similar projects, name options (docs only, [landscape](research/landscape.md)) | ✅ PR #4; coexistence plan not implemented or tested; the name waits for the user |
| G1 `ccx ui` (read-only live page) + `ui.lang` | PR #7; `ccx stop` waits for the adapter refactor |
| I1–I4 adapters per agent, vendor decides "another", fallback and reviewers from data | this change — new interface: `ccx.agents.get(name)` → `Adapter` (build/parse, vendor, support, tested_version, capabilities()); `ccx.agents.vendor()`, `others()`; `ccx agents` lists them as JSON |

## Next three

1. F10–F14 on the new adapters; then J4, J5, J11.
2. J4 one-step handover to a fresh conversation, J5 a model suggestion for the lead itself, J7 how often probable
   verdicts get overturned (with the eval session's numbers).
3. Then the rest of the unified order: H5–H7 + I6 shared memory, H3–H4 + I7 `ccx discuss`, H8–H9, `ccx stop`, I5, H1–H2, H12, H14–H16, I8, and the open-source release.

## How sure we are (short)

**real** = run on a real Windows machine with logged-in CLIs; **fake** = tests with fake CLIs only.

- **real**: delegation both ways (read and write), `--check`, independent review, failure kinds, `--bg`, `ccx send`,
  auto-continue, `task resume` after a kill, memory on the Claude side, wiring (`sync --apply`), accounting and
  `ccx report`, DeepSeek as a provider, the E8 handover both ways (once each), `ccx lead --breakdown` / `--cache`, `ccx ui` (page and server in Edge on a hub of ccx runs on the fake CLIs,
  read-only once on the real hub; other browsers/OS not opened).
- **fake only**: worktrees, `ccx batch`, quota fallback to the other agent, the queue and seats, `--fork`, Gemini
  CLI, `ccx uninstall --apply`, a real quota stop.
- **not calibrated**: routing priors (few real verdicts), the 10-minute checking window in `ccx trial`, the token
  estimates per part in `--breakdown` (the total is measured).
