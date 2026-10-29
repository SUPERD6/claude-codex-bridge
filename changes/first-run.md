- First delegation: a person at a terminal (no lead tool detected, or `--from user`) who names `--to` gets a task
  routing calls too small delegated anyway, on the cheapest rung, with one stderr line saying doing it yourself
  would be cheaper (`route.cheaper_self`); a lead's call is still refused as before. README, docs/install and
  `ccx setup` now suggest the same first command, one a lead's call delegates too.
- Environment failures (the agent CLI's own launcher could not start, seen in its stderr: ShellExecuteExW /
  CreateProcessWithLogonW / orchestrator_helper_launch) end the run as `kind: env` with a fix hint: no climb to a
  pricier rung, no retry, not learned from. The sub-agent's summary and generic "CreateProcess failed" lines do not
  count, so a task about process code still climbs. `ok` is false whenever the status is blocked or failed, in
  `ccx run` and `ccx selftest` alike (exit codes unchanged). A foreground `ccx run` / `resume` on a terminal prints
  one progress line to stderr about every 30 s (`CCX_PROGRESS_SEC`); a lead's piped call gets none.
- `ccx setup` without a terminal shows every remaining step as the exact command (`ccx init --hub`, `ccx sync`,
  `ccx sync --apply`, `ccx doctor`, the first delegation) and changes nothing; a CLI that is not logged in skips the
  selftest (also with `--yes`) and its login is listed first at the end.
- `ccx doctor`: the login row shows the real status line and the login command; the closing lines list what to do in
  order (logins, `ccx init`, then sync); "Codex as lead (sandbox)" is one info line unless `--codex-lead` (or Codex
  runs doctor). The recap after an auth failure points at the login.
- On a terminal, `ccx run` / `resume` / `route` end with two or three plain lines (result, cost, next command);
  piped output is the same JSON as before. `ccx route` labels follow `ui.lang` (English unless set to zh).
- `ccx undo` is listed under Everyday, `--apply` has help text, and a run that changed nothing says so in one line;
  when git cannot list the run's files (base commit gone) it reports `git_error` instead.
- Routing: a one-line edit ("add a line ... to README.md") no longer scores standard dev (T2); it starts on T1.
  Briefs that also carry hard, design or critical work keep their tier, and the pull-down never makes a brief T0.
- README (EN + ZH) states the same rule for the first command: from your own terminal `--to` delegates even a very
  small task; a lead's call still gets it turned back.
