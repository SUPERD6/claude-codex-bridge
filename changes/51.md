- `ccx discuss --tier` defaults to `auto`: every agent talks at T2, except one whose subscription quota is projected
  past 100% by its reset (`ccx/quota.py`): it steps down to T1 (Claude on haiku, Codex on luna). `--dry-run` shows
  each agent's tier, model and why (`tier`, `models`, `tier_why`); the saved discussion keeps `tiers`. A tier given
  (`--tier T1`) applies to all, as before.
