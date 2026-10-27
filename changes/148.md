- New batch / pipeline throughput eval (`scripts/eval/batch.py`, opt-in, its own results file; r5 and its arms,
  schedule, done-keys and rows are unchanged), planned in `docs/research/2026-10-27-batch-plan.md`: one lead session
  gets several hold-out changes at once, put on one common start (`scripts/eval/batch_start.py`: the first commit
  that has all of them, every batch commit reverted on it with git's three-way revert; a code or test conflict drops
  that change and says so). `batch.py check` builds and checks each batch (holdout_check's band and leakage checks,
  hidden nodes that fail at the start and pass at the end, none of them in the start's test files word for word, the
  start imports, the declared same-file overlap and end). Batches (`scripts/eval/tasks_batch.py`): five changes of
  this repository with one deliberate same-file overlap, its largest conflict-free variant (four: no five-change set
  is both revertible on one start and conflict-free), humanize's four (one overlap) and three (none; neither humanize batch checked
  yet); itsdangerous has no batch (its two candidates' revert conflicted on an earlier try, not re-run). Arms `self`, `builtin` (parallel workers allowed), `ccx-batch`,
  `ccx-pipeline` (`q add --plan`, `q run --bg`, `show <ids> --any --wait`, merge `waiting` / `unmerged`, `q done`)
  and `balanced`; `--lead-model` / `--lead-effort` as r5 (default opus medium). Per unit: wall, lead and sub-agent
  $, hidden tests on the final merged tree (per change and all-right, with regressions), merge conflicts and markers
  left, the lead's turns, requests, tokens, wake-ups and idle ratio (from line arrival times), quota events (every
  ccx attempt, not only the last); round 5's clean room, fingerprint and audit. `run --dry-run` prints the plan and a
  cost estimate (a projection, about $27 for four batches x five arms x two repeats); the summary gives median / p90
  wall per batch and arm and plain paired per-batch numbers with n (no bootstrap). No paid run yet.
- Batch eval fixes after review: hidden test files run with `--continue-on-collection-errors`, so a file that does
  not import (at the start, or a change the lead left out) fails only its own nodes instead of the whole session
  (the first check's empty `start_passed` and false `coupled` came from this; collection errors of every run are
  recorded); the start's commits get a fixed date and a cached check is keyed on the start tree and on the check
  code (`batch_start.py`, `batch.py`), so `run` can reuse it; `without_one`'s cherry-pick fallback settles
  documentation-only conflicts as `revert_all` does; a merge conflict counts once per `CONFLICT` line; review runs
  (label `review:`) are left out of `delegated`; builtin's sub-agent $ is not split when the lead runs on the
  worker's model, and every row keeps the worker model's share as `lead_worker_model_usd`.
