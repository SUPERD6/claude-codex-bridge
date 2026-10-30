- `[shared_context] dedupe` (experimental, default `false` = unchanged): `true` leaves out a "Settled" sentence of the
  shared work context that already stands whole in one of the person's asks shown above it; nothing else is cut and
  the default size is unchanged. The run's `shared_context` record now always carries `est_tokens` (rough tokens of
  the block), and `deduped` / `deduped_chars` when the switch is on. Off until measurement M5.
