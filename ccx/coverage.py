"""What a passed check actually covered: the test files its pytest / unittest command runs, and which of them the run
itself changed or wrote. Display only (the receipt, `ccx show`, the ledger); the verdict rules do not use it.

P1-10 (verdict audit, 2026-10-31): of the receipts that said ok but whose hidden tests failed, all 8 had a passed
check and a passed review, and the check did not reach the broken behaviour: 3 never ran the test file the hidden
test lives in, 5 ran a same-named file that the sub-agent had itself changed or written. A receipt that says
"check passed" should say what it passed on."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from .review import is_test_file

SHOWN = 20                                # file names kept in the record; n_files has the full count
_PARTS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
# pytest options that take a value as the next token (so that value is not a path)
_PYTEST_VAL = {"-k", "-m", "-p", "-c", "-o", "-W", "-r", "-n", "--rootdir", "--deselect", "--ignore", "--ignore-glob",
               "--maxfail", "--tb", "--junitxml", "--junit-xml", "--basetemp", "--confcutdir", "--override-ini",
               "--timeout", "--log-level", "--cov", "--cov-report", "--durations", "--import-mode", "--capture",
               "--log-cli-level", "--dist"}
_UNITTEST_VAL = {"-k", "-s", "-p", "-t", "--start-directory", "--pattern", "--top-level-directory"}
_SKIP_DIRS = {".git", ".ccx", ".ccx-worktrees", "node_modules", ".venv", "venv", "__pycache__", ".tox", "build",
              "dist", ".mypy_cache", ".pytest_cache"}


def _runner(toks: list[str]) -> tuple[str, list[str]] | None:
    """('pytest' | 'unittest', the arguments after it) for a command part that runs one, else None."""
    for i, t in enumerate(toks):
        name = t.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
        if name in ("pytest", "py.test"):
            return "pytest", toks[i + 1:]
        if t == "-m" and i + 1 < len(toks) and toks[i + 1] in ("pytest", "unittest"):
            return toks[i + 1], toks[i + 2:]
    return None


def targets(cmd: str) -> list[str] | None:
    """Paths the command's pytest / unittest runs name, relative to where it runs ('.' when it names none: the
    whole folder). None when no part of the command is pytest or unittest: then ccx cannot tell what it ran."""
    out: list[str] = []
    seen = False
    for part in _PARTS.split(cmd or ""):
        part = part.replace("\\", "/")            # Windows paths; shlex would read a backslash as an escape
        try:
            toks = shlex.split(part)
        except ValueError:
            toks = part.split()
        r = _runner(toks)
        if r is None:
            continue
        seen = True
        kind, args = r
        vals = _PYTEST_VAL if kind == "pytest" else _UNITTEST_VAL
        paths: list[str] = []
        skip = False
        start = None
        for k, t in enumerate(args):
            if skip:
                skip = False
                if kind == "unittest" and args[k - 1] in ("-s", "--start-directory"):
                    start = t
                continue
            if t.startswith("-"):
                if t in vals:
                    skip = True
                elif "=" in t and t.split("=", 1)[0] in ("--start-directory",):
                    start = t.split("=", 1)[1]
                continue
            if kind == "unittest":
                if t == "discover":
                    continue
                if "/" not in t and not t.endswith(".py"):
                    # a dotted module (tests.test_x, maybe .TestCase.test_y): the longest prefix that is a file
                    # is decided in covered(); keep the dotted name as a path guess
                    t = t.replace(".", "/")
            paths.append(t.split("::", 1)[0])
        if kind == "unittest" and not paths:
            paths = [start or "."]
        out.extend(paths or ["."])
    return list(dict.fromkeys(out)) if seen else None


def _rel(p: Path, repo: Path) -> str | None:
    try:
        return os.path.relpath(p.resolve(), repo.resolve()).replace("\\", "/")
    except ValueError:                        # another drive
        return None


def _resolve(t: str, cwd: Path) -> Path:
    """A target as a path under cwd; a unittest dotted name becomes the longest prefix that is a .py file."""
    p = cwd / t
    if p.exists() or t.endswith(".py"):
        return p
    parts = t.split("/")
    for k in range(len(parts), 0, -1):
        f = cwd.joinpath(*parts[:k]).with_suffix(".py")
        if f.is_file():
            return f
    return p


def covered(tgts: list[str], cwd: Path, repo: Path) -> tuple[list[str], list[str]]:
    """(test files the targets run, as repo paths; the targets that are folders, as repo paths)."""
    files: list[str] = []
    dirs: list[str] = []
    for t in tgts:
        p = _resolve(t, cwd)
        if p.is_dir():
            r = _rel(p, repo)
            if r is not None:
                dirs.append("." if r == "." else r.rstrip("/") + "/")
            for root, sub, names in os.walk(p):
                sub[:] = sorted(d for d in sub if d not in _SKIP_DIRS and not d.startswith("."))
                for n in sorted(names):
                    f = Path(root) / n
                    if n.endswith(".py") and is_test_file(n):
                        rf = _rel(f, repo)
                        if rf is not None and rf not in files:
                            files.append(rf)
        else:
            r = _rel(p, repo)
            if r is not None and r not in files:
                files.append(r)
    return files, dirs


def new_tests(diff: str) -> list[str]:
    """Test files the run created (a diff part from /dev/null)."""
    out: list[str] = []
    new = False
    for ln in diff.splitlines():
        if ln.startswith("--- "):
            new = ln[4:].strip() == "/dev/null"
        elif ln.startswith("+++ ") and new:
            f = ln[4:].strip()
            f = f[2:] if f.startswith("b/") else f
            if is_test_file(f) and f not in out:
                out.append(f)
            new = False
    return out


def _key(f: str) -> str:
    return f.replace("\\", "/").lstrip("./").lower()


def summarize(cmd: str, cwd: Path, repo: Path, edited: list[str], written: list[str]) -> dict:
    """The record's check["covers"]: {"files" (at most SHOWN), "n_files", "dirs"?, "edited"?, "written"?,
    "basis_changed"?, "own_tests_only"?}, or {"unknown": why} when the command is not pytest / unittest."""
    tgts = targets(cmd)
    if tgts is None:
        return {"unknown": "not a pytest / unittest command: which tests it ran is not known"}
    files, dirs = covered(tgts, cwd, repo)
    keys = {_key(f) for f in files}
    under = [_key(d) for d in dirs if d != "."] if "." not in dirs else [""]

    def inside(f: str) -> bool:
        k = _key(f)
        return k in keys or any(k.startswith(d) for d in under)
    ed = [f for f in edited if inside(f)]
    wr = [f for f in written if inside(f) and f not in ed]
    out: dict = {"files": files[:SHOWN], "n_files": len(files)}
    if dirs:
        out["dirs"] = dirs
    if ed:
        out["edited"] = ed
        out["basis_changed"] = True        # the check passed on tests the sub-agent changed: its own yardstick
    if wr:
        out["written"] = wr
    if files and {_key(f) for f in written} >= keys:
        out["own_tests_only"] = True       # every test the check runs is one the sub-agent wrote
    return out


def text(cov: dict | None, limit: int = 3) -> str:
    """'covers: a.py, b.py +2 more; basis changed: a.py (edited by the sub-agent)' for receipts and recaps."""
    if not cov:
        return ""
    if cov.get("unknown"):
        return "covers: not known (not pytest / unittest)"
    files = cov.get("files") or []
    n = cov.get("n_files", len(files))
    if cov.get("dirs") and n > limit:
        what = ", ".join(cov["dirs"][:limit]) + f" ({n} test files)"
    elif files:
        what = ", ".join(files[:limit]) + (f" +{n - limit} more" if n > limit else "")
    else:
        what = "no test file found"
    out = f"covers: {what}"
    if cov.get("basis_changed"):
        out += f"; basis changed: {', '.join(cov['edited'][:limit])} edited by the sub-agent"
    if cov.get("own_tests_only"):
        out += "; only tests the sub-agent wrote"
    elif cov.get("written"):
        out += f"; written by the sub-agent: {', '.join(cov['written'][:limit])}"
    return out
