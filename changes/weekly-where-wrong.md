- H14, a weekly "where it was wrong" in `ccx report` (`ccx/accuracy.py`), this week next to last week: per agent ×
  tier × kind of work the share of judged pieces that were wrong and that needed rework; routing's prediction `p`
  against what happened (Brier score and binned calibration; right = judged right and done by the rung routing
  picked); how many probable verdicts were overturned later; and the acceptance commands that let wrong work through
  (J7). Evaluation runs are left out (`ledger.is_eval`); `ccx report --include-evals` counts them. `ways.pieces` rows
  now carry `ts`, `p`, `attempts` and `ok`.
