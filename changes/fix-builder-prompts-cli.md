- Codex builder notes: every Codex sub-run (fresh exec and exec resume, any system) is told to print the whole
  exec_command result or at least exit_code and session_id, and to continue a still-running command with
  `write_stdin` instead of starting it again; the Windows note no longer recommends `python -c` (`;` not `&&`, `*` is
  not expanded for python/pytest, Python with quotes/non-ASCII/several statements in a temp .py file, rg patterns in
  single quotes). Checked on codex-cli 0.164.0.
- `ccx run/ask/resume/way`: words after an option join the brief (`ccx resume R --check X "fix"` exited 2); a
  mistyped option still exits 2. The agent-delegate skill example puts the brief first.
- Hub config hygiene: a `~/.ccx/config.toml` or `layout.toml` that does not parse prints the file, line/column and a
  Windows-path hint on stderr (the hub fallback was silent); `ccx doctor` has a `ccx config` row (FAIL: does not
  parse, WARN: a control character in a value); `ccx init --hub` writes a single-quoted literal string; `ccx setup`
  counts [n/7].
- Claude sub-runs: `errors[]` of a failed result goes into the run's error (e.g. "No conversation found"), and
  `ccx resume` then says to send the task again with `ccx run --new`.
