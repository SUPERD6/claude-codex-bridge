- The board on the real CLIs (codex-cli 0.164.0 gpt-6-luna low, dsh 0.2.1-rc.3 deepseek-flash low): `ccx say
  --resume` got answers from both back on the board with the right `from` / `via` / `reply_to`; the Claude hook
  command shows them once. DeepSeek cost $0.0030. Codex desktop's per-turn hook and `--now` into a live Codex thread
  are not verified (docs/research/2026-10-25-board-acceptance.md).
- Fix: a message sent with `ccx say --resume` no longer tells the headless run to `ccx reply` itself (ccx posts its
  answer; dsh had no `ccx` on its PATH and said so in its answer).
