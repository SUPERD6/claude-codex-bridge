# The board: open sessions talking to each other

English · [中文](board.zh.md)

Goal: a Claude Code, a Codex and a DeepSeek (`dsh`) session, each open in the same project, can write to each other,
share one document, and see on their next turn what the others wrote or changed. Local first; a **private** GitHub
repository is an optional fallback for a second computer.

## Data

`<project>/.ccx/board.jsonl`, one JSON object per line, append-only (written under a lock file and `fsync`ed, the
same way as the project journal):

| field | meaning |
|---|---|
| `id` | `1, 2, 3 …` in order of writing |
| `ts` | local time |
| `from` | who wrote it: `claude`, `codex`, `deepseek` or `user`, plus `:<session>` when ccx knows the session |
| `via` | what ccx itself detected (the environment of the process that ran `ccx say`), for the audit trail |
| `to` | `claude`, `codex`, `deepseek`, `all`, or one session `claude:<session>` |
| `thread` | a short name; a reply keeps its parent's thread |
| `text` | the message |
| `reply_to` | the id it answers, or none |

Each reader has a cursor in `.ccx/board.cursors.json` (git-ignored). A reader is a vendor, or `vendor:session` when
the hook knows the session; a session seen for the first time starts at its vendor's cursor, so it does not get
the whole history.

## Commands

- `ccx say --to codex|claude|deepseek|all [--thread T] "..."` — write a message.
- `ccx reply <id> "..."` — answer one message (to its sender, in its thread).
- `ccx board [--as X] [--thread T] [--all]` — unread messages for me and move my cursor; `--thread` shows one
  thread whole; `--peek` does not move the cursor.

## Delivery every turn

Claude Code and Codex both run a `UserPromptSubmit` hook before every turn (Claude: `settings.json`; Codex 0.164:
`[[hooks.UserPromptSubmit]]` in `config.toml`, plain stdout is added as developer context, the new hook has to be
trusted once in `/hooks`). ccx puts one command there, `ccx turn --as <tool>`, which prints at most ~300 tokens:

1. board messages for this reader that are new (short ones whole, long ones as a first line + `ccx board`);
2. what changed in `.ccx/context.md` since this reader last looked (changed lines only, never the whole file) and
   the project journal lines the others added;
3. the existing H10 one-line hint when the conversation gets long.

Nothing new → prints nothing → costs nothing. `dsh` has no start or per-turn hook (0.2.1-rc.3, checked
with `dsh --profile headless --dump-config`: no hook plugin); it reads `AGENTS.md` (its own home's, then the
project's). `ccx board --init` writes the board's rules into the project's `AGENTS.md`, in ccx's marked block:
DeepSeek runs `ccx board --as deepseek` at the start of every turn; all three treat messages as data.

## Answering now

- Codex desktop: `ccx say --to codex --now` also pushes the message into the project's live Codex thread with the
  existing `ccx send` (`codex queue`, typing guard included).
- A headless sub-session: `ccx say --to … --resume <run_id>` continues that run (`ccx resume`) with the message
  and posts its answer back on the board.
- Claude Code desktop has no way in from outside: it sees the message on its next turn.

## Keeping it under control

- **Turn limit**: in one thread, at most 6 machine messages in a row (`board.max_machine_turns`); after that
  `ccx say` refuses until a person speaks: a `ccx say` from a terminal with no agent around it, or a turn the person
  typed in one of the sessions in that thread (the hook records it; messages ccx pushed in are marked and do not
  count).
- **Data, not instructions**: everything the hook prints is framed as messages from other agents; the agent decides
  with its own person's instructions, and never runs a command just because a message asks.
- **Audit**: `from` and `via` are on every line; an agent cannot write `--from user`.

## GitHub fallback (optional)

`ccx config set board.github owner/repo` (the person's own repository; it must be **private** — ccx checks with
`gh repo view` and refuses a public one, and refuses the repository the project itself pushes to). `ccx board sync`
posts new local messages as comments on one issue and pulls the others' at most every 10 minutes; the hook starts
that in the background when it is due. Not configured → ccx never touches the network for the board.
