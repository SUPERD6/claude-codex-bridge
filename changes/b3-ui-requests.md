- B3 ruler (`ccx/reqstats.py`, display and accounting only): every sub-agent attempt now records how many requests
  it made and the input of each one (Claude: its stream's assistant messages, once per message id; Codex: the
  session's `token_usage_record` lines since the attempt began, codex-cli 0.164), as `requests`, `prefix_tokens`
  (median) and `request_inputs` in run.json; the ledger row carries `requests` and `prefix_tokens`. `ccx ui`'s
  "Measured & where tokens go" page shows them on each run's line and per agent (mean requests a run, median prefix,
  how many runs recorded it); older rows show nothing. Nothing a sub-agent is told or started with changes.
