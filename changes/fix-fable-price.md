- Fable has a price: `[prices.fable]` in the task-routing priors ($10 input, $50 output, cache reads $0.25 per 1M
  tokens; cache-write multipliers as for the other Claude models), and `fable`, `claude-fable-5-1` and
  `claude-fable-5` map to it. Before, a Fable lead or run had none: `ccx lead --breakdown/--cache` showed $0 for it
  and the ledger showed its cost as unknown. Source: the Claude API model table bundled with Claude Code 2.1.309
  (cached 2026-10-06); verify against the pricing page before relying on it.
