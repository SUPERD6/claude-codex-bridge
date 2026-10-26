- Eval: `scripts/eval/fixround_replay.py` replays recorded review-driven fix rounds offline, with no model calls. It
  rebuilds the tree before each fix round from the run's start commit plus the diff in its review prompt, and the tree
  after it from the fix round's own review prompt (or the unit's final tree). It runs the task's hidden test on both
  and counts fail->pass / pass->fail / unchanged per review reason, per kind of [must] item and per who started the
  round. A new file cut at 4000 characters is completed from the final tree only when the recorded text is a prefix
  of it; otherwise the round is skipped and counted. `--check-final` re-scores each unit's final tree against
  results.jsonl as a second check.
- Eval: `r5.py summary` / `export` add `by_tag`: per tag and arm, n / right / $ per success and wall median, mean and
  p75, with each round kept apart; the per-arm totals also get `wall_mean` and `wall_p75`.
