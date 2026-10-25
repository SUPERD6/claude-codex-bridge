- `ccx stop <run_id>` stops a running delegation and keeps it resumable. Sub-agents now start in their own process
  group (Windows `CREATE_NEW_PROCESS_GROUP`, POSIX `start_new_session`), and the run record keeps the child's pid,
  ccx's own pid and the host. Stop writes `<run>/stop.request` and kills the whole tree (`taskkill /T /F`,
  `os.killpg`); the run's own ccx writes the final state (`state=stopped`, `kind=user_stopped`, nothing learned) and
  its one ledger row. Only when that process is gone does stop close the record itself; `final.lock` makes sure only
  one of them does. A stop that lands as the sub-agent finishes keeps the finished result. Timeouts, the spending
  cap and Ctrl+C now kill the whole tree too: a grandchild holding stdout open no longer hangs the run.
