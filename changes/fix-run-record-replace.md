- Windows: writing a run record retries for up to 3 s when another process has `run.json` open (`ccx stop` or
  `ccx show` polling it); before, the replace was refused for that moment and a stopped run's final state stayed
  `running` (seen in CI on PR #37). The stop tests now wait for their background ccx before the temp folder goes.
