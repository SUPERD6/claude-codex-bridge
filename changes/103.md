- `--review auto` now judges weak evidence from the run itself, with no history needed: a write run that changed
  code is reviewed once (on the other vendors' cheapest rung only, within `weak_daily`) when there is no `--check`,
  when the check runs no tests (`exit 0`, a linter, an import), or when the tests it runs never name a changed code
  file or a changed public function. A passed check whose tests reach the change is not reviewed, nor are read-only
  runs. Round 2 of the seven-cores A/B: auto fired 0 times in 36 runs, while review on raised right first time from
  33/36 to 36/36 for +$0.004 a task; replaying the 18 trap tasks' reference changes, the new rule fires on 4,
  inventory among them (its visible test never calls `low_stock` or `remove_stock`).
