- The repository is now a plugin marketplace: `claude plugin install relayline --marketplace SUPERD6/relayline`
  gives Claude Code the four skills and ccx's SessionStart / UserPromptSubmit hooks (they run the plugin's own
  `bin/ccx`); `codex plugin marketplace add SUPERD6/relayline` + `codex plugin add relayline@relayline` gives Codex
  the skills. Where the plugin is enabled, `ccx sync` leaves the Claude hooks and the four skills to it and removes
  its earlier copies, so nothing runs twice; `ccx doctor` reports the plugin, warns when a hook is there twice and
  when ccx itself is not installed. `bin/ccx` now finds a Python 3.11+ (`python3`, `python` or `py`).
