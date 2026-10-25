- Shared memory (proposal L, L1–L3). `ccx mem search` ranks notes by BM25 (rare words count more, not every word
  is needed; `--all-words` keeps the old filter, `--limit N`, default 10). Five fixed kinds — preference,
  constraint, fact, pitfall, event, plus other: `ccx mem add --kind`, older notes guessed from topic and words when
  read (`ccx mem kinds --list`). `ccx mem compact --by project` writes one short block per project to
  `memory/scenes.md`. New `[memory]` settings, both off until the H11 trial ends on 2026-11-01: `by_kind` (a start
  carries new preferences and constraints only, briefs pick by BM25 without events) and `start_scene` (a start adds
  this project's block); `ccx config set memory.by_kind true`. On a fixed 40-note, 10-query set
  (`tests/memory_bench.py`), relevant notes in the first 3: search 7 → 11 of 13, briefs 11 → 12.
