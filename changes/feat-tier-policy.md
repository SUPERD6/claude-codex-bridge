- Whole-workflow tiers on `--tradeoff`: `save | balanced | fast | cheapest` (new value `cheapest`). task-routing
  `tier_plan` (CLI `task_routing.py tier`) sizes a task from the brief plus `--minutes` / `--files` (any one signal
  is enough; state-machine words match whole words, with plain endings) and says who does it: `self`, `ccx2` (delegated, the lead
  accepts; models picked like save) or `direct` (cheapest: nobody re-checks, `may_be_wrong`). Provisional thresholds
  and per-tier rules in `config/tiers.toml [policy.*]`; a knob 0..1 maps onto save/balanced/fast. `ccx propose` /
  `ccx route` show it under `tier` / `policy`.
- New setting `policy.picked` (`ccx config set policy.picked save|balanced|fast|cheapest|none`, shipped none): the
  tier the person picks. Only it pre-authorises: `ccx propose` for that tier returns `authorized: true` with
  `worth_offering: true` and a `say` line (proposal row `preauthorized`); that proposal's run skips the random A/B
  self-run, keeps the proposal's tier in the ledger, and is refused if the setting changed. A pre-authorisation
  covers one run of that task: a second run with the same id (claimed atomically when the run starts), a run
  sized smaller than the proposal, or a run whose own brief the tier would plan `self` (its hard / uncertain rules)
  is refused; with `--bg` the refusal comes before detaching (a refused detached child leaves a finished `refused`
  record, so `ccx show --wait` ends);
  its answer (`source: tier`) is written only when the run starts (an L0/L1 stop or a routing refusal records
  nothing). Project autonomy L0/L1 still asks before edits; a proposal the picked tier planned `self` is not an
  approval for it either (sent out anyway, its answer is `source: lead`). `policy.picked` sets the tier plan, not the
  models: a plain run still picks models by `--tradeoff` / `defaults.tradeoff`; `proposals.stats` leaves tier-decided proposals out of the H12 chain (`tier_decided`). A
  `--tradeoff` the lead passes authorises nothing (offer-first, A/B and the H11 trial as before). Default tier stays
  `save`. The agent-delegate and task-routing skills say what to do with `authorized: true`.
- A bad `[policy.*]` entry: `ccx propose` falls back to offer-first and shows `tier.error`; `ccx doctor` has a
  `tier policy` row (it reads `policy.picked` as routing does, case-insensitive).
- Ledger: run and proposal rows carry `policy_tier`, `band`, `planned_mode`, `tier_explicit`, `estimate_minutes`;
  a pre-authorised proposal's run has its own band and estimate plus `proposal_band`; run rows also `actual_mode`
  and `resume_chain` (follow-ups of the same task: `ccx resume`, review fix rounds, an
  interrupted run resumed; a board message answered in the session is not one); a proposal answer records
  `actual_mode` and, for a pre-authorised run, `source: tier`.
- `ccx turn` reads the hook's stdin as UTF-8 bytes, BOM dropped (a Chinese prompt on a GBK console was garbled).
- `--tradeoff` help no longer says "initially balanced"; `ccx config set defaults.tradeoff cheapest` is accepted.
