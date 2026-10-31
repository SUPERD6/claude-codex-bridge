- `scripts/eval/r5.py` (eval only; ccx itself unchanged): new task set `--taskset polyglot`, 30 Python exercises of
  aider's polyglot benchmark (Exercism, MIT), an outside benchmark with a difficulty spread, chosen without looking at
  any solution (`scripts/eval/polyglot_selection.json`: pinned commit, licence, rule, each exercise's reason). A unit
  gets only the solution stub in a fresh repository; the brief is the exercise's instructions plus an aider-like
  addendum; the exercise's tests are the hidden test, run in a fresh folder that receives only the solution files.
  Default arms self, ccx2, direct; preflight, canary, ledger and paired statistics are the existing ones. Every
  exercise unit keeps its final diff. Plan: `docs/research/2026-10-30-polyglot-slice-plan.md`.
