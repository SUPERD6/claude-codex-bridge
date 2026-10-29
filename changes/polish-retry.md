- New setting `defaults.focused_retry` (default false): when ccx's `--check` fails after the sub-agent said done and
  the next rung is on the same agent, that attempt continues the same session with the failing command and the last
  ~2000 characters of its output, told to fix only what fails. Without a session id it starts fresh as before; the
  escalation ladder is unchanged. Off until a measured round shows it does not lower the right-rate.
