"""The person's project catalog: every project under the roots they name, found by code (no model, no network).

    [projects] roots = [...]    in <hub>/ccx/tiers.toml or `ccx config set projects.roots "DIR;DIR"` (default empty)
    <hub>/ccx/projects.json     the catalog; this machine only, never in a repository, never uploaded

A project is a folder with `.git`, or with AGENTS.md / CLAUDE.md / a build file (pyproject.toml, package.json, ...),
or with a README right under a root. A folder marked only by rule files that holds projects of its own is a group
(its rules are inherited by the projects inside, so they are listed as "read first" too). Git repositories are not
entered; dependency, build, worktree, topics and archive folders are skipped. A link or junction to a folder
already seen is recorded once, under `also_at`.

Each entry: name, path, a one-line summary (README / AGENTS first paragraph), aliases (folder, titles, git remote,
package name, Chinese names in titles), rule files, state files (STATUS, handoff, .ccx/context.md, topics/),
last activity, and what was done lately (latest commit subjects, project journal lines)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

RULE_FILES = ("AGENTS.md", "CLAUDE.md")
BUILD_FILES = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "setup.py", "pom.xml", "build.gradle",
               "CMakeLists.txt", "Makefile", "requirements.txt", "environment.yml")
README_NAMES = ("README.md", "README.zh.md", "README_zh.md", "README.rst", "README.txt", "README", "readme.md")
SKIP_DIRS = {"node_modules", "venv", "env", "__pycache__", "site-packages", "dist", "build", "target", "worktrees",
             "archives", "archive", "topics", "docs", "tests", "test", "src", "lib", "outputs", "data", "scripts",
             "assets", "vendor", "backups", "backup", "third_party", "bin", "obj", "out", "logs", "tmp", "temp", "cache"}
STATE_FILES = ("docs/STATUS.md", "STATUS.md", ".ccx/handoff.md", ".ccx/context.md", "HANDOFF.md", "TODO.md")
MAX_DEPTH = 5
CJK = re.compile(r"[㐀-鿿豈-﫿]{2,}")


def store(p) -> Path:
    return p.state / "projects.json"


def configured_roots(cfg: dict) -> list[str]:
    v = (cfg.get("projects") or {}).get("roots") or []
    if isinstance(v, str):
        v = [x for x in re.split(r"[;\n]", v)]
    return [str(x).strip() for x in v if str(x).strip()]


def load(p) -> dict:
    f = store(p)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(p, cat: dict) -> Path:
    f = store(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return f


# ---- reading one folder ----

def _names(d: Path) -> tuple[set[str], list[str]]:
    """(file names, sub-folder names) of d; empty when it can't be read."""
    files, dirs = set(), []
    try:
        with os.scandir(d) as it:
            for e in it:
                try:
                    is_dir = e.is_dir()
                except OSError:
                    continue
                if is_dir:
                    dirs.append(e.name)
                else:
                    files.add(e.name)
    except OSError:
        pass
    return files, sorted(dirs)


def _kind(files: set[str], dirs: list[str], depth: int) -> str | None:
    if ".git" in files or ".git" in dirs:
        return "git"
    if any(f in files for f in RULE_FILES + BUILD_FILES):
        return "marked"
    if depth == 1 and any(f in files for f in README_NAMES):
        return "marked"
    return None


def _read(f: Path, limit: int = 20000) -> str:
    try:
        return f.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _plain(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)               # images
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)           # links -> their text
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


def title_and_summary(text: str) -> tuple[str, str]:
    """The first `# ` heading and the first paragraph of prose (badges, html, code, imports and rules skipped)."""
    title, para, fence = "", [], False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith("#"):
            if not title and line.startswith("# "):
                title = _plain(line[2:])
            if para:
                break
            continue
        if not line:
            if para:
                break
            continue
        if line.startswith(("<!--", "[![", "![", "<", "@", "---", "===", "|", "-->")):
            continue
        if (" | " in line and len(_plain(line)) < 40) or line.count(" · ") >= 3:
            continue                    # a language switch: "[中文](README.zh.md) | English"
        para.append(line.lstrip("> ").strip())
    s = _plain(" ".join(para))
    if len(s) > 220:
        s = s[:217].rstrip() + "..."
    return title, s


