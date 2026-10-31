# q-killed-spend

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `8887d6d` |
| Starting point | its parent, `8887d6d^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`ccx q`: when the whole `ccx q run` process tree is killed (the machine sleeps, the terminal is closed), the run that
was in progress stays `running` in its run.json forever, and what it spent never reaches the ledger or the queue
item. `ccx stats` already knows how to close dead runs (`recover.sweep`, usage read back from the session file).

Wanted: `ccx q run`, `ccx q resume` and `ccx q ls` first close such dead runs as interrupted (state `interrupted`,
last attempt kind `killed`, its spend written to the ledger once), and `ccx q resume` adds what the item's runs
since it went `doing` spent to the item's `cost_usd`, then finishes the item as usual.

Interface the tests use: after a killed `q run` and a `ccx q resume`, the old run's record has state `interrupted`
and last attempt kind `killed` with `ae_usd > 0`, exactly one ledger row for that run, and the item (from
`ccx q ls`) is `done` with `cost_usd` at least the killed attempt's `ae_usd`. Tests use the fake CLIs in
`tests/fakes` (`FAKE_STATUS=hang`).

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 8887d6d:tests/test_recover.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_recover.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
