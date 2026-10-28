"""Shared helpers of the offline experiments (C1-C6 of the improvement plan): where the recorded rounds live, how
their folders are laid out, and a few statistics. Standard library only; nothing here calls a model.

A round's work folder (<temp>/<tag>, tag r5c..r5h) holds, per unit:
  <round>-<task>-<arm>/              the unit's final repository (first commit "start" = the task's base)
  <round>-<task>-<arm>.stream.jsonl  the lead's Claude Code stream (stream-json), when the arm has a lead
  h-<round>-<task>-<arm>/ccx/runs/<run id>/run.json (+ events.N.log, brief.md, prompt.md, undo.json)
and the round's scored rows are in .ccx/eval/r5/results.jsonl (label eval-r5:<tag>:<round>:<task>:<arm>).
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

TAGS = ("r5c", "r5d", "r5e", "r5f", "r5g", "r5h")
LABEL = re.compile(r"^eval-r5:(?P<tag>[^:]+):(?P<round>\d+):(?P<task>[^:]+):(?P<arm>[^:]+)$")
UNIT = re.compile(r"^(?P<round>\d+)-(?P<task>.+)-(?P<arm>[a-z0-9]+)$")


def temp_root() -> Path:
    """Where the round folders are: CCX_REPLAY_RECORDS, else the system temp folder (as review_replay.py)."""
    return Path(os.environ.get("CCX_REPLAY_RECORDS") or tempfile.gettempdir())


def load(f: Path) -> dict:
    return json.loads(Path(f).read_text(encoding="utf-8"))


def read_jsonl(f: Path) -> list[dict]:
    out = []
    try:
        text = Path(f).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.quotepath=false", *args], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def unit_dirs(base: Path, tags=TAGS) -> list[tuple[str, Path]]:
    """(tag, unit repository) of every recorded unit, in name order."""
    out = []
    for tag in tags:
        d = Path(base) / tag
        if not d.is_dir():
            continue
        for u in sorted(d.iterdir()):
            if u.is_dir() and not u.name.startswith("h-") and UNIT.match(u.name) and (u / ".git").exists():
                out.append((tag, u))
    return out


def unit_key(tag: str, unit: str) -> str:
    """eval-r5 label of a unit folder name (1-brief-words-ccx2 -> eval-r5:<tag>:1:brief-words:ccx2)."""
    m = UNIT.match(unit)
    return f"eval-r5:{tag}:{m['round']}:{m['task']}:{m['arm']}" if m else ""


def results(f: Path, tags=TAGS) -> dict[str, dict]:
    """label -> the scored row (the last one when a label was scored twice)."""
    out = {}
    for r in read_jsonl(f):
        if r.get("tag") in tags and r.get("label"):
            out[r["label"]] = r
    return out


def hub_runs(hub: Path) -> dict[str, dict]:
    """run id -> run.json of one unit's hub (unreadable files skipped)."""
    out = {}
    for f in sorted(Path(hub).glob("ccx/runs/*/run.json")):
        try:
            r = load(f)
        except (OSError, ValueError):
            continue
        r["_dir"] = str(f.parent)
        out[r.get("run_id") or f.parent.name] = r
    return out


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test of the 2x2 table [[a, b], [c, d]] (sum of the tables no likelier than this one)."""
    r1, c1, n = a + b, a + c, a + b + c + d

    def p(x: int) -> float:
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)

    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)))


def lead_tool_calls(stream: Path) -> list[dict]:
    """The lead's own tool calls from a Claude Code stream-json file, in order, each with its result:
    {"i", "name", "input", "result" (text), "error" (bool)}. Calls made inside a sub-agent (parent_tool_use_id set)
    are left out: they are the worker's, not the lead's."""
    calls, by_id = [], {}
    for d in read_jsonl(stream):
        if d.get("parent_tool_use_id"):
            continue
        msg = d.get("message") or {}
        if d.get("type") == "assistant":
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    row = {"i": len(calls), "name": c.get("name"), "input": c.get("input") or {}, "result": "",
                           "error": False}
                    calls.append(row)
                    by_id[c.get("id")] = row
        elif d.get("type") == "user":
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                    t = c.get("content")
                    if isinstance(t, list):
                        t = "\n".join(x.get("text", "") for x in t if isinstance(x, dict))
                    by_id[c["tool_use_id"]]["result"] = str(t or "")
                    by_id[c["tool_use_id"]]["error"] = bool(c.get("is_error"))
    return calls
