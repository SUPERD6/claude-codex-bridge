- `ccx q` for batches of pieces: parallel writers in a git project with no uncommitted change get one worktree each
  (the `ccx batch` rule, one commit per piece on `ccx/<run>`; otherwise they share the folder as before, noted under
  `shared_folder`), and what depends on such a piece waits for your merge + `ccx q done <id> --ok 1` (listed under
  `waiting`; branches nothing waits on under `unmerged`); `q add --plan` reads task-split's `pieces` / `depends_on` /
  `files`, resolves dependencies after every id exists and errors on an unknown id or a cycle (they were dropped
  silently); a failed, blocked or needs_write dependency marks its dependents `dep_blocked` (naming the piece to fix)
  instead of leaving them todo forever (back to todo once settled; `q ls` / `tree` only show it); a task-split piece
  without a brief gets one built from the plan and runs in the mode its own title implies (the split hint made it
  read-only); items naming a common file never run side by side; new `q run --gate` / `q ls --gate` (off by
  default) makes every dependent wait for your verdict; `ccx ui` shows `dep_blocked` pieces as needing a decision.
- `ccx run --bg` refused by routing writes a finished record (kind `not_delegated`), so `ccx show <id> --wait`
  returns at once instead of waiting out its timeout.
