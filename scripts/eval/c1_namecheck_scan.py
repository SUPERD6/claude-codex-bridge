"""C1: should namecheck get stricter? Scan recorded code with this checkout's `ccx namecheck` and mark every hit.

Offline, no model calls. Two scans, each hit labelled true/false and marked whether it sits inside a broad
`except` that swallows (bare / Exception / BaseException, and the handler does not raise again):

  changes   every recorded unit's final tree (r5c..r5h, any arm), the way `ccx run` would check it: the .py files
            changed since the unit's first commit ("start"), only the functions whose lines changed (plus
            functions using a module-level name the change removed), new files whole
  whole     every distinct .py file in those trees, whole (a much larger surface for false positives), and the
            source of the external repositories (bare clones in --ext-cache: HEAD, read from `git archive`)

Hold-out rounds are scanned the same way when their work folders are given (--holdout-tags); none ran yet.

Labels: a hit is true when calling the function would raise NameError (the name is bound nowhere it could come
from at run time). The script cannot decide that alone, so it prints each hit with its line and takes the labels
from LABELS below (filled in by reading each hit) or --labels <json>; an unlabelled hit counts as "unlabelled".

  python scripts/eval/c1_namecheck_scan.py --ext-cache <dir with humanize.git, itsdangerous.git> --json out.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import offline_common as oc  # noqa: E402
from ccx import namecheck  # noqa: E402

# "<where>:<file>:<name>" -> (label, why). Filled in from reading each hit of the recorded rounds (see the report).
LABELS: dict[str, tuple[str, str]] = {
    "r5c/2-projects-refresh-ccx2:ccx/commands/memory.py:load_config": (
        "true", "cmd_mem imports load_config only inside other branches (lines 160, 411), not in this one; the "
                "NameError is swallowed by `except Exception: pass`, so session start silently skips the refresh"),
    # hits only in a reviewed tree (before its fix round): the final tree no longer has them
    "r5c/1-projects-refresh-direct:ccx/commands/memory.py:load_config": (
        "true", "same bug as r5c:2 (load_config imported only inside other functions); swallowed by "
                "`except Exception: pass`; gone after the fix round"),
    "r5e/2-projects-refresh-ccx2:ccx/commands/memory.py:cfg": (
        "true", "`cfg` is bound nowhere in cmd_mem; swallowed by `except Exception: pass`; gone after the fix round"),
    "r5g/2-projects-refresh-ccx2:ccx/commands/memory.py:cfg": (
        "true", "`cfg` is bound nowhere in cmd_mem (two uses); swallowed by `except Exception: pass`; gone after "
                "the fix round"),
    "r5g/1-mem-report-ccx2:ccx/delegate.py:_caller": (
        "true", "delegate.py never imports _caller (it lives in ccx/commands/common.py); _brief_notes would raise "
                "NameError whenever a brief gets notes, outside any try; gone after the fix round"),
}

BROAD = {"Exception", "BaseException"}


# ---------------------------------------------------------------- swallow blocks

def _broad(h: ast.ExceptHandler) -> bool:
    t = h.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    return any((isinstance(x, ast.Name) and x.id in BROAD) or (isinstance(x, ast.Attribute) and x.attr in BROAD)
               for x in names)


def _reraises(h: ast.ExceptHandler) -> bool:
    return any(isinstance(n, ast.Raise) for st in h.body for n in ast.walk(st))


def swallow_ranges(src: str) -> list[tuple[int, int]]:
    """Line ranges of `try:` bodies a broad handler swallows (catches Exception/BaseException/everything and does
    not raise again): a NameError there never reaches a test, only a missing effect does."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Try) and n.body and any(_broad(h) and not _reraises(h) for h in n.handlers):
            out.append((n.body[0].lineno, max(getattr(s, "end_lineno", s.lineno) or s.lineno for s in n.body)))
    return out


def in_swallow(ranges: list[tuple[int, int]], line: int) -> bool:
    return any(a <= line <= b for a, b in ranges)


