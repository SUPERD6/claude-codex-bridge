- Seven-cores evaluation, round 1 (Claude Code + Codex, real runs): `scripts/eval/seven_ab.py` runs four randomised
  paired A/B comparisons (self vs delegate, fixed model vs routing, review off vs on, without vs with project memory;
  3 rounds per task, resumable, budget-capped) and `scripts/eval/seven_func.py` the functional checks (Codex lead ->
  Claude sub-agent, kill then `ccx task resume`, `ccx undo`, the spend cap). Three medium and three memory tasks join
  `scripts/eval/tasks.py`; fake-CLI tests cover the schedule, resuming, the statistics and the undo check. Plan and
  report in `docs/research/2026-10-24-seven-cores-plan.md` and `-ab.md` (EN + ZH), de-identified data in
  `docs/research/data/`.
