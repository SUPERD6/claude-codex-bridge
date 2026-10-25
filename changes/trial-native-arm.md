- `ccx trial` has a third half, "native": a Claude Code conversation that did the task with its own built-in
  helpers or a dynamic workflow (ultracode). Tag it with `ccx trial tag --arm native --session ID [--kind K --b B
  --ok 1|0 --since/--until ISO]`; its spend is read from that conversation's files, every helper and workflow agent
  included. The report compares each half with the lead doing it itself only within the same kind and difficulty
  (weighted by task count, 95 % interval resampled within buckets) and says "deferred, no conclusion" below 10
  matched tasks a half. `ccx trial report --markdown` shows three columns.
- Lead usage now ties a workflow's agents (`<session>/subagents/workflows/wf_*/agent-*.jsonl`) to their
  conversation; before, their tokens were counted as separate conversations and missed by per-session windows.
- `claude -p` sub-runs pass `--settings {"ultracode": false, "workflowKeywordTriggerEnabled": false}` and no longer
  inherit `CLAUDE_CODE_EFFORT_LEVEL`, which overrode the routed `--effort` (checked against Claude Code 2.1.309).
