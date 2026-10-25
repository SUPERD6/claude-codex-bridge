- Windows: background discussions and the board now wait for a reader too when they replace their state files
  (`ledger.replace`, the retry `run.json` got in #48); a background discussion's state write failed once in CI
  (PR #67). `ccx discuss --show` reads the state with the same retry.
