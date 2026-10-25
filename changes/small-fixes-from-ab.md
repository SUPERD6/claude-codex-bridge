- Two small fixes from the seven-cores A/B (PR #30): the spend-cap message shows amounts below a cent with four
  places (a $0.0001 cap read "spent $0.00 (cap $0.00)"); agent-delegate tells the lead that a printed result with a
  `run_id` means the delegation ran, so it must not send the same brief again (a real Codex lead did, after a run
  that had already passed) and should use `ccx resume <run_id>` to add to it.
