- Evals archive what their throwaway hubs leave: `scripts/eval/preflight_e2e.py` and the memory units of
  `scripts/eval/seven_ab.py` run `ccx archive --apply` in their own hub at the end (`common.archive_hub`), final or
  not, since nothing continues those sessions and the person's hub never sees them. Sessions from such runs had
  stayed in the apps' session lists (2026-10-25). A run that ends with a final result already archives its own
  session in whatever hub it runs (`sessions.archive = after_run`); a test now covers that case too.
