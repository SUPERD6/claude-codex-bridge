- `bench/`: a public benchmark anyone can re-run. One file per task for the hold-out set (hc1, 10 tasks) and the r5
  dev set (10 tasks), written from `scripts/eval/tasks_holdout.py` / `tasks_r5.py` by `bench/make_tasks.py`
  (external tasks are pointers only: URL, commit, test path); `bench/run.py run` wraps `scripts/eval/r5.py` with few
  options (`--set`, `--arm self|ccx|builtin`, `--tasks`) and `bench/run.py table` prints the README's table for any
  results file; the published hc1 and r5 rows, scrubbed by `r5.py export`, are in `bench/results/`. The README says
  plainly that the hold-out set stops being one once published, and that the next headline needs a new one.
  `tests/test_bench.py` checks the task files against the task sets, the rows for personal data, and that the table
  still gives the published numbers. No command or option changed; `scripts/eval/` and `ccx/` untouched.
