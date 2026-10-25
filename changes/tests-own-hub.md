- Tests: `tests/conftest.py` gives every test its own hub, Codex and Claude homes and user config under its own
  temp folder (and drops a live run's `CCX_DEPTH`/`CCX_RUN_ID`), so a test that forgets to set them never reads or
  writes the machine's real `~/.ccx`, `~/.codex` or `~/.claude`, and tests share no state. The shared test base
  retries removing its temp folder for up to 10 s: on Windows a background ccx (`--bg`) that just finished still
  holds the folder as its cwd for a moment.
- Tests no longer see the machine's own provider keys (`*_API_KEY`, `*_AUTH_TOKEN`): with a real
  `DEEPSEEK_API_KEY` set, `test_missing_key_is_a_clear_error` failed on that machine only.
