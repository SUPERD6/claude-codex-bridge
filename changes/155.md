- `ccx batch` with uncommitted changes: parallel writers no longer get worktrees made from the last commit (which
  lacked those changes); like `ccx q run`, they share the project folder and the output lists them under
  `shared_folder` with "commit first" and "keep pieces on separate files" (their checks, reviews and undo can see
  each other's edits). Clean repos are unchanged; the plan file itself does not count, also with a non-ASCII name
  (git status is read with `-z`, so quoted names and renames are parsed right); `--lanes` too. A task that sets
  `"worktree": true` in a dirty project keeps its worktree and is listed under `stale_base`. The git check moved to
  `ccx/gitstate.py`, shared by both.
