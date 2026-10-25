- Independent review is cheaper and checks the task, not the tests (seven-cores A/B, PR #30: routing picked
  claude sonnet medium as the reviewer, 20–40x the luna-low work it reviewed; it mostly asked for more tests and
  missed the same real bug three times). Now each other vendor's T1 rung (claude haiku low, codex luna low, ...)
  comes before the routed rung, so sonnet is only the fallback in `[review] also`. The review brief asks the reviewer
  to go through the task requirement by requirement (each return value, case, rule and error it names), since the
  acceptance tests may cover only some; a requirement not met is `[must]`, missing tests are a `[note]`. Real check
  (inventory task, luna low worker, `--review on`, 3 runs): haiku low found the bug each time ("returns Item
  objects, the task asks for SKUs"), the fix round made the hidden test pass 3/3 (round 1 with review: 0/3), review
  cost $0.004–0.009 per run (round 1: $0.04–0.09).
