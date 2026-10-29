- Eval clean room (scripts/eval): `--codex-home` is made absolute when parsed and a relative path is refused (r6a:
  `../x` passed preflight but every Codex resolved it from its unit's work dir and failed). Eval Codex runs
  (CCX_CODEX_ISOLATE=1 only) turn off the `plugins`, `remote_plugin` and `apps` features, the eval config.toml gets
  the same `[features]`, a starting run removes the remote plugins codex-cli 0.164 synced into `plugins/`, and the
  home is checked again after every unit (plugins, skills, features, connector / plugin catalog caches): a change
  stops the run. Rows of r5.py and batch.py record `codex_home_after`; rows record `fingerprint.codex_cli` and
  `codex_features_off`. A check-only preflight no longer fails after the canary on a home whose `[features]` table
  a starting run would write.
