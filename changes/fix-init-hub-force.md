- `ccx init --hub <folder>` no longer switches this machine to another hub without a word: when
  `~/.ccx/config.toml` already names a different hub it stops with exit 1 and prints the hub in use, the one asked
  for and what to do; `--force` (new) switches (nothing in the old hub is moved or deleted). The same goes for
  `--snapshot` / `--external-sync` that would replace a `layout.toml` with different content. Running it again with
  the same hub or the same values works as before. `ccx setup --hub` (which asks first) names the hub it replaces,
  and its printed step-by-step commands add `--force` when needed.
