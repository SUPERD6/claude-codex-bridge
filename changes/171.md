- `ccx q accept <id...>` (or `--all-ready`) lands the pieces a `ccx q run` left on worktree branches: it merges them
  one at a time in dependency order into the branch the project has checked out, runs the joint check (`--check`,
  else each piece's own) after each merge and rolls that merge back when it fails. A merged piece gets the lead's
  verdict, as `ccx q done --ok 1`, and a `q_accept` ledger row. Pieces that are not done (running, failed,
  no_changes, review failed), whose review is still running, that have no evidence (no passed check, review or
  verdict, and no `--check` here) or that wait on a piece not accepted are refused, each with the reason. A conflict
  aborts that merge and skips what waits on it; the other pieces still land. A run you rejected (`ccx verify --ok 0`)
  is refused, even with `--check`. When a rollback does not go through, or the joint check leaves edits in tracked
  files, the batch stops and nothing more is merged on top. A worktree piece given `ccx q done --ok 1` before its
  branch was merged still shows as `unmerged` and can be accepted (`q done` says so). It never pushes and never merges into
  main or another protected branch without `--into-protected`. `--dry-run` shows the plan. The merge steps of
  `ccx autonomy merge` are now shared helpers (its behaviour is unchanged).
- `ccx q ls` prints one line per piece by default (id, state, agent, seconds, $, then what to do next). A worktree
  piece that has not landed shows as `unmerged` with `next: ccx q accept qN`. `--long` prints the old JSON (anything parsing `ccx q ls` as JSON must add `--long`). The
  `q run` summary points `unmerged` / `waiting` pieces at `ccx q accept`.
- `ccx q add --dep 1` means q1 (before, a bare number was an unknown dependency). `ccx q done` takes several ids;
  with `--ok 1`, each needs a passed check or review of its own, or a `--note "<id>: ..."`.
- skills/agent-delegate: a short pipeline section. Hand off independent pieces with `ccx q`, collect them with
  `ccx show --any --wait`, and land finished ones in dependency order with `ccx q accept` while the others run.
