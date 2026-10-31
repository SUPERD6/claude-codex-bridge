# discuss-auto-tier

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `5b68121` |
| Starting point | its parent, `5b68121^`, plus today's `tests/conftest.py` |
| Area | discussions |
| Reference size | 56 non-test lines in 2 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`ccx discuss` talks at one tier for every participant (`--tier`, default T2). An agent whose subscription quota is
projected to run out before it resets should talk on its cheap model instead.

Wanted: `--tier auto`, the new default: T2, except T1 for a participant whose projected quota share at its reset is
above 100% (the projection `ccx/quota.py` already makes, `quota.pressure`). A tier given explicitly applies to
everyone as before. The tiers chosen are used for the turns, kept in the saved discussion and shown by
`ccx discuss`.

Interface:
- `ccx.discuss.tiers(p, names, tier="auto", quota=None) -> (tiers, why)`: `tiers` maps each agent to its tier;
  `quota` (agent -> projected fraction of its window, e.g. 0.85) is read from ccx when None. With `auto`, `why` has
  an entry for every agent: the projected share as a percentage (like "85%") when there is a reading, or a text
  containing "no quota reading" when there is none. With a fixed tier, `why` is empty.
- `ccx.discuss.estimate(..., tier=...)` and `ccx.discuss.run(..., tier=...)` take either one tier for everyone or
  such a per-agent dict; the estimate's `models` and `tier` are per agent.
- The `ccx discuss --dry-run` JSON has `tier_why` only when the tier is auto.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 5b68121:tests/test_discuss.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_discuss.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
