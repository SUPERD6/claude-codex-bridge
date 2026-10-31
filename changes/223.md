- A write run whose `--check` passed only on tests the sub-agent wrote or changed in that run (every test file the
  check ran; tests merely added to an existing file do not count) is no longer plain ok: `kind` is `ok_self_checked`.
  It is still a pass (exit 0, `ok` true, a `ccx q` piece is done), but `check.basis` and `needs_lead` say "not
  independently verified", the recap shows `needs_lead=ok_self_checked`, the ledger row has `check.self_authored`,
  `ccx ui` asks the person with the reason, it is never auto-judged right (`soft_verdicts`) and L2 auto-merge does not
  take it. On pg1 such a check passed in all 18 hidden-test failures; the verdict audit found 7 of its 8 false "ok"s
  ran a test the sub-agent had changed.
- New setting `[escalate] on_self_checked = review | rung | off` (`ccx config set escalate.on_self_checked ...`),
  default `review`: an `ok_self_checked` run is always reviewed (outside `weak_daily` and `weak`), the brief asks the
  reviewer to hold each name, signature, return value, error and case the task states against the code, and
  `must_needs_repro` does not apply; `rung` first has one stronger rung redo it in the same session (told its check
  ran only its own tests) while one is left; `off` only labels it. Default `review` because a review is one cheap read
  of the diff and #212's rubric is the question, while a rung redoes the whole task on a dearer model; not measured
  yet (planned: a ccx2 rerun of pg1).
- agent-delegate and task-routing (EN + ZH): a passing test the sub-agent wrote is not a done task; accept
  `ok_self_checked` against the task text or a check on existing tests.
