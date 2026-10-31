# ledger-repair

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `ce4195a` |
| Starting point | its parent, `ce4195a^`, plus today's `tests/conftest.py` |
| Area | accounting repair |
| Reference size | 86 non-test lines in 2 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

Codex usage recorded before a recent counting fix is over-counted. `codex exec resume` reports the whole session's
running total, and old run records stored that total as each resumed attempt's usage, so `ae_usd` and the ledger
count the earlier turns again. New records already store only the growth (`delegate._codex_total`,
`delegate._codex_growth`) and keep the session's total in the attempt's `codex_total`.

Wanted: `ccx repair [--apply]`.
- Without `--apply` it is a dry run: it reports what it would fix and changes nothing.
- With `--apply`: going through the run records (`<hub>/ccx/runs/*/run.json`) oldest first, a Codex attempt without
  `codex_total` that continues a session seen before gets its `usage` replaced by the growth over that session's
  previous total, and its `ae_usd` recomputed from the price table. Every Codex attempt it has looked at then
  carries `codex_total`, so a second repair finds nothing to fix.
- The ledger rows of the fixed runs are rebuilt the same way `ledger.append` writes them, after the ledger has been
  backed up to a file next to it; other rows (events) stay as they are. Files are replaced atomically.
- JSON output: `applied`, `runs_fixed`, `runs` (each with `run_id`, `ae_before`, `ae_after`) and the totals
  `ae_before`, `ae_after`.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show ce4195a:tests/test_ccx.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_ccx.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
