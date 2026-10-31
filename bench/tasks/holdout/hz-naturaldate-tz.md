# hz-naturaldate-tz

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | https://github.com/python-humanize/humanize (MIT; not copied here) |
| Commit (the reference change) | `a47a89ea9111a5eaba138c391e8a564134a15c60` |
| Starting point | its parent, `a47a89ea9111a5eaba138c391e8a564134a15c60^`, as a fresh one-commit repository |
| Python for the tests | 3.11+ with pytest, freezegun, without `humanize` installed |
| Area | humanize: naturalday / naturaldate time zones |
| Reference size | 19 non-test lines in 1 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`humanize.naturalday()` and `humanize.naturaldate()` compare the date of the value with today's date on the
machine's local clock. For a timezone-aware datetime that is wrong near midnight: a moment that is "today" where the
datetime's own time zone is can come out as "tomorrow" or "yesterday", because "today" was taken somewhere else.

Wanted: when the value is a timezone-aware datetime, "today" is the current date in that value's own time zone, in
both functions. Dates and naive datetimes behave as before. `naturaldate()` keeps its rule of adding the year when
the date is more than about five months away, and otherwise hands the value, with its time zone, on to
`naturalday()`.

## Acceptance (hidden tests)

The commit's own test file(s): [`tests/test_time.py`](https://github.com/python-humanize/humanize/blob/a47a89ea9111a5eaba138c391e8a564134a15c60/tests/test_time.py). Before scoring, the repository's test folder and test settings are put back as they were at the parent and these files are written over them; then, from the repository root:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider --color=no tests/test_time.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
