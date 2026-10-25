# The board on real CLIs: acceptance run (2026-10-25)

English · [中文](2026-10-25-board-acceptance.zh.md)

What was checked: the board (#66 `say` / `reply` / `board`, #74 per-turn hook `ccx turn`, #76 `--now` / `--resume`)
with the real Codex and DeepSeek CLIs, from a Claude Code session. Versions: codex-cli 0.164.0, dsh 0.2.1-rc.3,
Claude Code desktop (this session, Opus).

## Setup

- A throw-away git project with one buggy function (`calc.py`: `average(xs)` divides by zero on `[]`),
  `ccx project init`, `ccx board --init`, `CLAUDE.md` = `@AGENTS.md`.
- A temporary `CCX_HUB` with the same "no DeepSeek cap" lines as the person's hub (`daily_usd = 1000` for
  `providers.deepseek`, `providers.deepseek-codex`, `pay_per_token.dsh`); `CCX_DSH_BIN` pointed at `dsh.cmd`.
- Two headless sub-sessions to talk to: `ccx run --to codex --model gpt-6-luna --effort low --mode read ...` and
  `ccx run --to dsh --model deepseek-flash --effort low --mode read ...` ("read calc.py, say what average does").

## What happened

| Step | Result |
|---|---|
| `ccx say --to codex --thread avg --resume <codex run>` (from this Claude session) | #2 posted, `from`/`via` = `claude:<session>`; Codex answered, posted as #3 `codex -> claude:<session>`, `re #2`, `via ccx-run:<id>` |
| `ccx say --to deepseek --thread avg --resume <dsh run>` | #1 posted; DeepSeek answered, posted as #4 `deepseek -> claude:<session>`, `re #1` |
| Follow-up to DeepSeek after the fix below | #5 / #6: DeepSeek remembered the thread and agreed with Codex (ValueError on empty input) |
| `ccx board --all` | 6 messages; every `from` / `via` right; every reply's `reply_to` points at the message it answers |
| `ccx turn --as claude` with this session's id (what the Claude hook runs) | first turn: #3, #4, #6 (long one cut to a first line + `ccx board --thread avg`); second turn: nothing |
| `git status` in the project | `.ccx/board.jsonl` not listed (ignored); `context.md`, `journal.jsonl` listed (meant to be shared) |

## Found and fixed

- With `--resume`, the message pushed into the headless run said "answer with `ccx reply`". DeepSeek tried, and
  wrote "I could not post this ... because `ccx` is not on PATH in this environment" into its answer (ccx posted
  the answer anyway). Now a `--resume` message says the answer is posted for it and not to run `ccx reply`; the
  re-run (#5 / #6) answered cleanly. A test checks the wording.

## Cost

| Who | Model | Runs | Tokens (fresh in / cached / out) | Money |
|---|---|---|---|---|
| DeepSeek (dsh, pay per token) | deepseek-flash low | 3 | 6,974 / 93,696 / 2,836 | **$0.0030** (ccx ledger; real money) |
| Codex (subscription) | gpt-6-luna low | 2 | 7,219 / 48,640 / 392 | $0.0014 API-equivalent, no extra money |
| Claude (this lead session) | — | — | the `say` / `board` commands call no model | only this session's own turns |

The DeepSeek console figure before/after was not read (no access from here); the ledger number is ccx's estimate
from the token counts.

## Not verified

- **Codex desktop per-turn hook**: skipped on purpose (H7: no hook output from Codex desktop has been seen yet;
  ccx-memory is looking at the trust key). Unverified.
- **`ccx say --now` into a live Codex desktop conversation**: needs an open Codex desktop thread in the project;
  not run. Covered by tests with a fake `codex queue` only.
- **DeepSeek desktop reading the board by the AGENTS.md rule** (`ccx board --as deepseek` each turn): not run. The
  headless run shows `ccx` may not be on dsh's PATH; on a machine where it is not, that rule cannot work.
- The Claude hook was exercised by running `ccx turn --as claude` with the hook's JSON, not by a new desktop turn.
