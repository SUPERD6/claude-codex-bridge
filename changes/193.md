- Writers that start side by side (`ccx q run`, `ccx batch`) no longer fail now and then while getting their
  worktrees: `git worktree add` reads every worktree already registered, and one that another `worktree add` was
  still creating has no `commondir` yet, so git stopped with "failed to read .git/worktrees/<name>/commondir"
  (seen on Windows CI: the second writer of a `q run` came out `failed`). Threads of one ccx now add their
  worktrees one at a time (one lock per repository, its linked worktrees included). Against another ccx process
  (e.g. `ccx run --bg --worktree` side by side) only a retry helps: the same error, known by its path in any
  language, is tried again up to 3 times on the branch git already made. Tests: `tests/test_worktree_race.py`; the
  queue end-to-end test now prints why a piece failed.
- Test fix: `tests/test_ui_tokens.py` period test used "now - 60 s" as a run of today, which is yesterday in the
  first minute after midnight; it now uses one fixed time for the records and the queries.
