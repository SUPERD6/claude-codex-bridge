- B3 result report (docs/research/2026-10-31-b3-lean-switches, both languages): the three `[subagent]` lean switches
  keep their defaults and stay experimental. `codex_memories = false` Unknown (all conditions pass on 29 clean pairs,
  one pair on a different daily snapshot); `clean = true` Fail (3 hold-out pairs lost, at most 2 allowed);
  `codex_lean_tools = true` Fail under the registered rule on the 30 clean pairs (right 29 vs 30), read post hoc as
  undecided because 20 of the 50 registered pairs are missing. Medians fell but the paired statistics show no
  reliable saving; no re-run, stated as a decision beyond the rule. DECISIONS, config/tiers.toml comments, features,
  measured and the research index point to it.
