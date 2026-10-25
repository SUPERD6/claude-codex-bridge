- Shared hub notes now reach Claude and Codex sub-agents too (I6). Before, a tool with a start hook was skipped on
  the assumption that its hook shows memory, but under a sub-agent `ccx mem delta` prints nothing, so hub notes
  never reached Claude or Codex sub-agents at all. Every sub-agent's brief now carries up to 4 notes that share a
  word with the task (`memory.for_brief`, budget unchanged at ~300 tokens); no shared word, no note.
