- Warm lanes, off by default: `ccx batch --lanes N` and `ccx q run --lanes N` (`[lanes] default = 0`) cut pieces for
  the same project, agent and read/write mode into at most N lanes; a lane's first piece starts a sub-session and each
  later one continues it as a new task, while lanes run side by side. Each piece stays its own ccx run (own `--check`,
  ledger row, undo snapshot; one commit per piece in a worktree). A piece that does not finish cleanly, a piece that
  used more than `[lanes] max_tokens` (200k), or `max_blocks` (5) pieces hand the next piece a fresh session.
  Measured on round 2's ten small modules (`scripts/eval/warm_lanes.py`, n = 2, Codex luna low): ~40% cheaper than
  one fresh run per piece but not fewer tokens and slower; one run doing all ten is cheaper still
  (docs/research/2026-10-25-warm-lanes.md).
