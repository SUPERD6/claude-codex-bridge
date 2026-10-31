- Receipts say what a passed check covered (P1-10, display only; `ccx/coverage.py`): a write run's `check` record
  gets `covers` — the test files its pytest / unittest command ran (folders expanded; `unknown` for other commands),
  which of them the run edited (`edited`, `basis_changed`) or wrote (`written`, `own_tests_only`). The result's
  `check.covers` / `check.basis_changed`, the recap line (`check=passed (covers: …)`), `ccx show`, the queue's
  evidence line, probable verdicts and the ledger's `check` (`covers_n`, `basis_changed`, `own_tests_only`) show it.
  The verdict rules are unchanged. agent-delegate tells the lead to read edited tests first.
