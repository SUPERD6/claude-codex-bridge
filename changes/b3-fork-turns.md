- `[subagents] fork_turns` (experimental, default `"all"` = unchanged): `"none"` adds one sentence to a `--parallel`
  Codex piece's brief asking it to start its own sub-agents with `spawn_agent(fork_turns="none")` and a self-contained
  message, so children stop re-reading the parent's history on each request (codex-cli 0.164.0 parameter). Claude
  pieces, runs without `--parallel` and `--subagents off` are untouched; run.json records `parallel_fork_turns`.
  Off until measurement M3.
