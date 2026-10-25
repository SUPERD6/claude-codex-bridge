- DeepSeek can lead, by two routes, tested on a real machine: DeepSeek Harness (`dsh` 0.2.1-rc.3 headless) handed
  work to Codex, and Claude Code running a DeepSeek model (`--bare`, ANTHROPIC_BASE_URL) handed work to Claude.
  `lead_identity()` tells the lead from the environment (`DSH_SESSION_ID`; the provider whose ANTHROPIC_BASE_URL
  Claude Code uses; Codex's config.toml `model_provider`; or `CCX_LEAD`), `--from` accepts dsh and the providers,
  and every run records `caller_vendor` (deepseek on all three routes). `dsh` is `can_lead`; `ccx mem delta --as
  claude` counts the notes for the provider when Claude Code runs one. A Claude sub-agent of such a lead gets neither
  the lead's DeepSeek endpoint and key nor `CLAUDE_CODE_SIMPLE` (which made it bare and "Not logged in").
- ccx finds the `dsh` bundled with the DeepSeek Harness desktop app on Windows from the uninstall registry's
  InstallLocation when it is not on PATH (adapters get an optional `locate()`); `ccx doctor` shows where. Tests set
  `CCX_NO_LOCATE` so they never find a real CLI.
- A dsh session keeps the read-only / write mode it started with, so ccx no longer continues a dsh session across
  read and write (a write task continued in a read-only session could not edit, real run).
- `ccx sync` warns when, with an external snapshot, a lead such as dsh does not load it. agent-delegate says how
  DeepSeek leads (PowerShell 5.1 shell, `--brief-file`, dsh needs `danger-full-access` and what that means). README
  (EN + ZH): leads are Claude Code, Codex and DeepSeek (tested); Gemini CLI untested.
