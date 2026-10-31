- Eval: `--canary` now also runs a Codex canary when an arm needs Codex (`CODEX_ARMS`): one real `codex exec` with a
  unit's own command line (`codex_invocation`: the T1 Codex model and effort, `[permissions.codex] write`, no lean
  tools; the eval CODEX_HOME, `CCX_CODEX_ISOLATE=1`) that must run one shell command and return its output in a
  `command_execution` item; a non-zero exit, a timeout, "setup helper" or error 1223 with the launch on the same line
  (launch_canceled / ShellExecuteExW / "os error") or `ENV_MARKERS` in stderr, an error event / error item or the
  command's output, or no such output fails the preflight before any unit, unless `--force-unclean` (round pg1 lost
  13 units to a stale elevated-sandbox password). A canary that cannot run at all is a problem, not a traceback. The
  eval home is checked again after it (`codex_home_drift`, the connector / plugin catalog caches); reports carry
  `codex_canary`. `r5.py run` and `batch.py run` have the canaries on by default (`--no-canary`), so every round now
  makes one more Codex request.
- Eval, Windows: the eval CODEX_HOME must use `[windows] sandbox = "unelevated"`: elevated or unset is now a preflight
  problem (before any canary), and a new eval home's config.toml is written with it instead of copying the person's
  own setting. The canary records `.sandbox-secrets` of the eval home and the person's CODEX_HOME before and after
  (existence and mtime only, never read) and prints a loud warning when either changed.
- Eval: the eval CODEX_HOME's Windows sandbox is recorded (`codex.windows_sandbox`: elevated / unelevated / unset /
  n/a; every row's `fingerprint.codex_windows_sandbox`); `r5.py summary` and `batch.py summary` count, over the same
  rows (no `error`, clean or not, arm starts Codex), each row's effective sandbox (a daily arm's own first; `unknown`
  for a row from before the field) under `codex_windows_sandbox` and print a warning when rows ran under more than
  one value, `unknown` included.
