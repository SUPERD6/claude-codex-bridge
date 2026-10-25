# Status

English · [中文](STATUS.zh.md) · updated 2026-10-24 · version 0.4.0 · 284 tests

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
| J0 baseline, H11 first batch, E8 both ways, F9 on/off, J7 | ✅ PR #6 ([report](research/2026-10-24-h11-e8-f9-measurements.md)): lead median 352k tokens / $0.11 a request (7 days), ~55k fixed per request; delegating saved 1 lead request per small task only when the lead trusted the check; F9 started no sub-agents; J7 switch in, no overturn data yet |
| Fixes from that report: handoffs per file (parallel sessions), plan from a numbered list, the conversation's ccx runs in a handoff, saving measured or labelled a model, agent-delegate: don't re-run a passed check | ✅ PR #15 |
| J12 `ccx uninstall --apply` once for real, then back in (report 5c); fixed: line endings kept, the Codex block back in place, uninstall says how to reinstall the skills | ✅ PR #17 |
| J8–J10 official codex-plugin-cc, similar projects, name options (docs only, [landscape](research/landscape.md)) | ✅ PR #4; coexistence plan not implemented or tested; the name waits for the user |
| G1 `ccx ui` (read-only live page) + `ui.lang` | ✅ PR #7; `ccx stop` next (the adapters are in) |
| I1–I4 adapters per agent, vendor decides "another", fallback and reviewers from data | ✅ PR #11 — new interface: `ccx.agents.get(name)` → `Adapter` (build/parse, vendor, support, tested_version, capabilities()); `ccx.agents.vendor()`, `others()`; `ccx agents` lists them as JSON |
| J4 one step to a fresh conversation (`ccx fresh`) | ✅ PR #12 |
| J5 a model for the lead itself (`ccx lead --suggest`, a line in `ccx report`) | ✅ PR #13 |
| J11 `ccx/delegate.py` split by job, behaviour unchanged | ✅ PR #14 |
| F10–F14 own sub-agents: spend and quota limits, Agent tool for Claude, explicit "use sub-agents" for parts | ✅ PR #18 — limits not yet hit by a real run (sub-agents rarely start: PR #6) |
| H3–H4 + I7 `ccx discuss`: 2–3 vendors propose / find faults / judge, ≤3 rounds, points only; a conversation in `ccx ui`; the lead asks first | ✅ PR #22 — fake CLIs only; no real discussion run yet |
| H5–H6 + I6 shared memory in use: suggested notes the person accepts, this project first, usage counts, notes in the brief for tools without a start hook | ✅ PR #21 — suggestions are heuristic; **H7 waits for the user**: open a new Codex desktop conversation in this project and send "ok", to confirm the start hook arrives |

## Next three

1. H8–H9 ways of working (by risk; first-time-right and rework rates per kind of task).
2. J0 on real sessions (`scripts/eval/j0_baseline.py real --days 7`) a week after J1–J6, against the baseline in
   PR #6; spot-check 5 probable verdicts a week so J7 has an overturn rate.
3. Then the rest of the unified order: H7 (the user's check above), `ccx stop`, I5, H1–H2, H12, H14–H16, I8, and the open-source release.

## How sure we are (short)

**real** = run on a real Windows machine with logged-in CLIs; **fake** = tests with fake CLIs only.

- **real**: delegation both ways (read and write), `--check`, independent review, failure kinds, `--bg`, `ccx send`,
  auto-continue, `task resume` after a kill, memory on the Claude side, wiring (`sync --apply`), accounting and
  `ccx report`, DeepSeek as a provider, the E8 handover both ways (once each), `ccx lead --breakdown` / `--cache`, `ccx ui` (page and server in Edge on a hub of ccx runs on the fake CLIs,
  read-only once on the real hub; other browsers/OS not opened).
- **fake only**: worktrees, `ccx batch`, quota fallback to the other agent, the queue and seats, `--fork`, Gemini
  CLI, a real quota stop.
- **not calibrated**: routing priors (few real verdicts), the 10-minute checking window in `ccx trial`, the token
  estimates per part in `--breakdown` (the total is measured).
