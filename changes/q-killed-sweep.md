- `ccx q`: when the whole `q run` process tree was killed, the run in progress stayed `running` and its spend never
  reached the ledger or the item (r2 group 9, 4-I). `q run`, `q resume` and `q ls` now close such runs as
  interrupted first (`recover.sweep`, as `ccx stats` does, with the usage read back from the session file), and
  `q resume` adds what the item's runs since it went `doing` spent to its `cost_usd`.
