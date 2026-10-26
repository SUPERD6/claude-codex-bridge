- Independent review raises `[must]` only for real problems with the asked-for change (round 5: fix rounds were
  spent on robustness the task never asked for, and units with review issues were not more often right): the
  reviewer must quote the task sentence a `[must]` rests on, or name the existing behaviour, test or task-named
  input it breaks; hardening, extra validation, unasked edge cases, style and extra tests are `[note]`. A `[must]`
  that labels itself out of scope right after the tag ("(out of scope)", "Hardening:", "not asked for", ...) counts
  as a note and starts no fix round.
- Review fix rounds: at most one per run (`[review] fix_rounds` is 0 or 1; larger counts as 1, and the round
  counter now increases so a larger value can no longer loop); the fix round's own review is judged against the
  first run's task instead of the issue list it was handed, and the fix brief says not to add unasked hardening.
