- Eval: the hold-out set is now 5 tasks of this repository and 5 from two other open-source Python libraries
  (humanize, itsdangerous), sizes 8-86 lines; the 6 candidates left out are kept in `DROPPED` with the reason.
  `scripts/eval/ext_repo.py` fetches each other repository once per run (`--ext-cache` for local copies), pins the
  full sha and gives every unit the parent's tree as a fresh one-commit repository (no future history; the clone is
  denied to the unit's agents); their tests are scored with `PYTHONPATH=src` and `--ext-python`.
  `holdout_check.py` checks them the same way.
