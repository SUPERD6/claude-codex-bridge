- Review rubric (P1-10, `[review] coverage_rubric`, on by default): the reviewer checks, requirement by
  requirement, whether a test the acceptance command runs exercises it; tests the agent wrote or changed count as
  its own yardstick, not evidence; the brief lists the test files the command runs and which the agent wrote,
  added to or changed (`ccx way`'s acceptance brief too), and asks for the edited pre-existing test files in one
  `[note]` (a `[must]` only when a changed assertion contradicts the task or stops testing unchanged behaviour).
  A missing test, or one only the agent wrote, stays a `[note]`. `false` restores the old sentence for A/B.
