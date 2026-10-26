- Review prompt: ccx's independent reviewer (caller `ccx-review`) no longer gets the builder's "run the relevant
  tests" Finish text and "your shell tool works" permission, which contradicted its brief ("You cannot run
  commands"); it gets a read-only Finish text that asks for further reads in one batch. Builders are unchanged.
  Replay of recorded round-5 reviews: median 29.9 s -> 23.1 s and 5,618 -> 4,362 output tokens per review, known
  real bugs found 16/28 -> 19/28.
- Review brief: an opt-in `## Code around the change` block after the diff (`[review] context = true`, default
  false), in what the diff leaves of `max_diff_chars`: the changed functions in full, definitions of names they call
  (same file, or imported from the tree) and tests naming them. Off because the replay found fewer known bugs with
  it (11/28), although reviews took half the time (15.3 s).
- `scripts/eval/review_replay.py`: re-runs recorded round-5 reviews with old and new prompts (`--variants
  old,new,finish`) through the real review path (claude haiku low, clean room), with a money cap, and counts the
  known real findings kept.
