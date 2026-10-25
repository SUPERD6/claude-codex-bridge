- `ccx discuss --dry-run` estimates turn by turn: the price of each agent's model at `--tier` × (the CLI's start-up
  overhead + question + context + the points passed so far), for the longest talk (`usd_max_est`: every round, then
  the judge) and the shortest (`usd_min_est`: agreement in round 1). Earlier discuss turns on the same rung
  (agent:model:effort) in the ledger replace the model. It also says which model each agent will use (`models`) and
  where each number comes from (`basis`). The old estimate averaged all recent read runs and said $0.036 for a talk
  that cost $0.283 (discuss-r1); replayed on the same inputs the new one says $0.17–0.40.
- `ccx discuss` names the model for every turn, so a provider such as `deepseek` (no row in the tier table) can take
  part: it runs on its own model instead of failing with "tier T2 has no deepseek model".
