- Tests: `test_verify_builtin_learns_ability_and_real_cost` wrote its sub-agent transcript with a fixed
  2026-10-24 timestamp, which fell out of `verify --builtin`'s 7-day window on 2026-10-31; it now uses the current time.