def _git(d: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _remote_name(d: Path) -> str:
    cfg = _read(d / ".git" / "config") if (d / ".git").is_dir() else ""
    m = re.search(r"\[remote \"[^\"]+\"\][^\[]*?url\s*=\s*(\S+)", cfg)
    if not m:
        return ""
    return re.sub(r"\.git$", "", m.group(1).rstrip("/").replace(":", "/").rsplit("/", 1)[-1])


def _package_name(d: Path, files: set[str]) -> str:
    if "package.json" in files:
        try:
            return str(json.loads(_read(d / "package.json")).get("name") or "")
        except ValueError:
            pass
    if "pyproject.toml" in files:
        m = re.search(r'(?m)^name\s*=\s*"([^"]+)"', _read(d / "pyproject.toml"))
        if m:
            return m.group(1)
    return ""


def _commands(d: Path, files: set[str]) -> list[str]:
    """The commands a project installs (pyproject [project.scripts], package.json bin): what people call it by."""
    out: list[str] = []
    if "pyproject.toml" in files:
        import tomllib
        try:
            out += list((tomllib.loads(_read(d / "pyproject.toml")).get("project") or {}).get("scripts") or {})
        except ValueError:
            pass
    if "package.json" in files:
        try:
            b = json.loads(_read(d / "package.json")).get("bin")
            out += list(b) if isinstance(b, dict) else []
        except ValueError:
            pass
    return out[:5]


def _journal_tail(d: Path, n: int = 3) -> list[str]:
    out = []
    for line in _read(d / ".ccx" / "journal.jsonl", 400000).splitlines()[-n:]:
        try:
            t = str(json.loads(line).get("text") or "")
        except ValueError:
            continue
        if t:
            out.append(t[:160])
    return out


def _mtime(d: Path, files: set[str]) -> float:
    best = 0.0
    for name in list(files)[:200]:
        try:
            best = max(best, (d / name).stat().st_mtime)
        except OSError:
            continue
    return best


def _aliases(name: str, titles: list[str], extra: list[str]) -> list[str]:
    out: list[str] = []

    def add(x: str) -> None:
        x = x.strip(" -—:：()（）[]")
        if x and len(x) <= 60 and x.casefold() not in {a.casefold() for a in out}:
            out.append(x)
    add(name)
    for t in titles:
        if not t:
            continue
        add(re.split(r"\s+[—–-]\s+|[:：（(]", t)[0])
        for cjk in CJK.findall(t):
            add(cjk)
        for m in re.findall(r"\(formerly ([^)]+)\)", t):
            add(m)
    for x in extra:
        if x:
            add(x)
    return out


def _worked_in(d: Path, files: set[str], dirs: list[str]) -> bool:
    return ".ccx" in dirs or "topics" in dirs or any((d / f).exists() for f in STATE_FILES)


def describe(d: Path, files: set[str], dirs: list[str], inherited: list[str], kind: str) -> dict:
    readme = next((d / f for f in README_NAMES if f in files), None)
    titles, summary = [], ""
    for f in [readme] + [d / r for r in RULE_FILES if r in files] + \
             [d / z for z in ("README.zh.md", "README_zh.md") if z in files]:
        if f is None:
            continue
        t, s = title_and_summary(_read(f))
        titles.append(t)
        summary = summary or s
    keywords = []                       # titles of the READMEs one level down (pet/README.md: "Desk pet ...")
    for name in dirs:
        if name.startswith(".") or name.casefold() in SKIP_DIRS - {"docs", "src"}:
            continue
        sf, _ = _names(d / name)
        sr = next((d / name / f for f in README_NAMES if f in sf), None)
        if sr:
            t, s = title_and_summary(_read(sr, 6000))
            if t:
                keywords.append(t)
            summary = summary or s
        if len(keywords) >= 8:
            break
    own_rules = [str(d / r) for r in RULE_FILES if r in files]
    commits, last = [], 0.0
    if kind == "git":
        for line in _git(d, "log", "-5", "--format=%ct%x1f%s").splitlines():
            ts, _, subj = line.partition("\x1f")
            if ts.isdigit():
                last = max(last, float(ts))
                commits.append(subj.strip()[:120])
    journal = _journal_tail(d)
    jf = d / ".ccx" / "journal.jsonl"
    if jf.exists():
        last = max(last, jf.stat().st_mtime)
    last = max(last, _mtime(d, files))
    topics = []
    if "topics" in dirs:
        topics = _names(d / "topics")[1][:40]
    return {
        "name": d.name,
        "path": str(d),
        "summary": summary,
        "aliases": _aliases(d.name, titles, [_remote_name(d), _package_name(d, files),
                                                     *_commands(d, files)]),
        "rules": own_rules + [r for r in inherited if r not in own_rules],
        "state": [s for s in STATE_FILES if (d / s).exists()] + (["topics/"] if topics else []),
        "topics": topics,
        "git": kind == "git",
        "last_active": int(last),
        "recent": commits[:3],
        "journal": journal,
        "keywords": keywords,
    }


# ---- walking the roots ----

def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def scan(roots: list[str], max_depth: int = MAX_DEPTH) -> dict:
    found: dict[str, dict] = {}         # normcase(real path) -> entry
    links: list[tuple[Path, int, list[str]]] = []
    missing: list[str] = []
    walked: list[str] = []

    def walk(d: Path, depth: int, inherited: list[str]) -> int:
        """Record the projects inside d (d itself excluded); how many of them are d's direct children."""
        direct = 0
        real_d = os.path.realpath(d)
        _, dirs = _names(d)
        for name in dirs:
            if name.startswith(".") or name.casefold() in SKIP_DIRS:
                continue
            c = d / name
            real = os.path.realpath(c)
            if not _same(real, os.path.join(real_d, name)):
                links.append((c, depth + 1, inherited))
                continue
            key = os.path.normcase(real)
            if key in found:
                continue
            files, sub = _names(c)
            kind = _kind(files, sub, depth + 1)
            rules = [str(c / r) for r in RULE_FILES if r in files]
            if kind == "git":
                found[key] = describe(c, files, sub, inherited, kind)
                direct += 1
                continue
            before = set(found)
            inner = walk(c, depth + 1, rules + inherited) if depth + 1 < max_depth else 0
            if kind and (not inner or _worked_in(c, files, sub)):
                # a project (its own repositories inside, e.g. shared/source/X, stay projects of their own); a
                # folder with projects right inside it and no work of its own (.ccx, topics, STATUS) is a group
                found[key] = describe(c, files, sub, inherited, kind)
                direct += 1
                for k in set(found) - before - {key}:
                    found[k].setdefault("parent", found[key]["name"])
        return direct

    for r in roots:
        root = Path(r).expanduser()
        if not root.is_dir():
            missing.append(str(root))
            continue
        walked.append(os.path.realpath(root))
        files, _ = _names(root)
        walk(root, 0, [str(root / x) for x in RULE_FILES if x in files])
    for c, depth, inherited in links:
        real = os.path.realpath(c)
        key = os.path.normcase(real)
        if key in found:
            found[key].setdefault("also_at", []).append(str(c))
            continue
        if any(os.path.normcase(real).startswith(os.path.normcase(w) + os.sep) or _same(real, w) for w in walked):
            continue                    # a link into a root: what it points at was (or will be) walked there
        if not Path(real).is_dir():
            continue
        files, sub = _names(c)
        kind = _kind(files, sub, depth)
        if kind:
            e = describe(Path(real), files, sub, inherited, kind)
            e["also_at"] = [str(c)]
            found[key] = e
    projects = sorted(found.values(), key=lambda e: -e["last_active"])
    _unique_names(projects)
    return {"scanned_at": int(time.time()), "roots": [str(Path(r).expanduser()) for r in roots],
            "missing_roots": missing, "projects": projects}


def _unique_names(projects: list[dict]) -> None:
    """Two folders with one name become parent/name (the catalog's names are what people type)."""
    by: dict[str, list[dict]] = {}
    for e in projects:
        by.setdefault(e["name"].casefold(), []).append(e)
    for same in by.values():
        if len(same) > 1:
            for e in same:
                e["name"] = f"{Path(e['path']).parent.name}/{Path(e['path']).name}"


def refresh(p, cfg: dict, roots: list[str] | None = None) -> dict:
    """Scan the given roots (else the configured ones, else the ones the last scan used) and save the catalog."""
    roots = roots or configured_roots(cfg) or load(p).get("roots") or []
    if not roots:
        raise ValueError('no project roots: `ccx config set projects.roots "DIR;DIR"`, or '
                         "`ccx projects scan --root DIR`")
    depth = int((cfg.get("projects") or {}).get("max_depth") or MAX_DEPTH)
    cat = scan(roots, depth)
    save(p, cat)
    return cat


def find(cat: dict, name: str) -> dict | None:
    """The entry whose name, alias or path is exactly `name` (case-insensitive); None if none or several."""
    want = name.strip().casefold()
    hits = [e for e in cat.get("projects") or []
            if want == e["name"].casefold() or want in (a.casefold() for a in e.get("aliases") or [])
            or _same(want, e["path"]) or any(_same(want, x) for x in e.get("also_at") or [])]
    exact = [e for e in hits if e["name"].casefold() == want]
    return (exact or hits)[0] if len(exact or hits) == 1 else None


def brief_row(e: dict) -> dict:
    return {"name": e["name"], "summary": (e.get("summary") or "")[:90],
            "last_active": time.strftime("%Y-%m-%d", time.localtime(e["last_active"])) if e.get("last_active")
            else ""}
