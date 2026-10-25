- `ccx mem report [--days 14] [--json]` (H6): who wrote the shared notes that were used and who used them (a
  writer x user matrix), per project, by way of use (session start, search, a sub-agent's brief), and how many
  notes written in that time nobody used yet. `memory.mark_used` now records `by`, `project` and `via`; uses
  recorded before this count as `unknown`.
