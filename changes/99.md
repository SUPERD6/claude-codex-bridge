- `ccx ui` and the session-start "N delegated piece(s) wait for you" leave out evaluations and tests by default:
  eval-* labels, `--no-ab`, ccx's probes (now also `startup-probe`, `two-way-*`), runs in the system's temporary folder
  or inside a project's `.ccx` folder (unless the hub itself is temporary), and the projects and lead conversations
  there. A "show evaluations and tests" switch on the page brings them back.
- `ccx verify RUN --dismiss --note why`: a test or leftover counts neither right nor wrong. It leaves "waits for you",
  `--sweep` skips it and routing, splitting and the statistics leave it out (`ledger.is_eval`); a later `--ok`
  undoes it, and a run that already has a verdict cannot be dismissed.
