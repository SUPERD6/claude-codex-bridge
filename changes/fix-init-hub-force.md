- `ccx init --hub <folder>` no longer switches this machine to another hub without a word: when
  `~/.ccx/config.toml` already names a different hub (or does not parse, so the hub it meant is unknown) it stops
  with exit 1 and prints the hub in use, the one asked for and what to do; `--force` (new) switches (nothing in the
  old hub is moved or deleted). The same goes for `--snapshot` / `--external-sync` that would replace a
  `layout.toml` with different content. The same hub again (on Windows in any letter case) works as before. The
  install scripts pass it on (`install.ps1 -Force`, `install.sh <hub> --force`). `ccx setup --hub` names the hub it
  replaces and asks first; `ccx setup --yes` does not switch hubs (it stops and prints the `--force` command); its
  step-by-step commands off a terminal add `--force` when needed.
