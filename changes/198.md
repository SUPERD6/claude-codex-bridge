- Fable 5.1 has a price: `[prices.fable]` in the task-routing priors ($10 input, $50 output, cache reads $0.25 per
  1M tokens; cache-write multipliers as for the other Claude models, not checked for Fable), and `fable` and
  `claude-fable-5-1` map to it. Before, a Fable run had none: its cost in the ledger and the prices in
  `ccx lead --breakdown/--cache` came out unknown or $0. Fable 5 (`claude-fable-5`) stays unpriced (its cache-read
  price is not known here), and `ccx lead` suggestions still do not list Fable as a lead model. Source: the Claude
  API model table bundled with Claude Code 2.1.309 (cached 2026-10-06); verify against the pricing page.
  Hubs with their own copy of the task-routing skill get it after `ccx skills install`.
