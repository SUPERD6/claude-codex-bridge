# waiting-evals

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `05ffff9` |
| Starting point | its parent, `05ffff9^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

The session-start line "N delegated piece(s) wait for you" counts evaluation runs too, so on a real hub it says 33
when 16 are real. ccx already has one rule for runs that measured ccx: `ledger.is_eval` (label `eval-...`, started
with `--no-ab`, ccx's own probes such as `quota-probe`).

Wanted: the count leaves those out; `ccx ui` itself still lists them.

Interface the tests use: `ccx.ui.waiting(p) -> int`, the number of finished runs nobody judged yet, without
evaluation runs (a run labelled `eval-7c:...`, a run whose `route` has `no_ab: true`, a run labelled `quota-probe`).

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 05ffff9:tests/test_ui.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_ui.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
