# hz-natural-list-iterables

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | https://github.com/python-humanize/humanize (MIT; not copied here) |
| Commit (the reference change) | `ffdf407fdfe1a5738159b989eb2df190ed780448` |
| Starting point | its parent, `ffdf407fdfe1a5738159b989eb2df190ed780448^`, as a fresh one-commit repository |
| Python for the tests | 3.11+ with pytest, freezegun (pytest 9.0 or newer), without `humanize` installed |
| Area | humanize: natural_list input types |
| Reference size | 20 non-test lines in 1 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`humanize.natural_list()` joins items into readable text ("a, b and c"), but it only really works for lists (and
other sequences): a dictionary's keys view or a generator fails, although they are perfectly good collections of
items.

Wanted: `natural_list(items)` accepts any iterable, read only once (so a generator works), and gives the same text as
it does for a list of the same items: nothing gives "", one item gives that item as text, two give "x and y", more
give "x, y and z". Every item is turned into text with `str()` as now. The type hint and the docstring say Iterable.

## Acceptance (hidden tests)

The commit's own test file(s): [`tests/test_lists.py`](https://github.com/python-humanize/humanize/blob/ffdf407fdfe1a5738159b989eb2df190ed780448/tests/test_lists.py). Before scoring, the repository's test folder and test settings are put back as they were at the parent and these files are written over them; the files its install would generate are stubbed (`src/humanize/_version.py`); then, from the repository root:

```bash
PYTHONPATH=src python -m pytest -q -p no:cacheprovider --color=no tests/test_lists.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
