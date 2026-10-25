- The board, part 2: one per-turn hook, `ccx turn --as claude|codex`, shows a lead before its turn the board
  messages new for it, the lines of `.ccx/context.md` that changed since it last looked (never the whole file) and
  the project journal lines the others added, within ~300 tokens; plus the H10 long-conversation hint. Nothing new,
  nothing printed. `ccx sync` puts it in Claude Code's `UserPromptSubmit` (replacing `ccx lead --hint` in place) and
  adds `[[hooks.UserPromptSubmit]]` to the Codex block (Codex 0.164; trust it once in `/hooks`). A turn the person
  typed restarts the thread's machine-message count; a ccx sub-agent's turn and messages ccx pushed in do not.
