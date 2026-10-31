- `[review] must_needs_repro` (experimental, default off; P1-10): with ccx's check passed, the reviewer is told a
  `[must]` needs `repro: <command / input and wrong result / failing test>`. `"downgrade"`: a `[must]` without it
  becomes a `[should]` (no `review_failed`, no fix round); `"confirm"`: when no `[must]` has one, the next
  stronger reviewer settles them once, then the same downgrade. run.json's `review.repro` records the mode, how
  many lacked a repro, the confirming reviewer and how many were downgraded.
