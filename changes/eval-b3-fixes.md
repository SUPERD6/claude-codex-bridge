- `scripts/eval/r5.py` (eval only): six fixes found while checking the B3 result. `run --wait-quiet MINUTES` waits
  for other heavy work on the machine to finish before the checks (instead of `--force-unclean` past a busy one);
  each run keeps its evidence in `<results>-artifacts/<start time>/` (`artifacts.run` in the row), apart from an
  aborted run's; `sub_usage` sums the sub-agents' `requests` from the ledger (`sub_req=` in the run log); pairs left
  out as not env_clean are said even when both sides lost alike, and a B3 rule on fewer pairs than the 50 registered
  prints "registered 50 pairs, counted N" (report-only, results unchanged); `--include-unclean` help says neither
  rule counts those rows. The B3 plan says the "2–3 pairs lost" edge was not a second threshold.
