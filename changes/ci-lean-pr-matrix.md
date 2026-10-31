- CI: a pull request runs Windows 3.11 + Ubuntu 3.13 and the package check on Ubuntu; a push to main, a version tag
  or a run by hand runs the full matrix (3 OS × 3.11–3.13, package on 3 OS); pushes to other branches no longer run
  (their PR does). Job names no longer carry the matrix's `full` flag (`test (windows-latest, 3.11)`), so the
  branch protection's required checks have to be renamed with it.
- CONTRIBUTING (both languages) gains a test rule: time comes in as a parameter, no written-out dates measured
  against a window, concurrency tested with a fixed interleaving and real processes on one repository run one after
  another (examples: #193, #190).
