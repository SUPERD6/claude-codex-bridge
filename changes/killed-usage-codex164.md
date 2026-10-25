- A Codex attempt stopped mid-run is now counted from the per-request `token_usage_record` lines codex-cli 0.164
  writes to its session file (since the attempt began), falling back to the growth of its `token_count` total.
  Found by a real `ccx stop` (run `20261025-101228-1108`, gpt-6-luna low, stopped after 7.6 s during its first
  request): the request's 19,245 input and 207 output tokens were only in a `token_usage_record`, so the attempt
  was counted as 0. A read-back attempt is marked `recovered` and is never taken as the session's running total,
  so a later `ccx resume` counts its own turn in full.
