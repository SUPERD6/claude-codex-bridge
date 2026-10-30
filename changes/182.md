- `scripts/eval/daily_home.py`: on Windows every daily arm's per-unit Codex home gets `[windows] sandbox =
  "unelevated"` in its config.toml (replacing the person's own `windows.sandbox`; nothing new elsewhere). A fresh home
  has no `.sandbox-secrets` for Codex's machine-wide elevated sandbox accounts, so its setup helper needed UAC, was
  cancelled unattended and every command failed (codex-cli 0.164.0); re-running setup would rotate the shared accounts
  and break the other homes. Rows record `daily.windows_sandbox` (fingerprint `isolation.daily_windows_sandbox`),
  `daily-check` and `run --dry-run` show it. Limitation: the person's real setup uses the elevated sandbox; the daily
  arms compare the switches with each other under the unelevated one.
