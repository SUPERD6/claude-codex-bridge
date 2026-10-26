- agent-delegate skill: a short "Delegate cheaply" section from round 5's lead transcripts. The brief is the
  person's request verbatim (interfaces, names, strings, numbers unchanged) plus known paths and the acceptance
  command, without reading the code base first; long work goes `ccx run --bg` then `ccx show <run_id> --wait`
  (no `tail`/`head` pipes, no resume of a running run); a passed check plus files_changed / diffstat is enough;
  `--review` stays auto; the sub-agent never commits. The brief template and the Chinese README say the same.
- Round-5 evaluation: an opt-in arm `ccx2` (`--arms ccx2`) whose lead follows that guidance, next to the unchanged
  `ccx` arm; the default schedule is unchanged, `summary` reports it, unknown arms are refused.
