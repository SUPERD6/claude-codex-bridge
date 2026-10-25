- Fix: a plain terminal was taken for a Codex lead when the person had `CODEX_SQLITE_HOME` or the installer's
  `CODEX_INSTALL_DIR` set for good (any `CODEX_*` but `CODEX_HOME` counted). `ccx say --from claude` then failed with
  "runs inside codex", and `ccx run` recorded the caller as Codex. Codex is now recognised by the variables it sets
  for the commands it runs (codex-cli 0.164, checked on a real run: `CODEX_THREAD_ID`, `CODEX_SESSION_ID`,
  `CODEX_TOOL_CALL_ID`, `CODEX_CI`, `CODEX_SANDBOX*`).
