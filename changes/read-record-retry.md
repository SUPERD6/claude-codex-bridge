- Windows: reading a run record retries for up to 3 s when the run is replacing it at that moment (the read side of
  the write retry): a test polling a live run failed once in CI with PermissionError on `run.json`. `ccx` itself
  reads records through `ledger.read_record` (show, stop, the interrupted-run sweep).
