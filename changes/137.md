- Review prompt: ccx's independent reviewer (caller `ccx-review`, read mode) no longer gets the builder's "run the
  relevant tests" Finish text; it is told to run no tests or builds (reading with file tools or shell read commands
  stays allowed, so a Codex reviewer can still read), to open further files in one batch and to set
  `verification='not-run'`, and its Finish text points at the brief's Checks. Builders are unchanged. Replay of 10
  recorded round-5 reviews (claude haiku low only): median 29.9 s -> 23.1 s and 5,618 -> 4,362 output tokens per
  review; known real bugs found 15/28 -> 19/28, which at this n means no loss detected, not a gain. A Codex reviewer
  with the new text is not measured.
- Review brief: an opt-in `## Code around the change` block after the diff (`[review] context = true`, default
  false), in what the diff leaves of `max_diff_chars`: the changed functions in full, definitions of names they call
  (same file, or imported from the tree) and tests naming them. Off because the replay found fewer known bugs with
  it (11/28), although reviews took about two-thirds of the time (15.3 s vs 23.1 s).
- `scripts/eval/review_replay.py`: re-runs recorded round-5 reviews with old and new prompts (`--variants
  old,new,finish`) through the real review path (claude haiku low, clean room), with a money cap, and counts the
  known real findings kept. It needs the round-5 work folder of the machine that recorded them.
