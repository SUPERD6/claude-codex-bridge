- `ccx run --effort X` without `--model` (or `--provider`) prints one line on stderr saying the effort is not used:
  the route picks the model and its effort (2026-10-31 new-machine walkthrough: `--effort medium` kept
  `codex:gpt-6-luna:low` and nothing said so). Behaviour and the JSON result are unchanged; `ccx run -h` says the same.
  The project-manager skill's cheap draft review now says `--tier T1` instead of an `--effort low` that was never used.
  docs/install: how to install without pipx (a virtual environment, macOS/Linux and Windows PowerShell).
