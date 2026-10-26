- The independent review now runs while ccx runs its own acceptance check, instead of after it. It is told the
  command and is only counted when the check passes; a failed or broken check stops the review and drops it.
  `--review off` is unchanged.
- `check_broken` is handled like the other failures: it ends a lane's session, gets its own card and history line in
  the dashboard, and the work queue treats it as needing the lead.
