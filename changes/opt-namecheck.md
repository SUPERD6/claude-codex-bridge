- `namecheck`: after a write run, a static check (stdlib `ast` + `symtable`, a few ms a file) of the functions the
  run changed for names no scope defines, i.e. a NameError waiting on that path. Round 5 shipped two such bugs past
  passing tests (an import missing behind `except Exception`). Default `warn`: hits go to the record (`namecheck`),
  the compact result and the review brief as weak evidence, and keep the run from the 12 h probable verdict;
  `fail` turns a hit into `check_failed` (check `ccx namecheck --run <id>`, reason `namecheck`; the acceptance
  command is not run, and with a rung left it climbs like a failed check); `off`. Set by `[defaults] namecheck` or
  `ccx run|resume --namecheck`; `ccx resume` keeps the mode the run was started with. New command `ccx namecheck`
  (a run's changes with `--run`, the working tree since `--base`, or whole files; exit 1 on a hit). Per-function resolution, annotations never checked, a fixed builtins set (same
  verdict on 3.11-3.13), BOM-safe, files with star imports, `exec`, `globals()`, module-level `vars()`/`locals()`,
  `sys.modules[__name__]`, builtins writes, enum exports or `import cython` skipped; a name imported only under
  `TYPE_CHECKING` and read at run time is reported; a function counts when its lines changed or it uses a module
  name the run removed.
- `review.changes` names files from the repo root and unquoted (`--full-name`, `core.quotepath=off`): a new file
  in a subfolder run, or a non-ASCII path, was missed or read from the wrong place by the review and the namecheck.
