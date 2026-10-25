- `ccx doctor` warns on version drift (I8): when an agent CLI's installed major.minor differs from the adapter's
  `tested_version`, a `<agent> version` row says so; for an official adapter it asks for the release check (H15: real
  read, write and resume runs on that version), for a community one it says not verified on that version.
- `ccx/agents/_template.py` and `tests/fakes/fake_template.py`: a working skeleton for a new agent CLI (not
  registered), run end to end by `tests/test_agent_template.py`. CONTRIBUTING (EN + ZH) points at it; its step 1 no
  longer names the old `runners.py` tables. README (EN + ZH) explains official vs community.
- `ccx doctor` notices OpenAI's codex-plugin-cc (J8): installed or enabled in Claude Code (`codex@openai-codex`), it
  reports `info` (its SessionStart/SessionEnd/Stop hooks run beside ccx's) and `WARN` if ccx's own SessionStart hook
  is there more than once. README's "can be used side by side" now says not tested together yet.
