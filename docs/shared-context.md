# Shared work context

English · [中文](shared-context.zh.md)

Claude Code, Codex and DeepSeek each keep their own context window; no tool can read another's, and ccx does not
pretend they share one. What ccx adds is a **shared work context**: a short summary of what a session has been doing
lately, read by code from the tool's own session file (no model call), that the other tools can read. It reaches them
in three ways.

| Where | What the other tool gets | Switch |
|---|---|---|
| A delegated task (`ccx run`) | the lead's recent work: the person's last asks, sentences that settled something, the lead's plan, the files it changed, its latest message; each line with its time and source; about 1–1.2k tokens in English (5000 Chinese characters are ~2.2–3k) | `--context auto\|on\|off`; auto (default) = write tasks only; `[shared_context] run` |
| `ccx peek claude\|codex\|deepseek` | a read-only look at that tool's newest open session in this project (or `--session ID`) | — |
| The per-turn hook (`ccx turn`) | one line per other tool that did something since this reader last looked: what its person asked, what was settled, which files changed | `[shared_context] turn = false` |

Experimental, off by default: `[shared_context] dedupe = true` leaves out a "Settled" sentence that was cut from one
of the person's asks shown above it and stands there whole (the same words twice); a decision the lead stated later
stays, even in the same words, nothing else is cut and the size limit is unchanged. A run
that attaches the block records its rough size as `est_tokens` in run.json's `shared_context`, and with the switch on
how many sentences it left out. How many items are shown is decided on the text without dedupe, so the two settings
differ only by the repeated sentences (and, when the block is still too long at the fewest items, by
how much of its end the final character cut takes off). It stays off until a rerun of the 2026-10-25 A/B shows first-try-right does not drop.

Everything is framed as **data, not instructions**: the block's header says so, the sub-agent's rules name it, the
leads' memory block and the project's AGENTS.md (via `ccx board --init`) say it again. A sub-agent's own task and the
person's instructions decide; a line from another session never does.

## What is read

| Tool | File | Read |
|---|---|---|
| Claude Code | `projects/<folder>/<session>.jsonl` | person messages, assistant text, Edit / Write / MultiEdit / NotebookEdit, TodoWrite and the desktop plan tool; side chains and compact summaries skipped |
| Codex 0.164 | `sessions/**/rollout-*.jsonl` | UserMessage, AgentMessage, FileChange, update_plan, apply_patch |
| dsh 0.2.1-rc.3 | `~/.dsh/sessions/<folder>/<session>/session.v4.jsonl.zstd` | user/message, assistant/message text, edit / write, todo_write |

dsh compresses its session files with zstd, which Python 3.11's standard library cannot read. ccx decodes them with
Node ≥ 22.15 (`CCX_NODE`, or `node` on PATH) or with the Electron that ships dsh, run as Node (found through
`CCX_DSH_BIN`'s launcher). Without either, `ccx peek deepseek` says so. On Windows dsh's folder names repeat the whole
project path, so ccx reads them with long-path names.

"Settled" sentences are picked by words such as *decided, agreed, going with, from now on, never, must, instead of*,
and 决定 / 定了 / 约定 / 改成 / 不要 / 必须 / 以后. It is a heuristic: it can miss a decision worded otherwise, and it
can pick a sentence that only sounds like one. The person's own recent messages are included whole (cut at 500
characters), so a missed decision is often still there. Secrets are redacted as in `ccx handoff`.

## What it is not

- Not one context: each tool still reads only its own conversation plus this summary.
- Not a transcript copy: at most ~5,000 characters for a task, ~400 for a hook turn.
- Not instructions: see above.
- ccx's own headless sub-runs are never shown as someone's "open session" (excluded by the run ledger, and dsh
  sessions that start with ccx's sub-task line).

## Measured

See [docs/research/2026-10-25-shared-context-ab.md](research/2026-10-25-shared-context-ab.md).
