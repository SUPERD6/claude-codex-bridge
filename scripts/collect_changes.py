"""Fold the per-PR notes in changes/ into CHANGELOG.md (run when releasing, or to tidy Unreleased).

Each PR adds one file, changes/<PR>.md, holding its CHANGELOG lines ("- ..." bullets, wrapped as in CHANGELOG.md),
instead of editing CHANGELOG.md itself: parallel PRs then never conflict on it. This script puts the notes, oldest
PR first, under "## Unreleased" (after what is already there), or with --version turns Unreleased into a release
heading. Dry run by default: prints the new CHANGELOG; --apply writes it and deletes the folded notes.

  python scripts/collect_changes.py                       # preview
  python scripts/collect_changes.py --version 0.5.0 --title "..." --apply
"""
import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"README.md", "README.zh.md"}


def notes(folder):
    """The notes in folder, numbered ones (PR numbers) first in order, then the rest by name."""
    files = [p for p in folder.glob("*.md") if p.name not in SKIP]
    return sorted(files, key=lambda p: (0, int(p.stem), "") if p.stem.isdigit() else (1, 0, p.stem))


def check(path):
    """Problems with one note: it must be non-empty and every entry a "- " bullet (continuations indented)."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return [f"{path.name}: empty"]
    return [f"{path.name}:{i}: start an entry with '- ' (or indent a continuation)"
            for i, line in enumerate(text.splitlines(), 1)
            if line.strip() and not line.startswith(("- ", "  "))]


def fold(changelog, entries, version=None, title=None, date=None):
    """changelog with entries appended to Unreleased; with version, Unreleased becomes that release."""
    m = re.search(r"^## Unreleased[^\n]*\n", changelog, re.M)
    if not m:
        raise SystemExit("CHANGELOG.md has no '## Unreleased' heading")
    nxt = re.search(r"^## ", changelog[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(changelog)
    body = changelog[m.end():end].strip("\n")
    body = "\n".join(x for x in [body] + entries if x)
    head = "## Unreleased\n"
    if version:
        head = f"## Unreleased\n\n## {version} — {date or dt.date.today().isoformat()}"
        head += f" ({title})\n" if title else "\n"
    return changelog[:m.start()] + head + body + "\n\n" + changelog[end:].lstrip("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--version", help="turn Unreleased into this release, e.g. 0.5.0")
    ap.add_argument("--title", help="short summary after the release date")
    ap.add_argument("--date", help="release date (default today)")
    ap.add_argument("--check", action="store_true", help="only check the notes' format")
    ap.add_argument("--apply", action="store_true", help="write CHANGELOG.md and delete the folded notes")
    a = ap.parse_args(argv)
    files = notes(a.root / "changes")
    problems = [p for f in files for p in check(f)]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if a.check:
        print(f"{len(files)} note(s) ok")
        return 0
    path = a.root / "CHANGELOG.md"
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    new = fold(raw.replace("\r\n", "\n"), [f.read_text(encoding="utf-8").strip() for f in files],
               a.version, a.title, a.date)
    if not a.apply:
        sys.stdout.write(new)
        return 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new.replace("\n", eol))
    for f in files:
        f.unlink()
    print(f"folded {len(files)} note(s) into CHANGELOG.md" + (f" as {a.version}" if a.version else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
