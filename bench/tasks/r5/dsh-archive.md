# dsh-archive

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `cae823e` |
| Starting point | its parent, `cae823e^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

ccx archives sub-agent sessions after a run (`sessions.archive = after_run`), but not DeepSeek Harness (dsh)
sessions: dsh 0.2.1 has no archive command. The desktop app keeps its archived sessions in
`<DSH_HOME>/storages/workspace.json` under `global.archivedSessionIds`.

Wanted: archive a dsh run's session by adding its session id to that list; `ccx archive --restore <run_id>` and
`ccx resume` (before resuming) take it out again. Only that one id is added or removed, everything else in the file
stays as it was; the file is backed up once as `workspace.json.ccx-backup` and replaced atomically. A missing file is
skipped, not created. Session folders are never moved.

Interface the tests use: `ccx.archive.dsh_mark(sid, archived: bool) -> tuple[bool, str]`: `(True, "ok")` when it
changed the list, `(True, "already so")` when there was nothing to change, `(False, <reason>)` when the file does not
exist, the reason containing "never opened" (the desktop app was never opened). A `ccx run --to dsh` (fake dsh in
`tests/fakes`) ends with the session id appended to `archivedSessionIds`.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show cae823e:tests/test_archive_after_run.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_archive_after_run.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
