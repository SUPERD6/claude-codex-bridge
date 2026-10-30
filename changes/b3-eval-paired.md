- `scripts/eval/r5.py` (B3 eval, report-only; ccx itself unchanged): the B3 rule's median is now the true median
  (`statistics.median`), and `b3_rules` adds paired statistics next to the unchanged rule: share of pairs lower, per-pair
  ratio median, total ratio, a seeded pair-bootstrap 95% CI of the ratio of medians and `token_effect` (consistent /
  not shown). Pairs whose units ran on different daily snapshots are left out and listed. `summary` / `export` read
  several `--results` files and `--tag` more than once. `run` freezes the daily setup once per invocation, adds
  `--arm-order balanced` (Latin-square rotation; `shuffle` stays the default), records `switches_applied` per ccx run
  (derived Codex flags: run.json has no argv), keeps `hidden_failed`, the hidden pytest output and the final diff of
  every unit that is not right, and lists new real hub ledger rows with whether they belong to a unit.
