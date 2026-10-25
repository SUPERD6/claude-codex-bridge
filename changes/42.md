- `ccx discuss` reads the critic as agree / objections / unparsed (`discuss.critique`): `[must]` items count as
  objections even without the `CRITIQUE:` line; no line and no `[must]` is unparsed, which neither ends the talk
  early nor counts as agreement. An unparsed critic, or a judge without `RECOMMEND:` or without tagged items, is asked
  once more in the same session (resume) with the rule repeated; if it still does not keep to it, the turn says
  `unparsed` and the result lists `unparsed_turns` (and `unparsed` for the judge) instead of guessing. `ccx ui` marks
  such turns. Discuss turns now keep their CLI session (`Request.keep_session`) so they can be resumed, and
  auto-archive tidies them like other finished runs.
