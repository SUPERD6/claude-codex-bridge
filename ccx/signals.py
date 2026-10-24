"""Objective signals about a task, measured from its brief and the folder — the same for anyone who reruns them.

They don't replace the lead's estimate; they fill rubric items the lead left out and are shown next to the ones it
gave, so a lead that says "1 file" for a brief naming five can be seen (and its bias learned)."""
from __future__ import annotations

import re
from pathlib import Path

_PATH = re.compile(r"[\w./\-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|kt|c|cc|cpp|h|hpp|cs|rb|php|swift|md|toml|json|ya?ml|sh|ps1)\b")


def measure(brief: str, cwd: Path) -> dict:
    files, lines, dirs, tested = [], 0, set(), 0
    for tok in dict.fromkeys(_PATH.findall(brief or "")):
        f = (cwd / tok).resolve() if not Path(tok).is_absolute() else Path(tok)
        try:
            if not f.is_file() or cwd.resolve() not in f.parents:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.append(tok)
        lines += text.count("\n") + 1
        rel = f.relative_to(cwd.resolve())
        dirs.add(rel.parts[0] if len(rel.parts) > 1 else ".")
        stem = f.stem
        if stem.startswith("test_") or any((cwd / d).is_dir() and any((cwd / d).rglob(f"test*{stem}*"))
                                           for d in ("tests", "test")):
            tested += 1
    if not files:
        return {}
    n = len(dirs)
    return {"files_named": len(files), "lines": lines, "dirs": sorted(dirs), "with_tests": tested,
            "suggests": {"files": len(files), "coupling": "one" if n <= 1 else "cross" if n <= 3 else "system"}}
