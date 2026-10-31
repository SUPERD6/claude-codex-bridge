# quota-stop-log

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `4b4eb2f` |
| Starting point | its parent, `4b4eb2f^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

When ccx takes a failed attempt for a quota stop it falls back or waits, but leaves no trace of why. A wrong call
(the word "quota" in a task's own output, a new wording of a real limit) cannot be found later.

Wanted: every attempt taken for a quota stop appends its evidence to `<hub>/ccx/quota-stops.jsonl`, and `ccx quota`
shows the last five.

Interface the tests use:
- `ccx.quota.stop_evidence(cli, stdout, stderr, error) -> dict`: for Claude, a rejected `rate_limit_event` in the
  stream gives `{"by": "rate_limit_event", "event": <its rate_limit_info as it came>}`; otherwise the first quota
  hint that matches the text gives `{"by": "hint", "hint": <the hint>, "text": <the words around it>}`; nothing
  known gives `{"by": "unknown"}`.
- Each line of `quota-stops.jsonl` has `ts`, `run_id`, `agent`, `model` and the evidence keys.
- `ccx quota` JSON gets `recent_quota_stops` (the last five rows) only when there is at least one; other failures
  (an auth error) write nothing.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 4b4eb2f:tests/test_quota_stop_log.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_quota_stop_log.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
