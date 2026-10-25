- `scripts/eval/seven_ab.py`: the memory group has a third arm, `hubmem`: the same note only in the shared hub
  journal (`ccx mem add`), nothing in the repo. Every memory unit runs in its own throwaway `CCX_HUB`, so the
  person's hub is never read or written and no other note reaches the brief; each unit records `note_in_prompt`
  (the note was in the sub-agent's first prompt). The summary reports it as `memory:hubmem` (nomem -> hubmem),
  outside the Holm family of the four primary comparisons. Real run (codex gpt-6-luna low, 3 tasks x 3 rounds,
  paired with round 1's `nomem` units, $0.025): hidden test passed 9/9 vs 0/9 (McNemar p = 0.0039), the note was in
  the prompt 9/9; median $0.0030 vs $0.0019 and 29.5 s vs 23.5 s per unit. Limits: the control is round 1's (an
  earlier batch, before the I6 fix, the person's hub instead of an empty one), the tasks are made so the brief
  leaves out exactly what the note says, and each hub held just that one note; nothing here measures picking the
  right note among many.
