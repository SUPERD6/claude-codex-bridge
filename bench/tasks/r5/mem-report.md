# mem-report

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `f223125` |
| Starting point | its parent, `f223125^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

Nobody can tell whether the shared memory is used across tools: `memory.mark_used` only counts uses.

Wanted: record who used a note, in which project and how (session start, a search, a sub-agent's brief), and a
report `ccx mem report [--days 14] [--json]`: who wrote the notes that were used and who used them (writer x user),
per project, by way of use, and how many notes written in that time nobody used yet. Uses recorded before this
change count as `unknown`.

Interface the tests use:
- `memory.mark_used(p, seqs, by=None, project=None, via=None)`; the start-up line (`ccx mem delta --as claude`) marks
  with `via="start"`, a sub-agent's brief with `via="brief"`, search with `via="search"`; `project` is the working
  folder's name.
- `memory.use_report(p, days=14) -> dict` and `ccx mem report --json` print
  `{"matrix": {writer: {user: n}}, "via": {way: n}, "by_project": {project: {writer: {user: n}}},
  "written": {writer: n}, "written_never_used": n, ...}`; a use without `by` counts under user `unknown`, a writer
  whose notes nobody used is not in `matrix`.
- `ccx mem report` (text) has a header containing `written by \ used by` and a total like `3 time(s)`.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show f223125:tests/test_memsuggest.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_memsuggest.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
