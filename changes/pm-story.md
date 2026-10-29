- report / ui / stats: the saving estimate prices only the task-sized part of the sub-agent's tokens (fresh input
  and output, not its start-up and re-reading) at the lead's price; the old figure is kept as `saving_upper`, an
  upper bound. `ccx ui` ("Is it worth it"), `ccx report` and `ccx stats --summary` show the spend first and the
  estimate after it, labelled "model estimate; measured totals so far about even" with a link to docs/measured.md;
  `ccx stats --summary` gains `spend` and `saving` (the old `totals` keys stay). `ccx -h` no longer promises savings.
- run: a write run with no `--check` prints one reminder line on stderr; stdout and what ccx does are unchanged.
- docs: the README's first screen is the one job (a checkable chore from Claude Code to Codex on a cheaper model)
  with a self / built-in sub-agent / ccx table of round-5 dev-set ranges (hold-out pending) and a quick start with
  `--check`; the four best-case numbers moved to docs/measured.md. The FAQ compares with Claude Code's built-in
  sub-agent and no longer contradicts `ccx discuss` / `ccx send`; the plugin marketplace says five skills.
