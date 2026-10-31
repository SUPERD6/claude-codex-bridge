# batch-review-risk

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `528a5b6` |
| Starting point | its parent, `528a5b6^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`ccx batch --plan plan.json`: a task in the plan can say `"review": "off"` (or on/auto, as `ccx run --review`) and
`"risk": "visible"`, but both are dropped, so every batch runs with the default review (a real 3-task batch spent
$0.04 of its $0.05 on reviews it did not want).

Interface the tests use: `ccx.commands.delegation.cmd_batch(argparse.Namespace(plan=..., caller=...))` builds one
`Request` per plan task and calls `delegation.run(request, paths)`; the request's `review` comes from the task's
`review` (default `auto`) and its `risk` from the task's `risk` (default None). The request's `label` is the task id.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 528a5b6:tests/test_ccx.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_ccx.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
