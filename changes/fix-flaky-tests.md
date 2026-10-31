- Writers that start side by side (`ccx q run`, `ccx batch`) no longer fail now and then while getting their
  worktrees: `git worktree add` reads every worktree already registered, and one that another `worktree add` was
  still creating has no `commondir` yet, so git stopped with "failed to read .git/worktrees/<name>/commondir"
  (seen on Windows CI: the second writer of a `q run` came out `failed`). Threads of one ccx now add their
  worktrees one at a time; against another ccx process the same error undoes this run's half-made branch and tries
  again (up to 3 times). Tests: `tests/test_worktree_race.py`; the queue end-to-end test now prints why a piece
  failed.
- Test fix: `tests/test_ui_tokens.py` period test used "now - 60 s" as a run of today, which is yesterday in the
  first minute after midnight; it now uses one fixed time for the records and the queries.
