# hz-intword-carry

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | https://github.com/python-humanize/humanize (MIT; not copied here) |
| Commit (the reference change) | `ca892b368a535a79cc5e2181d052245b94fd6652` |
| Starting point | its parent, `ca892b368a535a79cc5e2181d052245b94fd6652^`, as a fresh one-commit repository |
| Python for the tests | 3.11+ with pytest, freezegun (pytest 9.0 or newer), without `humanize` installed |
| Area | humanize: intword rounding |
| Reference size | 8 non-test lines in 1 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`humanize.intword()` writes a big number with a word for its unit, and a value that rounds up to a whole next unit is
written as 1 of that next unit (with the default format, "1.0 <next unit>", never "1000.0 <unit>"). For very large
numbers, from about the sextillions up, this no longer happens: a value that rounds up to the next unit comes out as
"1000.0" (or "1000" with a "%.0f" format) of the smaller unit.

Wanted: the round-up carry works for every named unit up to decillion, whatever format is passed. Numbers above a
decillion and below a googol have no unit of their own; they stay written in decillions exactly as today.

## Acceptance (hidden tests)

The commit's own test file(s): [`tests/test_number.py`](https://github.com/python-humanize/humanize/blob/ca892b368a535a79cc5e2181d052245b94fd6652/tests/test_number.py). Before scoring, the repository's test folder and test settings are put back as they were at the parent and these files are written over them; the files its install would generate are stubbed (`src/humanize/_version.py`); then, from the repository root:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider --color=no tests/test_number.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
