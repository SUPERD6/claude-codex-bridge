- `scripts/eval/r5.py` (eval only): six fixes found while checking the B3 result. `run --wait-quiet MINUTES` waits
  for other heavy work on the machine to finish, before the checks and between units (two quiet checks in a row after
  a busy spell; recorded in `preflight.json`), instead of running on with `--force-unclean`; the unit that overlapped
  that work stays not env_clean. Each run keeps its evidence in its own `<results>-artifacts/<UTC start>Z/` folder
  (`artifacts.run` in the row), apart from an aborted run's. `sub_usage` sums the sub-agents' `requests` from the
  ledger (`sub_req=` in the run log, with how many runs said). Pairs left out as not env_clean are said even when both
  sides lost alike, and a B3 rule on fewer pairs than the 50 registered prints "registered 50 pairs, counted N"
  (report-only, results unchanged). `--include-unclean` help says neither rule counts those rows. The B3 plan gets an
  amendment: its "2–3 pairs lost" clause was not a second threshold, and its 50 extra units were not run.
