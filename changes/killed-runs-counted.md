- Killed and abandoned runs are counted. An attempt stopped mid-run (timeout, spending cap, `ccx stop`) prints no
  final usage line, so its usage is read back: Claude's assistant events in the stream (each message once, or its
  transcript), Codex's session file (rollout; only the growth is counted, as for a resume). Ctrl+C or a crash in
  ccx itself records the attempt in flight as `kind=killed`, the run as `state=interrupted`, with one ledger row.
  `ccx stats`, `ccx show` and `ccx resume` first close every `running` record whose ccx process is gone (a dead pid
  on this machine, or no heartbeat for 10 minutes) as interrupted, with the usage read back, so it is counted and
  can be resumed. `ccx stop` on such a run records the usage too. None of this is learned by routing.
