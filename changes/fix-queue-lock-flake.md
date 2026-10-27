- `ccx q` queue lock: on Windows it now waits when creating its lock file is denied (a file the last holder just
  unlinked is "delete pending" there, which raised PermissionError instead of FileExistsError and failed the write;
  the likely cause of a parallel `q run` row with no run on Windows CI, not reproduced locally, and that test now
  prints the row). A lasting denial (a folder no file can be created in, or any denial off Windows) fails at once,
  and the wait has a hard deadline (2 x timeout) even when a held lock cannot be taken over, so it never spins
  forever. Only a lock file older than the timeout is taken over (no longer any lock once the waiter has waited
  that long), and a release removes only its own lock, retrying a denied unlink instead of failing the write.
- `ccx q run`: an item that errors reports `status: failed` with the error (and `not_recorded` if writing that back
  failed too) instead of raising; one that errors after its run keeps that run and its cost in the row and the
  queue; a skipped item reports `status: todo`.
