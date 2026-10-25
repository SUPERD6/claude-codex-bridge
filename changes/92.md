- Codex hooks show ccx's lines (H7, second half): Codex 0.164 reads hook output that starts with `[` or `{` as JSON,
  and when it isn't, counts the hook as failed and drops the output. Every ccx start line begins with `[ccx`, so even
  with the PowerShell fix (#82) Codex saw nothing. `ccx mem delta --as codex` and `ccx turn --as codex` now start with
  a plain line ("From ccx (shared memory and delegated work):"); Claude Code's output is unchanged. Checked with a
  throwaway CODEX_HOME and hub: before, `hook: SessionStart Failed`; after, Completed and the note (Chinese included)
  is in the conversation.
