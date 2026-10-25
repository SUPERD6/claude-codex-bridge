- `ccx autonomy` (K4): how much the project manager does without asking. L0 only proposes (`ccx run --project`
  answers with a `plan`: agent, model, mode, `expected_usd`), L1 (the default) dispatches read-only runs and stops
  before a run that may edit files, L2 dispatches both and merges a small `--worktree` branch whose check passed and
  whose review said pass into the project's working branch, only where the person allowed it for that project
  (`ccx autonomy set L2 --project NAME --auto-merge on`) and never into `main` or another protected branch.
  `ccx run --approved` passes an L0/L1 stop after the person said yes; `--autonomy L?` sets one run's level; a
  project's own `.ccx/autonomy.toml` can only lower it. `[autonomy]` in `config/tiers.toml`, `autonomy.level` in
  `ccx config set`; the project-manager skill's section 6 follows the level.
