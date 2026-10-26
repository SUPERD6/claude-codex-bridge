- Evaluation: a hold-out task set (`scripts/eval/tasks_holdout.py`), 10 real past changes of this repository that
  were never used while tuning on round 5 (other commits, other feature areas, same size band: 13-86 changed lines,
  1-4 files, one hidden test file each). `scripts/eval/r5.py run --taskset holdout` runs it (results in their own
  file, the task file's hash in every row); r5 stays the default. `scripts/eval/holdout_check.py` checks every task:
  the hidden test fails at the parent and passes at the commit, size in band, nothing shared with r5.
- Evaluation: a task may `deselect` unrelated tests that fail at random under load (test_bg_run in two hold-out
  tasks); hold-out units leave nothing in the work dir after scoring (repository and hub removed, the lead stream
  moved to `.ccx/eval/r5/streams/<tag>/`), so a later round cannot find an earlier round's answer; the checkout's
  other git worktrees are denied to unit agents and flagged by the audit like the checkout itself.
