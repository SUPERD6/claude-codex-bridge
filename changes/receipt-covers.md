- Receipts say what a passed check covered (P1-10, display only; `ccx/coverage.py`): a write run's `check` record
  gets `covers` — the test files its pytest / unittest command names (folders expanded via git, pytest's file names;
  `unknown` for other commands), `filtered` (`-k` / `-m` / `--deselect` / node ids), and which of them the run edited
  (`edited`, `basis_changed`, a `conftest.py` above them included), only added tests to (`added_to`) or wrote
  (`written`, `own_tests_only`). The result's `check.covers` / `check.basis_changed`, the recap line
  (`check=passed (covers: …)`), `ccx show`, the queue's evidence line, probable verdicts and the ledger's `check`
  (`covers_n`, `basis_changed`, `own_tests_only`, `filtered`, `added_to`) show it. The verdict rules are unchanged.
  agent-delegate tells the lead to read edited tests first.
- A pytest `-k` / `-m` expression written without quotes (`-k undo or verify`) is quoted before the check runs
  (cmd.exe and POSIX shells alike); the record keeps the command as written and what ran (`ran`). Two P1-10 audit
  units were judged "not ok" because the shell split it (exit 4).
