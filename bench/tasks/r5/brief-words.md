# brief-words

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `21cb3da` |
| Starting point | its parent, `21cb3da^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

Two problems with `ccx run`:

1. The shared notes a sub-agent's brief gets (`memory.for_brief`, by word overlap) are picked badly. Words keep the
   dots and dashes at their ends (`JSON.` is not `json`), and common words such as `the`, `with`, `我们`, `这个` count
   as overlap, so unrelated notes get in and the right one is missed. The L5 memory cases in
   `scripts/eval/l5_memory.py` show it: the `mem-json` note never reaches its brief.
2. A lead that pipes `ccx run`'s JSON through `| tail -5` loses the run_id, which is the first key.

Interface the tests use:
- `memory._words(text) -> set[str]`: lower-cased words with the `.` and `-` at their ends stripped (`ccx-run-` is
  `ccx-run`, `a.b.c` stays), no common English words (at least `the`, `and`, `with`, `this`, `that`); Chinese runs
  are split into two-character pairs and common pairs (at least `我们`, `这个`) are dropped:
  `_words("我们这个") == {"们这"}` and `"记忆" in _words("我们的记忆")`.
- Over the 6 L5 cases (each with the 3 distractor notes), every case's own note is picked and at most 2 unrelated
  notes are picked in total.
- `ccx run` and `ccx resume` output: the JSON's LAST key is `recap`, one line like
  `ccx run <run_id>: status=done ok=true check=passed review=<verdict or none> ... next: ccx show <run_id>`
  (it must contain `ccx run <run_id>: status=done ok=true check=passed review=` and end with
  `next: ccx show <run_id>`). Other keys unchanged.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 21cb3da:tests/test_brief_words.py`; `git show 21cb3da:tests/test_ccx.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_brief_words.py tests/test_ccx.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
