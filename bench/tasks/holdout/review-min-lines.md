# review-min-lines

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `b37a345` |
| Starting point | its parent, `b37a345^`, plus today's `tests/conftest.py` |
| Area | review trigger |
| Reference size | 32 non-test lines in 3 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

With `--review auto` (the default) the independent review runs only for `--risk visible/critical`, a sub-agent
that says it is unsure, or claimed files that do not match the diff. A large change that looks routine gets no
review at all.

Wanted: auto mode also reviews a write run whose diff has at least `[review] min_lines` changed code lines
(default 50; `0` turns this trigger off). Documentation files (`.md`, `.txt`, `.rst`, `.adoc`) do not count.

Interface:
- `ccx.review.code_lines(diff: str) -> int`: added plus removed lines in the code files of a unified diff (the
  `---` / `+++` file headers are not changed lines). A file's lines start at its `+++ ` header (the diff may
  come without `diff --git` or `---` lines).
- `ccx.review.reason(mode, risk, result, claimed, actual, lines=0, min_lines=50)`: the new trigger's reason is
  "<n> changed code lines" (e.g. "75 changed code lines"); an explicit request and the risk reasons still come
  before it.
- `min_lines = 50` in the `[review]` table of `config/tiers.toml`; the run loop passes the diff's code-line count
  and the configured value.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show b37a345:tests/test_review.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_review.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
