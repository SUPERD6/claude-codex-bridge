- New setting `defaults.focused_retry` (default false): when ccx's `--check` fails after the sub-agent said done and
  the next rung is on the same agent, that attempt continues the same session with the failing command and the last
  ~2000 characters of its output, told to fix only what fails. Without a session id it starts fresh as before; the
  escalation ladder is unchanged. Off until a measured round shows it does not lower the right-rate.
- Independent review: the brief says ccx already ran the acceptance check ("You need not run it yourself", with the
  end of its output when ccx has it), and a Claude reviewer is asked for one plain git command per Bash call. No new
  permission: in r6a the refused reviewer calls were compound reads (`| head`, `cd && grep`), not test commands.
