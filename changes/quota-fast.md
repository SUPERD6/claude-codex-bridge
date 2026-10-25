- `--to auto` / `ccx route` no longer read a week of Codex session logs to know its quota. `quota.codex_readings`
  reads only the end (64 KB) of the session files changed in the last 48 hours (at most 40, newest first), plus
  small pieces further back at twice the distance each time, and parses only lines with `rate_limits`; when none of
  those has one it looks at up to 5 older files. Each file's readings are cached in
  `<hub>/ccx/codex-quota-cache.json` by (path, mtime, size). The pace now says when its reading was taken
  (`read_at`). Measured on one machine (144 session files, 2.5 GB): `ccx route --minutes 5` 13.9 s -> 0.70 s
  (quota 13.87 s -> 0.10 s uncached, 0.04 s cached), same projection as the full scan (0.224 vs 0.223).
