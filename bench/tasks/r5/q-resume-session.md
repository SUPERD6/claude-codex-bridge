# q-resume-session

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `6cdae1e` |
| Starting point | its parent, `6cdae1e^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

`ccx q resume` starts a `doing` piece over from scratch when `q run` was killed, even though its sub-agent session
was half way through. The item only learns its run id when the run returns, which a killed `q run` never reaches.

Wanted: `ccx q resume` finds the run a `doing` piece was in the middle of by its `q:<item id>` label (a review's fix
round included) and continues that run's session instead of starting over, telling the sub-agent it was stopped.
A piece whose run had already finished before `q run` was killed is marked done without running again.

Interface the tests use:
- `ccx q resume` prints JSON with `restored: {<item id>: "resumed" | "finished" | ...}`.
- A resumed piece continues the same session (for Codex: `exec resume <session_id>`), and the brief it gets starts
  with this note, word for word: "ccx was stopped while you were working on this piece. Go on from where you were:
  check what is already done before redoing anything." followed by a blank line and the original brief.
- A finished piece: `restored` says `finished`, no sub-agent is called again, the item becomes `done` and its
  `cost_usd` is greater than 0 (what its run spent).

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 6cdae1e:tests/test_queue.py`; `git show 6cdae1e:tests/test_recover.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_queue.py tests/test_recover.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
