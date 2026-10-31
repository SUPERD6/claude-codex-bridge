# its-timed-fallback-signers

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | https://github.com/pallets/itsdangerous (BSD-3-Clause; not copied here) |
| Commit (the reference change) | `6c58e969a513646c8e37260417929770a4ab1b67` |
| Starting point | its parent, `6c58e969a513646c8e37260417929770a4ab1b67^`, as a fresh one-commit repository |
| Python for the tests | 3.11+ with pytest, freezegun, without `itsdangerous` installed |
| Area | itsdangerous: timed serializer key rotation |
| Reference size | 21 non-test lines in 1 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`itsdangerous.Serializer` takes `fallback_signers`, so that after a change of signer settings (another digest
method, say) data signed with the old settings still loads: `loads()` tries the main signer and then each fallback.
`TimedSerializer` accepts the same argument but its `loads()` ignores it: timed data signed with settings that are
only in `fallback_signers` is rejected as a bad signature.

Wanted: `TimedSerializer.loads()` tries the main signer and then the fallbacks, as `Serializer.loads()` does, and
returns the payload (with the timestamp when `return_timestamp=True`) from the first one that accepts the data;
`max_age` is checked as before. When none accepts it, the error from the last one tried is raised.

## Acceptance (hidden tests)

The commit's own test file(s): [`tests/test_itsdangerous/test_timed.py`](https://github.com/pallets/itsdangerous/blob/6c58e969a513646c8e37260417929770a4ab1b67/tests/test_itsdangerous/test_timed.py). Before scoring, the repository's test folder and test settings are put back as they were at the parent and these files are written over them; then, from the repository root:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider --color=no tests/test_itsdangerous/test_timed.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
