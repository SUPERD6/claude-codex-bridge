- `namecheck`: after a write run, a static check (stdlib `ast` + `symtable`, a few ms a file) of the functions the
  run changed for names no scope defines, i.e. a NameError waiting on that path. Round 5 shipped two such bugs past
  passing tests (an import missing behind `except Exception`). Default `warn`: hits go to the record (`namecheck`),
  the compact result and the review brief as weak evidence, and keep the run from the 12 h probable verdict;
  `fail` turns a hit into `check_failed` (check `ccx namecheck`, reason `namecheck`; the acceptance command is not
  run, and with a rung left it climbs like a failed check); `off`. Set by `[defaults] namecheck` or
  `ccx run|resume --namecheck`. Per-function resolution, annotations never checked, a fixed builtins set (same
  verdict on 3.11-3.13), BOM-safe, files with star imports, `exec`, `globals()`, builtins writes, enum exports or
  `import cython` skipped; a function counts when its lines changed or it uses a module name the run removed.
