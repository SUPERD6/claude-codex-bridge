# Could Gemini CLI be a lead? (2026-10-25)

English · [中文](2026-10-25-gemini-lead.zh.md)

Not built. This note says what it would take, so the person can decide. Gemini CLI is not installed on the
machine this was written on; nothing here has run for real.

## What a lead needs in ccx, and what Gemini CLI offers

A lead is an adapter with `can_lead = True`: ccx shows it the shared memory when a conversation starts, and can
read its conversations for cost, hand-offs and the per-turn hint. `--as` (in `ccx mem delta`, `ccx fresh`,
`ccx lead`) now takes its choices from the adapters (`ccx.agents.leads()`), so flipping that flag is the only
registry change.

| Needed | Claude Code / Codex today | Gemini CLI (docs read 2026-10-25) |
|---|---|---|
| Start hook that adds context | SessionStart → `ccx mem delta` | **Yes.** `SessionStart` (source startup / resume / clear), output `hookSpecificOutput.additionalContext`: "Injected as the first turn in history" interactively, "Prepended to the user's prompt" non-interactively. geminicli.com/docs/hooks/reference, last updated 2026-04-10 |
| Per-turn hook (long-conversation hint) | UserPromptSubmit → `ccx lead --hint` | **Yes.** `BeforeAgent`: additionalContext "appended to the prompt for this turn only" |
| Where hooks are configured | `~/.claude/settings.json`, `~/.codex/config.toml` | `~/.gemini/settings.json` (user), `.gemini/settings.json` (project), `hooks.<Event>[].hooks[]` with `type: "command"`, `timeout` in ms (geminicli.com/docs/hooks, last updated 2026-04-13) |
| Instruction file | CLAUDE.md / AGENTS.md | GEMINI.md (the adapter already names it) |
| Reading its conversations | session JSONL files | **Unknown**: where and in what format Gemini CLI keeps chats was not checked |
| Quota | readable for both | not readable (already `quota_readable = False`) |

Caveat on the docs: their banner says Gemini CLI was replaced by Antigravity CLI for unpaid and Google One users on
2026-06-18. Which CLI the person would use decides whether this work is worth it. The ccx adapter was written
against Gemini CLI 0.65.0's source.

## The work, in pieces

1. **Start hook + memory (small, one PR):** `ccx sync` writes a marked SessionStart entry into
   `~/.gemini/settings.json`; `ccx mem delta --as gemini` prints the JSON Gemini expects
   (`{"hookSpecificOutput": {"additionalContext": "..."}}`) instead of plain text; doctor checks the entry;
   `can_lead = True`, `start_hook` filled in; tests with a fake Gemini. About half a day.
2. **Per-turn hint (small):** a `BeforeAgent` entry → `ccx lead --hint --as gemini`, same JSON. A few hours, but the
   hint reads the lead's own conversation, so it waits for piece 3.
3. **Reading its conversations (medium):** find Gemini CLI's chat files, write `lead_events` (tokens per turn) and
   the transcript reader for `ccx fresh` / `ccx handoff --from-transcript`. One to two days, and it needs the real
   CLI to see the files.
4. **The skills in Gemini (unknown):** the lead is told how to delegate by the agent-delegate skill. Whether Gemini
   CLI loads skills from a folder, or only through GEMINI.md or extensions, was not checked.
5. **A real check:** install, log in, run pieces 1–3 once (read-only and write sub-tasks from a Gemini lead), record
   the version in `tested_version`.

Pieces 1–2 alone give a Gemini lead the shared memory; without 3 its own cost is not in the ledger and hand-offs
from it must be written by hand (`ccx handoff`).
