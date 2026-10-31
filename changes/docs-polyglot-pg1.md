- Research report on the external benchmark pg1 (`docs/research/2026-10-31-polyglot-pg1.md`, EN + ZH): on 30 polyglot
  Python exercises (one round, hidden tests, one try), a Sonnet lead delegating to Codex gpt-6-luna low through ccx
  (ccx2) was right 12/30 against 25/30 doing it itself (13:0 discordant, p = 2.4e-4) and cost 3.1× per success (95 %
  CI 2.2–5.4), all 30 exercises; 82 % of ccx2's spend was on the lead's side. With no lead (direct) the same tier cost
  0.57× self per success but was right 9/30. 14 of ccx2's 18 failures guessed the hidden tests' interface wrong (one
  person's coding); its check ran the sub-agent's own `test_own.py` and passed in all 18, so the tier never climbed.
  Recomputed from the result rows by `scripts/research/polyglot_pg1.py` (fixed bootstrap seeds, post-hoc feature AUCs
  with intervals, half-up wall rounding); scrubbed rows in `docs/research/data/2026-10-31-polyglot-pg1.json`. README
  (external-benchmark line), `docs/measured.md`, the research index and DECISIONS (a direction, not implemented:
  small tasks stay with the lead; `[routing] small_self` still ships off) updated.
