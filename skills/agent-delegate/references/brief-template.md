# Brief template (aim for ≤ 200 words)

```
Goal: <one sentence, the outcome, not the steps>
Look at: <paths/dirs; the sub-agent reads them itself>
Constraints: <don't touch X; keep API Y; style Z>
Done when: <observable condition, e.g. `pytest tests/test_io.py` passes>
Report: list files changed; say exactly what you verified.
```

Good
```
Goal: make load_csv() accept a `delimiter` argument (default ",").
Look at: src/io/loader.py, tests/test_loader.py
Constraints: no new dependencies; keep the public signature otherwise unchanged.
Done when: new test for ";" delimiter passes with `pytest tests/test_loader.py -q`.
```

Bad (wastes tokens both ways)
- pasting the whole file or chat history into the brief
- "fix everything that looks wrong" (no boundary → long, expensive run)
- re-explaining project background that belongs in .ccx/context.md
