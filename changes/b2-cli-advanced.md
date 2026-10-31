- Help regrouped, nothing removed (B2): `ccx -h` lists only the everyday commands (setup, doctor, run, ask, resume,
  stop, undo, verify, show, q, ui, mem, lead, demo). New `ccx advanced` prints every group (same as `ccx -h --all`);
  the Advanced group now holds the hub, several-projects and install commands (init, projects, where, intake, sync,
  config, uninstall, repair, agents). New `ccx dev` lists the developer commands, and `ccx dev <command> ...` runs
  one exactly as `ccx <command> ...`. Rarely used options of `ccx resume`, `ccx verify` and `ccx lead` sit under an
  "advanced" heading in their help. Every command, option and positional keeps its name and parses as before:
  `tests/data/cli_surface.json` froze the full list and `tests/test_cli_surface.py` fails if any of it disappears.
  The top description no longer says ccx routes to "the cheapest agent".
