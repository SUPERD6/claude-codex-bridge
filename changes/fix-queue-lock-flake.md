- `ccx q` on Windows: the queue lock now waits when creating its lock file is denied (a file the last holder just
  unlinked is "delete pending" there, which raised PermissionError instead of FileExistsError and failed the write,
  so parallel `q run` items could come back as an error row with no run); releasing it retries a denied unlink
  instead of failing the write it guarded. A `q run` item that errors reports `status: failed` with the error (and
  `not_recorded` if writing that back failed too) instead of raising; a skipped item reports `status: todo`.
