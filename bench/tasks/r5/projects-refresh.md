# projects-refresh

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `2978690` |
| Starting point | its parent, `2978690^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

The project catalog (`ccx projects`, `ccx where`) goes stale: it is only rebuilt by a manual `ccx projects scan`.

Wanted: at session start (`ccx mem delta`, which the start-up hook runs) ccx rescans the catalog in a detached
background process when it is due; the start never waits for it, and only one scan runs at a time.

Interface the tests use:
- `ccx.projects.refresh_due(p, cfg, now=None) -> bool`: False with no roots and no catalog; True when roots are set
  and nothing was scanned yet; False right after `projects.refresh(p, cfg)`; True once the catalog is older than
  `[projects] refresh_hours` hours (default 24), also when the roots are no longer configured but the last scan had
  roots; `refresh_hours = 0` turns it off. While the guard file `p.state / "projects.scanning"` is less than
  10 minutes old a scan is in progress: not due.
- `refresh_later(p, cfg)` starts the background scan (writes the guard first); `ccx mem delta --as claude` calls it
  when due. Two quick starts in a row produce one scan; after it, `projects.load(p)["projects"]` holds the projects
  and the guard file exists.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 2978690:tests/test_projects.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_projects.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