# ---------------------------------------------------------------- the changes scan

def changed_lines(diff_u0: str) -> dict[str, set[int]]:
    """new-side line numbers per file of a `git diff -U0` text."""
    out: dict[str, set[int]] = {}
    cur = None
    for ln in diff_u0.splitlines():
        if ln.startswith("+++ "):
            cur = None if ln[4:] == "/dev/null" else ln[4:].removeprefix("b/")
            if cur:
                out.setdefault(cur, set())
        elif ln.startswith("@@") and cur:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", ln)
            if m:
                start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
                out[cur].update(range(start, start + count))
    return out


def scan_changes(repo: Path, base: str | None = None) -> dict:
    """namecheck over a repository's changes since `base` (default: its first commit), as `ccx run` sees them."""
    base = base or (oc.git(repo, "rev-list", "--max-parents=0", "HEAD").split() or [""])[-1]
    if not base:
        return {"hits": [], "files": 0, "skipped": "no commits"}
    names = set(oc.git(repo, "diff", "--name-only", base).split("\n"))
    names |= set(oc.git(repo, "ls-files", "--others", "--exclude-standard").split("\n"))
    lines = changed_lines(oc.git(repo, "diff", "-U0", base, "--", "*.py"))
    out = {"hits": [], "files": 0, "not_checked": []}
    for n in sorted(x for x in names if x.endswith(".py")):
        f = repo / n
        if not f.is_file():
            continue
        data = f.read_bytes()
        old = oc.git(repo, "show", f"{base}:{n}") if oc.git(repo, "cat-file", "-t", f"{base}:{n}").strip() else ""
        if old:
            ch = lines.get(n) or set()
            if not ch:
                continue
            removed = namecheck.defined_names(old) - namecheck.defined_names(data)
        else:
            ch, removed = None, set()
        out["files"] += 1
        hits, why = namecheck.check_source(data, n, ch, removed)
        if why:
            out["not_checked"].append(f"{n}: {why}")
        text = namecheck._decode(data)
        rng = swallow_ranges(text)
        src_lines = text.splitlines()
        for h in hits:
            h["swallowed"] = in_swallow(rng, h["line"])
            h["code"] = src_lines[h["line"] - 1].strip()[:160] if h["line"] <= len(src_lines) else ""
            out["hits"].append(h)
    return out


# ---------------------------------------------------------------- the whole-file scan

def scan_sources(sources: dict[str, bytes]) -> dict:
    """namecheck over whole files {path: bytes}, each distinct content once."""
    out, seen = {"hits": [], "files": 0, "not_checked": 0, "distinct": 0}, set()
    for path, data in sorted(sources.items()):
        key = hashlib.sha1(data).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out["distinct"] += 1
        hits, why = namecheck.check_source(data, path, None)
        out["files"] += 1
        if why:
            out["not_checked"] += 1
        if hits:
            text = namecheck._decode(data)
            rng, src_lines = swallow_ranges(text), text.splitlines()
            for h in hits:
                h["swallowed"] = in_swallow(rng, h["line"])
                h["code"] = src_lines[h["line"] - 1].strip()[:160] if h["line"] <= len(src_lines) else ""
                out["hits"].append(h)
    return out


def tree_sources(repo: Path) -> dict[str, bytes]:
    """Every .py file of a working tree (tracked or not, .git and caches left out)."""
    out = {}
    for f in repo.rglob("*.py"):
        rel = f.relative_to(repo).as_posix()
        if rel.startswith((".git/", ".venv/", "venv/")) or "/__pycache__/" in rel or "/.git/" in rel:
            continue
        try:
            out[rel] = f.read_bytes()
        except OSError:
            pass
    return out


