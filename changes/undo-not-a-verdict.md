- `ccx undo --apply` no longer records the run as wrong. It restores the files, writes `undone.json` and an `undo`
  event (`reason: undone`), and the run waits for your verdict (the 12-hour sweep skips undone runs). Add `--wrong` to
  record it as wrong in the same step (a lead verdict: it teaches routing). Seven-cores A/B question 8: undoing to
  retry or to split the work used to teach routing a failure. See docs/DECISIONS.md.
