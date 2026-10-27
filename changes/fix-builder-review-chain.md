- F14 default change: the "explicitly asked to use sub-agents" words are added only with `--parallel`, no longer
  when a brief lists 3 or more items (round 5: 40/100 first runs got them, +$0.007-0.024 a run, no wall gain).
- The sub-task prompt says that delegation / acceptance instructions written for the lead in the shared context
  were already carried out: the sub-agent is the implementer. The shared context for a delegated task also drops
  the few sentences that only name the hand-off ("do not edit files yourself", "hand ... through ccx", ...).
- A resume or review fix round of a write run inherits its chain's undo snapshot: reviewing after resuming a fix
  run sees the whole change, and `ccx undo` of any run in the chain puts back what the chain changed.
- `edited_tests` (changed pre-existing tests) is shown for every write run, also with `--review off`.
- `[review] cache_ttl` (default off): "5m" or "1h" sets Claude Code's `promptCacheTtl` for ccx's Claude reviewer
  only.
