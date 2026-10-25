- Shared work context (docs/shared-context.md): ccx reads what a session has been doing from the tool's own session
  file, by code (Claude Code projects record, Codex rollout, dsh session; dsh's zstd files through Node or dsh's own
  Electron), and the other tools can read it. `ccx run --context auto|on|off` attaches the lead's recent asks,
  settled sentences, plan, changed files and latest message, each with time and source, ~1k tokens (auto: write
  tasks only; `[shared_context] run`); `ccx peek claude|codex|deepseek` is a read-only look at another tool's open
  session here; the per-turn hook adds one line per other tool that did something since you last looked
  (`[shared_context] turn = false` turns it off). All of it framed as data, not instructions, in the sub-agent's
  rules, the leads' memory block and the board's AGENTS.md block. Each tool keeps its own context: this is a shared
  summary, not one shared context. A/B on real CLIs in docs/research/2026-10-25-shared-context-ab.md.
