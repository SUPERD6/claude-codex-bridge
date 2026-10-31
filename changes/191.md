- B3 ruler (`ccx/reqstats.py`, display and accounting only): a Claude or Codex sub-agent attempt now records how
  many requests its own conversation made and the input of each one (Claude: its stream's assistant messages, once
  per message id, Agent-tool helpers left out by `parent_tool_use_id`; Codex: the session's `token_usage_record`
  lines since the attempt began, codex-cli 0.164; children write their own files), as `requests`, `first_input` (a
  fresh session's first request: the start-up prefix), `input_per_request`, `prefix_tokens` (median) and
  `request_inputs` in run.json; the ledger row carries `requests`, `prefix_tokens` (mean a request) and
  `first_input`. `ccx ui`'s "Measured & where tokens go" page shows them on each run's line and per agent; older rows
  and gemini / dsh runs show nothing. Nothing a sub-agent is told or started with changes.
