- `ccx batch --merge` (experimental, off by default; `--no-merge`, `[merge]` in tiers.toml, `ccx/merge.py`): small
  write pieces of one batch (same folder, agent, model rung or tier, worktree and namecheck; each with `minutes` <= 5;
  no common declared `paths`) run as one run of up to 5 pieces / 15 minutes, never escalated and without sub-agents
  of its own. Each piece is judged on its own (its check, else its own `[id] done|partial|failed` summary line, else
  `unconfirmed`), keeps its own entry in `results` (`merged_run`, `merged_with`, `piece_state`) and `ccx undo <run>
  --piece <id>` for its paths. Pieces not done get one follow-up in the same session, then a run of their own on the
  usual ladder; after a quota / login / stop / timeout nothing more starts (`not_run`). Follow-up and spun-off runs
  record `merge_of` (run.json and ledger) and a `merge` ledger event lists each piece's outcome. Without the flag
  `ccx batch` is unchanged. Off until measurement M4.
