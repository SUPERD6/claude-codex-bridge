- `ccx trial report` no longer crashes with FileNotFoundError / WinError 3 on a Claude or Codex session folder it
  cannot list (removed while walking, or past the Windows path limit): the session readers walk with `usage.walk`,
  which lists long paths with the `\\?\` prefix and skips what it still cannot list. A delegated task whose lead
  conversation's files are gone or unreadable is shown under `unmeasured` with the reason and left out of the
  comparison instead of counting as zero.
- `ccx trial stop --void REASON` records the trial as void (the running one, or the last one if it has ended);
  `ccx trial report`, `--markdown` and the dashboard show it as void with its reason and claim no saving or result.
  `ccx trial stop` without `--void` is unchanged.
- The H11 trial `trial-20261025` is void (docs/DECISIONS.md): defaults that waited for it (`[memory] by_kind`,
  `[lanes] default`) stay off and are decided by the confirmation run's fast vs save tiers; no default changed.
