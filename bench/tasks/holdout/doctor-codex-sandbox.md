# doctor-codex-sandbox

Set: `holdout`. hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it is no longer a hold-out set (see bench/README.md).

| | |
|---|---|
| Repository | this one (https://github.com/SUPERD6/relayline) |
| Commit (the reference change) | `883be56` |
| Starting point | its parent, `883be56^`, plus today's `tests/conftest.py` |
| Area | doctor |
| Reference size | 55 non-test lines in 2 file(s) |

## Brief

The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / `LEAD_PROMPT_EXT` in scripts/eval/r5.py).

A Codex lead working in its sandbox cannot use `ccx run`: ccx writes run records into the hub, and the sub-agent
CLI it starts needs the network. Codex's `workspace-write` sandbox blocks both unless it is configured, and on
Windows even a configured workspace-write did not work in real runs (only `danger-full-access` did). `ccx doctor`
should say so, and a permission error from a ccx command should point there.

Interface:
- `ccx.doctor.codex_lead_sandbox(config_text: str, hub, windows: bool | None = None) -> tuple[str, str]`:
  (state, detail) from the text of Codex's `config.toml`; `windows` defaults to whether this is Windows. The state
  is `ok`, `WARN` or `Unknown`.
  - `sandbox_mode = "danger-full-access"`: `ok`.
  - On Windows anything else: `WARN`, and the detail says to give lead sessions `danger-full-access` (e.g. a
    profile).
  - Elsewhere `read-only` is `WARN`. `workspace-write`, or no `sandbox_mode` at all (Codex then decides; check it
    as workspace-write and say it is "not set"), is `ok` only when `[sandbox_workspace_write]` lists the hub or a
    folder above it in `writable_roots` and has `network_access = true`. Otherwise `WARN`: the detail names each
    missing part ("the hub is not a writable root", "network_access is off") and gives the exact lines to add, with
    the hub path written with forward slashes.
  - Text that is not valid TOML: `Unknown`.
- `ccx doctor` shows a row "Codex as lead (sandbox)" from it when `codex` is installed.
- When a command fails with a PermissionError, the error JSON also gets a `hint` that points to that doctor row.

## Acceptance (hidden tests)

The commit's own test file(s), read from this repository's history: `git show 883be56:tests/test_codex_lead_sandbox.py`. They are written over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:

```bash
python -m pytest -q -p no:cacheprovider tests/test_codex_lead_sandbox.py
```

Right = that command exits 0. The tests are public (they always were, in the commit's history), so an agent that looks the commit up can find the answer; the evaluation denies web access and the copies of other repositories to its agents, but a model may still remember an older commit.
