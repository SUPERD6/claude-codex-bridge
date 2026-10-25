- J7 spot checks: `ccx verify --sample N` picks N random probable verdicts (soft) of this week that nobody judged
  since, shows what each run changed (summary, files, check or self-check, why it was judged), and asks ok / wrong /
  skip; an answer is your verdict (`ccx verify`), so it teaches routing and feeds `ledger.soft_trust`. Without a
  terminal, or with `--list`, it prints the picks as JSON. Evaluation runs are left out unless `--include-evals`.
