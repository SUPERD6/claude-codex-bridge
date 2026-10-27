- Round-5 evaluation, for the confirmation run (all opt-in; the default schedule, arms and done-keys of old tags are
  unchanged): `--lead-model` / `--lead-effort` (default sonnet medium) recorded in every row, its fingerprint and its
  done-key, with another lead's units summarised as their own arm (`ccx2@opus-high`); an opt-in arm `builtin2r`
  (builtin2 whose worker prompt also carries ccx's KEEP_TESTS and WIRING rules, imported from `ccx/prompts.py`), so
  ccx2 vs builtin2r isolates ccx from those rules; the summary pairs every two arms on shared units (McNemar exact p
  with Holm over the pairs, task-level bootstrap 95% CIs of the cost-per-success and wall-median differences), adds a
  Wilson CI and the right count per round per arm, the wall per phase of units that used ccx (sub-agent attempts,
  checks, reviews, fix rounds, the lead waiting; median and p75) and, with arms `balanced` and `save`, the tier
  decision rule (pass / fail per condition). `--budget` now counts only the tag's own spend (plus `--extra-spent`);
  each unit line and the end of a run print the run, tag and file totals.