def bare_sources(bare: Path, rev: str = "HEAD") -> dict[str, bytes]:
    """Every .py file of a bare repository's `rev`, read from `git archive` in memory (nothing is extracted)."""
    r = subprocess.run(["git", "archive", "--format=tar", rev], cwd=bare, capture_output=True)
    if r.returncode or not r.stdout:
        print(f"  (cannot read {bare}: git archive failed; pass a checkout with --ext-trees)", file=sys.stderr)
        return {}
    out = {}
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.endswith(".py"):
                out[m.name] = tf.extractfile(m).read()
    return out


# ---------------------------------------------------------------- the trees reviewers saw (before fix rounds)

def reviewed_trees(base: Path, tags, work: Path, skipped: list | None = None):
    """(where, tree) of every recorded review whose brief holds the whole diff: the tree the reviewer saw, rebuilt
    as review_replay.py does (the unit's start commit + the brief's diff). Fix rounds overwrite this state, so a
    bug a review caught is only here, not in the final tree. A review whose tree cannot be scanned is appended to
    `skipped` as {"where", "why"} (it shrinks the denominator, so the report states it)."""
    skipped = [] if skipped is None else skipped
    import review_replay as RR
    for tag in tags:
        for d in RR.review_dirs(base, [tag]):
            try:
                b = RR.parse_brief((d / "brief.md").read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                skipped.append({"where": f"{tag}/{d.parents[2].name.removeprefix('h-')}/{d.name}",
                                "why": f"brief: {type(e).__name__}"})
                continue
            unit = d.parents[2].name.removeprefix("h-")
            snap = RR.build_run(d.parent, oc.load(d / "run.json"))
            why = "diff cut" if b["cut"] else "no undo snapshot" if not snap else "empty diff" if not b["diff"].strip() else ""
            if why:
                skipped.append({"where": f"{tag}/{unit}/{d.name}", "why": why})
                continue
            tree = work / f"{tag}-{unit}-{d.name}"
            if not tree.exists():
                try:
                    RR.rebuild(d, Path(snap.get("repo") or base / tag / unit), snap["base"], b["diff"], tree)
                except (OSError, ValueError, KeyError) as e:      # a diff touching a scratch path that is gone
                    shutil.rmtree(tree, ignore_errors=True)
                    print(f"  (skip reviewed tree {tag}/{unit}/{d.name}: {type(e).__name__})", file=sys.stderr)
                    skipped.append({"where": f"{tag}/{unit}/{d.name}", "why": f"rebuild: {type(e).__name__}: {getattr(e, 'strerror', None) or e}"[:200]})
                    continue
            yield f"{tag}/{unit}@review:{d.name}", tree


# ---------------------------------------------------------------- labels and the report

def hit_key(where: str, h: dict) -> str:
    return f"{where}:{h['file']}:{h['name']}"


def label(where: str, h: dict, labels: dict) -> tuple[str, str]:
    """The label of a hit: by its unit (a whole-file hit's path starts with <tag>/<unit>/), else by file alone."""
    parts = h["file"].split("/")
    lb = (labels.get(hit_key(where, h)) or labels.get(f"*:{h['file']}:{h['name']}")
          or (labels.get(f"{parts[0]}/{parts[1]}:{'/'.join(parts[2:])}:{h['name']}") if len(parts) > 2 else None))
    return tuple(lb) if lb else ("unlabelled", "")


def tally(rows: list[dict]) -> dict:
    t = {"hits": len(rows)}
    for lb in ("true", "false", "unlabelled"):
        rs = [r for r in rows if r["label"] == lb]
        t[lb] = len(rs)
        t[f"{lb}_swallowed"] = sum(r["swallowed"] for r in rs)
    return t


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="", help="folder holding the round folders (default: temp_root())")
    ap.add_argument("--tags", default=",".join(oc.TAGS), type=lambda x: [t for t in x.split(",") if t])
    ap.add_argument("--holdout-tags", default="", type=lambda x: [t for t in x.split(",") if t])
    ap.add_argument("--ext-cache", default="", help="folder with <name>.git bare clones of the external repos")
    ap.add_argument("--ext-trees", default="", type=lambda x: [t for t in x.split(",") if t],
                    help="comma-separated checked-out external repositories (scanned whole, like --ext-cache)")
    ap.add_argument("--no-whole", action="store_true", help="skip the whole-file scan")
    ap.add_argument("--reviewed", default="", help="also rebuild every reviewed tree (before its fix round) under "
                                                   "this folder and scan its changes")
    ap.add_argument("--labels", default="", help="json {key: [label, why]} on top of LABELS")
    ap.add_argument("--json", default="", help="write every hit and the totals here")
    a = ap.parse_args(argv)
    base = Path(a.records) if a.records else oc.temp_root()
    labels = dict(LABELS)
    if a.labels:
        labels.update({k: tuple(v) for k, v in oc.load(Path(a.labels)).items()})
    report: dict = {"changes": [], "whole": [], "units": 0, "holdout_units": 0}

    for tags, kind in ((a.tags, "round"), (a.holdout_tags, "holdout")):
        for tag, u in oc.unit_dirs(base, tags):
            report["units" if kind == "round" else "holdout_units"] += 1
            res = scan_changes(u)
            for h in res["hits"]:
                where = f"{tag}/{u.name}"
                lb, why = label(where, h, labels)
                report["changes"].append({"where": where, "kind": kind, **h, "label": lb, "why": why})
    if a.reviewed:
        work = Path(a.reviewed)
        work.mkdir(parents=True, exist_ok=True)
        report["reviewed_skipped"] = []
        report["reviewed_trees"] = 0
        for where, tree in reviewed_trees(base, a.tags, work, report["reviewed_skipped"]):
            report["reviewed_trees"] += 1
            for h in scan_changes(tree)["hits"]:
                lb, why = label(where.split("@")[0], h, labels)
                report["changes"].append({"where": where, "kind": "reviewed", **h, "label": lb, "why": why})
    if not a.no_whole:
        srcs: dict[str, bytes] = {}
        for tag, u in oc.unit_dirs(base, a.tags + a.holdout_tags):
            for rel, data in tree_sources(u).items():
                srcs[f"{tag}/{u.name}/{rel}"] = data
        res = scan_sources(srcs)
        report["whole_files"] = {"files": res["files"], "distinct": res["distinct"], "not_checked": res["not_checked"]}
        for h in res["hits"]:
            lb, why = label("whole", h, labels)
            report["whole"].append({"where": "whole", **h, "label": lb, "why": why})
        ext = [(b.stem, bare_sources(b)) for b in sorted(Path(a.ext_cache).glob("*.git"))] if a.ext_cache else []
        ext += [(Path(t).name, tree_sources(Path(t))) for t in a.ext_trees]
        for name, files in ext:
            res = scan_sources({f"{name}/{k}": v for k, v in files.items()})
            report.setdefault("ext_files", {})[name] = {"files": res["files"], "not_checked": res["not_checked"]}
            for h in res["hits"]:
                lb, why = label(f"ext/{name}", h, labels)
                report["whole"].append({"where": f"ext/{name}", **h, "label": lb, "why": why})

    report["totals"] = {"changes": tally(report["changes"]), "whole": tally(report["whole"])}
    print(f"units scanned (changes since start): {report['units']} round, {report['holdout_units']} hold-out, "
          f"{report.get('reviewed_trees', 0)} reviewed trees, {len(report.get('reviewed_skipped') or [])} skipped")
    for sk in report.get("reviewed_skipped") or []:
        print(f"  skipped reviewed tree {sk['where']}: {sk['why']}")
    for part in ("changes", "whole"):
        print(f"{part}: {report['totals'][part]}")
        for r in report[part]:
            print(f"  [{r['label']}{', swallowed' if r['swallowed'] else ''}] {r['where']} {namecheck.line(r)}"
                  f"  | {r.get('code', '')}  {('- ' + r['why']) if r['why'] else ''}")
    if report.get("whole_files"):
        print(f"whole-file scan: {report['whole_files']}; external: {report.get('ext_files', {})}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
