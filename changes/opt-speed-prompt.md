- Sub-agents are told to iterate with targeted test runs (one file, `-x`, `-k NAME`) and run the full acceptance
  check once at the end, instead of re-running the whole check after every edit.
- `ccx run/resume --check` naming a test file that does not exist: a near-identical name (a typo) is swapped in with a
  one-line notice on stderr; otherwise the error also lists the test files that do exist.
