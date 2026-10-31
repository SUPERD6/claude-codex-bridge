# codex-hook-text

Set: `r5`. r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `f51996c` |
| Starting point | its parent, `f51996c^`, plus today's `tests/conftest.py` |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

Codex never shows ccx's session-start lines. Codex 0.164 reads hook output that starts with `[` or `{` as JSON; when
it is not valid JSON it counts the hook as failed and drops the output. Every ccx start line begins with `[ccx`.

Wanted: output meant for Codex (`ccx mem delta --as codex`, `ccx turn --as codex`) starts with a plain line, e.g.
"From ccx (shared memory and delegated work):", followed by the usual lines. Claude Code's output is unchanged.

Interface the tests use: `ccx.commands.common.hook_text(text, as_) -> str`: for `as_ == "codex"` text that starts
with `[` or `{` gets the plain line in front, other text is returned as it is (`hook_text("plain text", "codex") ==
"plain text"`); for other tools it returns the text unchanged (`hook_text("[x]", "claude") == "[x]"`).
`ccx mem delta --as codex --peek` still contains `[ccx shared memory` but does not start with `[` or `{`;
`--as claude` still starts with `[ccx`.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show f51996c:tests/test_ccx.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_ccx.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer. For external tasks the evaluation takes Claude's web tools and the copies of the repository away from its agents; a download from a shell is not blocked, only flagged by the audit; and a model may remember an older commit.
