- H9 statistics without evaluations: `ccx way --stats` (and the builder order `ccx way` uses) leave evaluation runs
  out (`ledger.is_eval`: label `eval-...`, `--no-ab`, ccx's own probes); `--include-evals` counts them. Each agent's
  rates are also split by tier (`tiers`, by the model:effort that finished the piece), so a cheap tier's misses are
  seen apart from the strong one's. On the maintainer's hub (30 days, code) the seven-cores A/B had made codex 116
  judged pieces at 71% first-time-right and claude 51; real use alone is codex 9 at 78% and claude 4.
