- Sub-agent sessions are archived as soon as their run's result is final (`sessions.archive = "after_run"`, the
  new default; `hours` keeps archiving only after `sessions.auto_archive_hours`, `off` never by itself): done and
  checked (`--check` passed, or the sub-agent checked itself), or judged with `ccx verify`. Runs that may still go
  on are kept (quota, timeout, stop, kill, blocked, failed check, review issues), and seats, discussions and reviews
  are left alone. `ccx resume` and the 1-hour auto-continue bring an archived session back first (`codex
  unarchive`, codex-cli 0.164; Claude's transcript moved back). A session archived by hand is still not
  auto-continued. Real run (gpt-6-luna low): run `20261025-120720-392d` archived right after its check passed;
  `ccx resume` brought it back and continued the same session (`20261025-120740-b4d6`, 74k cached tokens), which
  was archived again when it finished. Tests switch it off with `CCX_NO_AUTO_ARCHIVE=1` unless they are about it.
