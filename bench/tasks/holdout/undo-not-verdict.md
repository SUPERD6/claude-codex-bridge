# undo-not-verdict

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `8353f65` |
| Starting point | its parent, `8353f65^`, plus today's `tests/conftest.py` |
| Area | undo and verdicts |
| Reference size | 37 non-test lines in 4 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`ccx undo <run_id> --apply` puts back the files a write run changed, and it also records the run as wrong. But
people undo to try again or to split the work differently, not only because the work was wrong, and that "wrong"
teaches routing (it changes the routing state) all the same.

Wanted:
- Undoing alone records no verdict: the routing state and the verdict events stay as they were, and the `verdict`
  field of the JSON output starts with `none` (saying the run waits for the person's `ccx verify` or
  `ccx undo --wrong`).
- An undone run is left alone by the probable-verdict pass (`ccx verify --sweep`): it waits for the person.
- Every applied undo appends an event to the ledger: `{"type": "undo", "run_id": ..., "reason": "undone",
  "wrong": <true|false>, "ts": ...}`.
- New flag `ccx undo <run_id> --apply --wrong`: also records the run as wrong with reason `wrong`, exactly as the
  person's own `ccx verify <run_id> --ok 0 --reason wrong` records it (an ordinary verdict, not a soft, probable
  one), unless the run already has a verdict; the JSON `verdict` is then "recorded as wrong (undo --wrong)".

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 8353f65:tests/test_verdicts.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_verdicts.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
