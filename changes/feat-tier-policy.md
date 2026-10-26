- Whole-workflow tiers on `--tradeoff`: `save | balanced | fast | cheapest` (new value `cheapest`). task-routing
  `tier_plan` (CLI `task_routing.py tier`) sizes a task from the brief plus `--minutes` / `--files` and says who does
  it: `self`, `ccx2` (delegated, the lead accepts; models picked like save) or `direct` (cheapest: nobody re-checks,
  `may_be_wrong`). Provisional thresholds and per-tier rules in `config/tiers.toml [policy.*]`; a knob 0..1 maps onto
  save/balanced/fast. `ccx propose` / `ccx route` show it under `tier` / `policy`; an explicitly given `--tradeoff`
  pre-authorises the tier's delegation (`authorized: true`) and skips the random A/B self-run. Without a tier
  nothing changes (offer-first). Default tier stays `save`.
- Ledger: run and proposal rows carry `policy_tier`, `band`, `planned_mode`, `tier_explicit`, `estimate_minutes`;
  run rows also `actual_mode` and `resume_chain` (run records count `ccx resume` links); a proposal answer records
  `actual_mode`.
- `review_failed`: the hint now tells the lead to check the [must] items and fix the real ones itself
  (`ccx/prompts.py` `REVIEW_FAILED`); `ccx resume` is the last resort.
- `ccx turn` reads the hook's stdin as UTF-8 bytes (a Chinese prompt on a GBK console was garbled).
- `--tradeoff` help no longer says "initially balanced"; `ccx config set defaults.tradeoff cheapest` is accepted.
