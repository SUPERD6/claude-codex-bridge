- Research report on the external benchmark pg1 (`docs/research/2026-10-31-polyglot-pg1.md`, EN + ZH): on 30 polyglot
  Python exercises (one round, hidden tests, one try) delegating to Codex gpt-6-luna low through ccx was right 12/30
  against 25/30 for the Sonnet lead doing it itself (13:0 discordant, p = 2.4e-4) and cost 3.1× per success (95 % CI
  2.1–5.2); 82 % of ccx2's spend was on the lead's side; 14 of its 18 failures guessed the hidden tests' interface;
  its check ran the sub-agent's own `test_own.py` and passed in all 18, so the tier never climbed. Recomputed from the
  result rows by `scripts/research/polyglot_pg1.py` (fixed bootstrap seed); scrubbed rows in
  `docs/research/data/2026-10-31-polyglot-pg1.json`. README (external-benchmark line), `docs/measured.md`, the
  research index and DECISIONS (small tasks are not delegated; a sub-agent's own tests are not check evidence) updated.
