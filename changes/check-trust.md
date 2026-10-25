- J7, how far an acceptance command can be trusted: `ledger.check_trust(rows, p=None)` groups runs by their
  `--check` command and place (the folder name, numbers collapsed; a ccx worktree counts as its repository) and counts
  how often a pass was then judged wrong by the person or the lead. With at least 3 judged and more than 20% wrong the
  command is `weak`: its pass no longer makes a probable verdict (the run waits for a person), the run result's `check`
  says `weak` with a note, and `ccx report` has a "Where it was wrong" card listing such commands. The run's ledger row
  now keeps its check (`check: {key, cmd, passed}`); older rows are read from their run.json. Replayed on the
  seven-cores round-1 ledger: all 19 runs that passed the check but failed the hidden tests (the report's 14 in groups c
  and d, 3 inventory runs of the delegation arm, 2 of the pilot) fall in weak groups, and no group without such a run is flagged.
