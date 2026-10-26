- Whole-workflow tiers on `--tradeoff`: `save | balanced | fast | cheapest` (new value `cheapest`). task-routing
  `tier_plan` (CLI `task_routing.py tier`) sizes a task from the brief plus `--minutes` / `--files` (any one signal
  is enough; state-machine words match whole words, with plain endings) and says who does it: `self`, `ccx2` (delegated, the lead
  accepts; models picked like save) or `direct` (cheapest: nobody re-checks, `may_be_wrong`). Provisional thresholds
  and per-tier rules in `config/tiers.toml [policy.*]`; a knob 0..1 maps onto save/balanced/fast. `ccx propose` /
  `ccx route` show it under `tier` / `policy`.
- New setting `policy.picked` (`ccx config set policy.picked save|balanced|fast|cheapest|none`, shipped none): the
  tier the person picks. Only it pre-authorises: `ccx propose` for that tier returns `authorized: true` with
  `worth_offering: true` and a `say` line (proposal row `preauthorized`); that proposal's run skips the random A/B
  self-run, keeps the proposal's tier in the ledger, and is refused if the setting changed; project autonomy L0/L1
  still asks before edits; `proposals.stats` leaves tier-decided proposals out of the H12 chain (`tier_decided`). A
  `--tradeoff` the lead passes authorises nothing (offer-first, A/B and the H11 trial as before). Default tier stays
  `save`. The agent-delegate and task-routing skills say what to do with `authorized: true`.
- A bad `[policy.*]` entry: `ccx propose` falls back to offer-first and shows `tier.error`; `ccx doctor` has a
  `tier policy` row.
- Ledger: run and proposal rows carry `policy_tier`, `band`, `planned_mode`, `tier_explicit`, `estimate_minutes`;
  run rows also `actual_mode` and `resume_chain` (follow-ups of the same task: `ccx resume`, review fix rounds, an
  interrupted run resumed; a board message answered in the session is not one); a proposal answer records
  `actual_mode` and, for a pre-authorised run, `source: tier`.
- `review_failed`: the hint now tells the lead to check the [must] items and fix the real ones itself
  (`ccx/prompts.py` `REVIEW_FAILED`); `ccx resume` is the last resort.
- `ccx turn` reads the hook's stdin as UTF-8 bytes, BOM dropped (a Chinese prompt on a GBK console was garbled).
- `--tradeoff` help no longer says "initially balanced"; `ccx config set defaults.tradeoff cheapest` is accepted.
