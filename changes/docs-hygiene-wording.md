- Tests: a repo-hygiene test scans every tracked text file for personal home folders (a drive's Users\<name>,
  /Users/<name>, /home/<name>), allowing placeholders such as <you>, example and CI runner names.
- Docs: README says v0.5; `ccx -h`, pyproject and both plugin.json descriptions say Claude Code, Codex and DeepSeek
  lead and sub-agent each other, Gemini CLI only as a sub-agent adapter not run for real; `ccx -h` no longer opens
  with an unconditional "cost-saving".
- Docs: docs/measured.md adds the round-5 r5h ccx2 row (19/20, $0.135 per success, 236 s median wall; dev set,
  signal only); docs/research/README.md indexes the research reports (date, question, one-line result).
