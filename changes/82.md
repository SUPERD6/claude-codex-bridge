- Codex hooks work on Windows (H7): Codex 0.164 runs hook commands through PowerShell there, where a line that
  starts with a quoted path is just a string, so ccx's SessionStart and UserPromptSubmit hooks ran and failed with no
  output (seen live: the desktop app started and finished them; nothing reached the conversation). `ccx sync` now
  writes them with the call operator (`& "python" "ccx.py" ...`) on Windows. `ccx doctor` warns about a block written
  before this fix: run `ccx sync --apply`, then trust the hooks again in Codex with `/hooks`.
