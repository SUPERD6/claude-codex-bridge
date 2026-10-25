- H15: `scripts/eval/preflight_e2e.py`, a release preflight on the real CLIs with tiny tasks, judged by files, records
  and the ledger: delegate (Claude-led task to a Codex sub-agent, hidden test passes), followup (`ccx resume`, same
  session), stop (`ccx stop`: stopped, counted, one ledger row, then `ccx resume` on the same session), undo,
  handoff (written, shown by the receiving start hook, and a model given that names the next task), and with
  `--agents all` also review and the Codex -> Claude direction. A throwaway hub, `eval-preflight:` labels, `--no-ab`,
  and a spend cap (default $0.50) read from that hub's ledger after every step.
  First full pass, Codex only (gpt-6-luna low): all five steps passed for $0.013. A real stop -> resume from an
  earlier pass: stopped run `20261025-113353-a5b3`, ledger row `{"kind": "user_stopped", "ae_usd": 0.002088,
  "usage4": {"input_tokens": 20049, "cached_input_tokens": 0, "output_tokens": 167}, "sessions":
  ["01a173b2-67c3-7723-9a0d-2397972498e7"]}`, resumed as `20261025-113359-8b50` in that same session.
- `ccx resume --review auto|on|off`, as `ccx run` has. A write follow-up was always reviewed `auto`, so a Codex-only
  preflight called Claude (haiku) for the review.
