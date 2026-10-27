- New batch / pipeline throughput eval (`scripts/eval/batch.py`, opt-in, its own results file; r5 and its arms,
  schedule, done-keys and rows are unchanged), planned in `docs/research/2026-10-27-batch-plan.md`: one lead session
  gets several hold-out changes at once, put on one common start (`scripts/eval/batch_start.py`: the first commit
  that has all of them, every batch commit reverted on it with git's three-way revert; a code or test conflict drops
  that change and says so). `batch.py check` builds and checks each batch (holdout_check's band and leakage checks,
  hidden nodes that fail at the start and pass at the end, none of them in the start's test files word for word, the
  start imports, the declared same-file overlap and end). Batches (`scripts/eval/tasks_batch.py`): five changes of
  this repository with one deliberate same-file overlap, its largest conflict-free variant (four: no five-change set
  is both revertible on one start and conflict-free), humanize's four (one overlap) and three (none); itsdangerous's
  two candidates cannot share a start. Arms `self`, `builtin` (parallel workers allowed), `ccx-batch`,
  `ccx-pipeline` (`q add --plan`, `q run --bg`, `show <ids> --any --wait`, merge `waiting` / `unmerged`, `q done`)
  and `balanced`; `--lead-model` / `--lead-effort` as r5 (default opus medium). Per unit: wall, lead and sub-agent
  $, hidden tests on the final merged tree (per change and all-right, with regressions), merge conflicts and markers
  left, the lead's turns, requests, tokens, wake-ups and idle ratio (from line arrival times), quota events (every
  ccx attempt, not only the last); round 5's clean room, fingerprint and audit. `run --dry-run` prints the plan and a
  cost estimate (a projection, about $27 for four batches x five arms x two repeats); the summary gives median / p90
  wall per batch and arm and plain paired per-batch numbers with n (no bootstrap). No paid run yet.
