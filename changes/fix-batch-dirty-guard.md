- `ccx batch` with uncommitted changes: parallel writers no longer get worktrees made from the last commit (which
  lacked those changes); like `ccx q run`, they share the project folder and the output lists them under
  `shared_folder` with "commit first". Clean repos are unchanged; the plan file itself does not count; `--lanes`
  too. The git check moved to `ccx/gitstate.py`, shared by both.
