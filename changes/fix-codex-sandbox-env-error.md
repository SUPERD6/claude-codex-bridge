- Codex's Windows sandbox prompt cancelled (error 1223) is an environment failure again: codex-cli 0.164.0 wraps the
  launcher's error as `CreateProcess { message: "Rejected(\"... orchestrator_helper_launch_canceled: ShellExecuteExW
  failed to launch setup helper: 1223\")" }`, and ccx skipped every line with "Rejected" as a policy refusal, so a run
  climbed to the next rung in the same session and the lead resumed it (2026-10-31 eval: 13 units, 800-1650 s each).
  Only "blocked by policy" is skipped now; such a run stops after one attempt with `kind: env`, its `env_error` keeps
  the error code, the hint and `needs_lead` say "sub-agent environment problem: sandbox authorization was cancelled
  (Windows error 1223)", and `ccx ui` shows it in its own words (zh/en).
