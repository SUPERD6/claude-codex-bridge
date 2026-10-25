- The board (core 2, part 1): `ccx say --to claude|codex|deepseek|all "..."`, `ccx reply <id> "..."` and
  `ccx board [--thread T]` let open Claude Code, Codex and DeepSeek sessions in one project write to each other.
  Messages go to `.ccx/board.jsonl` (append-only, locked, fsynced, git-ignored); each reader (vendor, or
  vendor:session) has its own cursor, so a turn sees only what is new and for it. At most 6 machine messages in a row
  per thread (`board.max_machine_turns`) until a person speaks; every line records who wrote it and what ccx detected;
  an agent cannot write as the person. Design: docs/board.md. Delivery every turn comes in the next PR.
