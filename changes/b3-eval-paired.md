- `scripts/eval/r5.py` (B3 eval, report-only; ccx itself unchanged): the B3 rule's median is now the true median
  (`statistics.median`; m1h2 must be re-summarized, its earlier median was the upper middle), and `b3_rules` adds
  paired statistics next to the registered rule: share of pairs lower, per-pair ratio median, total ratio, seeded
  pair- and task-cluster bootstrap 95% CIs of the ratio of medians and `token_effect` (consistent / not shown). Pairs
  whose units ran on different daily snapshots are left out and listed, and any such pair turns a pass into Unknown.
  `summary` / `export` read several `--results` files and `--tag` more than once. `run` freezes the daily setup once
  per invocation, adds `--arm-order balanced` (a Williams design, base-first counts in `--dry-run`; `shuffle` stays
  the default), records `switches_applied` per ccx run (derived Codex flags: run.json has no argv), keeps
  `hidden_failed`, the hidden pytest output and the byte-exact final diff of every unit that is not right, and lists
  new real hub ledger rows with whether they belong to a unit.
