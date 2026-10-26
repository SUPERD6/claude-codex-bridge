- `ccx show <run_id> --wait [SECONDS]` (default 540, under a 10-minute tool-call limit) blocks until the run is
  finished and prints the same compact result as `ccx run`, recap line included; when the run started a review fix
  round it waits for that and reports the last run of the chain. Still running at the end: `status: running` and
  `next: ccx show <id> --wait`, exit 0. `ccx run --bg` and the "still working" refusal of `ccx resume` point to it:
  a lead whose Bash call timed out lost the result and resumed mid fix round (round 5).
- The compact result of a write run in a git repo has a `diffstat` line (`git diff --shortstat` since the run's
  undo snapshot, plus new untracked files), so the lead needs no `git diff` / `git status` of its own after each
  run (round 5). No git or no snapshot: the key is left out.
