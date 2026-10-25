- `ledger.is_eval(row, runs=None)`: one rule for "this run measured ccx, not the person's work" — label `eval-...`,
  started with `--no-ab`, or ccx's own probe (`selftest`, `quota-probe`). Verdict rows are judged by the run they
  point at (`ledger.runs_by_id`). `--no-ab` is now kept in the run's ledger row (`no_ab`) so it can be told apart.
  Statistics that learn or judge from real use call this to leave evaluations out.
