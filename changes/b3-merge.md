- `ccx batch --merge` (experimental, off by default; `[merge]` in tiers.toml, `ccx/merge.py`): small independent
  pieces of one batch that share folder, agent, model rung and mode, each at most 5 minutes and with no declared
  path (`paths`) in common, run as one run (up to 5 pieces, 15 minutes), never escalated and without sub-agents of
  its own. Each piece keeps its own check (run by ccx afterwards), its own entry in `results` (`merged_run`,
  `merged_with`) and `ccx undo <run> --piece <id>` for the paths it declared; failed pieces get one follow-up in the
  same session, then a run of their own on the usual ladder. Without the flag `ccx batch` is unchanged. Measured
  next in M4 (`.ccx` B3 plan): until then it stays off.
