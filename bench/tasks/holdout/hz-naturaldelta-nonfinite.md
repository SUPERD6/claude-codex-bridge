# hz-naturaldelta-nonfinite

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | https://github.com/python-humanize/humanize (MIT; not copied here) |
| Commit (the reference change) | `b48b37b187682ccc55b28ed1b7cfaa853dbca72f` |
| Starting point | its parent, `b48b37b187682ccc55b28ed1b7cfaa853dbca72f^`, as a fresh one-commit repository |
| Python for the tests | 3.11+ with pytest, freezegun, without `humanize` installed |
| Area | humanize: naturaldelta input checks |
| Reference size | 10 non-test lines in 1 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`humanize.naturaldelta()` given a float that is not a number (NaN) returns it unchanged as text, but given an
infinite float (positive or negative) it raises OverflowError.

Wanted: every non-finite float (NaN, infinity, minus infinity) is returned unchanged, as `str(value)`. A finite number
of seconds that is too large for a `datetime.timedelta` still raises OverflowError, as the docstring promises.

## Acceptance (hidden tests)

The commit's own test file(s): [`tests/test_time.py`](https://github.com/python-humanize/humanize/blob/b48b37b187682ccc55b28ed1b7cfaa853dbca72f/tests/test_time.py). Before scoring, the repository's test folder and test settings are put back as they were at the parent and these files are written over them; then, from the repository root:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider --color=no tests/test_time.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
