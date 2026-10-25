- Default `tradeoff` is now `save` (was `balanced`): routing starts small work on the cheap model. With routing fed
  the seven-cores A/B (PR #30), 5-minute work goes to codex luna low (predicted 0.94, about $0.004) instead of
  claude sonnet medium (0.997, about $0.04); 15-minute work still goes to sonnet. An existing hub keeps its own
  `defaults.tradeoff` if it set one (`ccx config get defaults.tradeoff`).
- A failed `--check` now escalates. When the sub-agent says done and ccx's own run of the acceptance command fails,
  the attempt is marked `check_failed` (learned as a failure of its rung) and, while a rung is left, the same session
  continues on the next rung with the check's output; before, only blocked/failed escalated and a cheap model that
  wrongly said done stopped there. The check runs once per attempt (the last result is reused, not re-run).
