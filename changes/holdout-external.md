- Eval: the hold-out set is now 5 tasks of this repository and 5 from two other open-source Python libraries
  (humanize, itsdangerous), sizes 8-86 lines; the 6 candidates left out are kept in `DROPPED` with the reason.
  `scripts/eval/ext_repo.py` reads each other repository once per run, before the canary, out of a clone in a
  temporary folder outside the work dir (`--ext-cache` for local copies) that is then removed, pins the full sha and
  gives every unit the parent's tree as a fresh one-commit repository (no future history). Their tests are scored
  with `PYTHONPATH=src` and `--ext-python`, after the parent's test folder and pytest configuration are put back.
  `holdout_check.py` checks them the same way.
- Eval leak guard for external units: the `--ext-cache` copies are denied and flagged, Claude's WebFetch/WebSearch
  are denied, pip gets no index, and the audit flags `pip install/download`, fetching from GitHub/PyPI, the
  repository's URL and `ext-cache`. The run does not start when `--ext-python` is older than 3.11, lacks the test
  modules or a new enough pytest, has the library itself installed, or sits next to the copies; a change to what is
  installed in it during a unit stops the run. Rows record that Python's versions and the commit date, and the
  summary reports results per repository.
