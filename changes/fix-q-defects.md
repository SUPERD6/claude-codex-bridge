- `ccx q` for batches of pieces: parallel writers in a git project get one worktree each (the `ccx batch` rule, one
  commit per piece on `ccx/<run>`), and what depends on such a piece waits for your merge + `ccx q done <id> --ok 1`
  (listed under `waiting`); `q add --plan` reads task-split's `pieces` / `depends_on` / `files`, resolves
  dependencies after every id exists and errors on an unknown id or a cycle (they were dropped silently); a failed
  dependency marks its dependents `dep_blocked` instead of leaving them todo forever (back to todo once settled);
  items naming a common file never run in the same round; new `q run --gate` (off by default) makes every dependent
  wait for your verdict.
- `ccx run --bg` refused by routing writes a finished record (kind `not_delegated`), so `ccx show <id> --wait`
  returns at once instead of waiting out its timeout.
