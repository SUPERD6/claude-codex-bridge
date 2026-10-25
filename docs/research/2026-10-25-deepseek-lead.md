# DeepSeek as lead and as `dsh` sub-agent: real runs (2026-10-25)

English · [中文](2026-10-25-deepseek-lead.zh.md) · DeepSeek Harness desktop 0.2.1-rc.3 (its bundled `dsh`, found by ccx
from the uninstall registry) · Claude Code 2.1.309 · codex-cli 0.164.0 · Windows 11 · temporary `CCX_HUB`

All runs on one small repo (`calc.py` with `add` returning `a - b`, `test_calc.py`), T1 (DeepSeek `deepseek-flash low`,
Codex `gpt-6-luna low`, Claude `haiku low`). DeepSeek spent about $0.01 through ccx, plus the two lead sessions
themselves (a few cents at most), within the day's $1.

## `dsh` as a sub-agent (I5)

| Run | Result | $ |
|---|---|---|
| read-only: which test fails and why | done, right answer; the read-only sandbox held (pytest could not write its temp folder) | 0.0023 |
| write, continued from the read run's session | **blocked**: the session kept read-only, so it could not edit | 0.0016 |
| write, new session (`--new`), `--check "python -m pytest -q -p no:cacheprovider"` | done; `add` fixed; ccx's own run of the check passed | 0.0010 |
| resume the write session: add `sub` and its test | done in the same session (same `session-…` id); 3 tests pass. ccx's independent review then flagged `return a - b` in `sub` as a bug (a false positive); dsh checked and said so | 0.0013 + 0.0009 |

Fixed from this: ccx no longer continues a dsh session across read and write (its permission is set when the session
starts, through `DSH_PERMISSION_MODE`).

## DeepSeek as the lead

| Lead | Command it ran | Ledger | Notes |
|---|---|---|---|
| `dsh --profile headless` with `DSH_PERMISSION_MODE=workspace-write` | `ccx run --to codex ...` | – | **failed**: `[WinError 5]` writing the hub's run folder; escalation needs an approval channel headless dsh does not have |
| same, `danger-full-access` | `ccx run --to codex ...` | caller `dsh`, caller_vendor `deepseek`, done | Codex answered without opening the file; the same task from a Claude Code lead did the same, so that is luna low on read tasks, not dsh |
| `claude -p --bare --model deepseek-flash` (ANTHROPIC_BASE_URL = DeepSeek) | `ccx run --to claude ...` | caller `deepseek`, caller_vendor `deepseek` | first try: the Claude sub-agent said "Not logged in"; the bare lead passes `CLAUDE_CODE_SIMPLE` on. Fixed; second try done, Claude read the file and answered correctly, priced as Claude (`haiku`) |

Seen on the way: dsh gives the commands it runs `DSH_SESSION_ID`, `DSH_PROFILE`, `DSH_HOME` and `DSH_SHELL`; its shell
on Windows is Windows PowerShell 5.1; a multi-line task passed as an argument to `dsh.cmd` is cut at the first line
(use stdin, `-`). dsh 0.2.1-rc.3 has no command hooks: it reads `$DSH_HOME/AGENTS.md`, `<agentsHome>/AGENTS.md` and
the project's `AGENTS.md` / `CLAUDE.md`.

## Not run

Codex running a DeepSeek model as the lead (recognised from config.toml `model_provider` or `CCX_LEAD`); the dsh
desktop app's own sessions as lead (only headless was run); Gemini CLI (the person chose not to install it); Kimi,
GLM, Qwen, OpenRouter (no keys); macOS and Linux.
