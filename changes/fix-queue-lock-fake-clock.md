- Tests: the two queue-lock tests that waited out other writers on the wall clock (real threads racing a
  2 * timeout window) run on a fake clock instead, so a slow CI runner can no longer fail them (windows 3.12, #207).
  Both still fail when the rule they guard is broken; no code change.
