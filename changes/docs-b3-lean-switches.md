- B3 result report (docs/research/2026-10-31-b3-lean-switches, both languages): the three `[subagent]` lean switches
  stay off by default and experimental. `codex_memories = false` Unknown (all conditions pass on 29 clean pairs, one
  pair on a different daily snapshot), `clean = true` Fail (3 hold-out pairs lost, at most 2 allowed),
  `codex_lean_tools = true` Unknown under the registered rule (only 30 of the 50 registered pairs are clean). Medians
  fell but the paired totals did not; 11 limits listed; no re-run. DECISIONS, config/tiers.toml comments, features,
  measured and the research index point to it.
