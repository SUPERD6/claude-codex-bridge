- New setting `defaults.focused_retry` (default false): when ccx's `--check` fails after the sub-agent said done and
  the next rung is on the same agent, that attempt continues the same session with the failing command and the last
  ~2000 characters of its output, told to fix only what fails. Without a session id it starts fresh as before; the
  escalation ladder is unchanged. Off until a measured round shows it does not lower the right-rate.
- Independent review: the brief says ccx already ran the acceptance check ("You need not run it yourself", with the
  end of its output when ccx has it), and a Claude reviewer is asked for one plain git command per Bash call. No new
  permission: in r6a the refused reviewer calls were compound reads (`| head`, `cd && grep`), not test commands.
- `ccx -h`: show and q join Everyday; where, projects, intake, init, uninstall, repair and agents move to a new
  Advanced group; trial, ab, bench, improve and namecheck move to a Developer group listed last. Every command is
  still callable.
- `ccx ui`: a run that stopped on an environment failure (`kind: env`) shows its fix hint and `ccx doctor` instead of
  "Try again". An empty overview says what to run first (the same first delegation as README and `ccx setup`) and,
  once this ccx has it, `ccx demo`.
- `ccx sync` dry run: a missing Codex `config.toml` is one line ("will create ... with the hook block") instead of an
  "add hook block" line plus "nothing to import"; a file that does not exist yet says "create" rather than "update
  managed block". A community lead (dsh) found only inside its installed app, not on PATH, is no longer connected by
  default (one optional note instead); one connected before keeps its block, and `ccx uninstall` still removes it.
- `ccx doctor`: rows about ccx's own workings (python, tiers.toml, ccx config, hub format, hub layout, routing prior,
  tier policy, hook timeouts) show only when they are not ok, or with the new `--verbose`; one line says how many
  were left out.
