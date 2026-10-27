- F14 default change: the "explicitly asked to use sub-agents" words are added only with `--parallel`, no longer
  when a brief lists 3 or more items (round 5: 40/100 first runs got them, +$0.007-0.024 a run, no wall gain).
- The sub-task prompt says that delegation / acceptance instructions written for the lead in the shared context
  were already carried out: the sub-agent is the implementer (only for a write run with the shared-context block;
  not ccx's read-only reviewer or read tasks). The shared context for a delegated task also drops a clause only
  when the whole clause is the hand-off ("Do not edit files yourself", "hand the implementation to a sub-agent
  through ccx", ...); specs about delegation itself stay. The block says how many were left out and the run
  record lists them (`shared_context.lead_only_dropped`).
- A resume or review fix round of a write run inherits its chain's undo snapshot: reviewing after resuming a fix
  run sees the whole change, and `ccx undo` of any run in the chain puts back what the chain changed (the output
  says so). Only while nothing changed between the links: after a commit or an edit by the lead, or for a board
  message answered in the session, the run takes its own snapshot, so undo keeps the lead's work.
- `ccx run --parallel` help text no longer says the words are added by themselves for 3+ listed items.
- `edited_tests` (changed pre-existing tests) is shown for every write run, also with `--review off`.
- `[review] cache_ttl` (default off): "5m" or "1h" sets Claude Code's `promptCacheTtl` for ccx's Claude reviewer
  only.
