- Research: verdict audit (`docs/research/2026-10-31-verdict-audit.md`): on the evaluations' 565 ccx units, after
  #158 8 of the 209 receipts that said right failed the hidden tests (3.8 %, above the 2 % bar; before #158 18/267,
  6.7 %); all 8 a passing check that did not test what the hidden test asked; 47 of 51 receipts that said wrong
  were right.
  `scripts/research/verdict_audit.py` recomputes it read-only; scrubbed per-unit rows in `docs/research/data/`.
- Research: dogfood (`docs/research/2026-10-31-dogfood.md`, real use, not a controlled experiment): the real hub's
  ledger for 10-24 to 10-30 has 283 runs ($8.17), only 5 of them (3–5 tasks) real work outside ccx's own tests;
  `scripts/research/dogfood.py` prints counts only. README links both.
