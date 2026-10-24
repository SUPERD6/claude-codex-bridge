"""Project layer: <repo>/.ccx/ shared by every agent that works in this project.

    context.md      project snapshot ("1"): goal, decisions, state, conventions
    journal.jsonl   project increments ("+2"): who added what, one line each
    cursors.json    how far each agent has read the project journal
    inbox/          files/emails/pages the user gave either agent (git-ignored)
    tasks/          task-checkpoint state (git-ignored)

Same incremental rules as personal memory: an agent's session start shows only what the
OTHER agent added since its last look, so the project is never re-read from scratch.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import memory

CONTEXT_TEMPLATE = """# 项目上下文 / Project context

两边子任务开局都会先读这里；保持简短。/ Every sub-agent reads this first; keep it short.

## 目标 / Goal
- 

## 已定的决定 / Decisions
- 

## 当前状态 / Status
- 

## 约定 / Conventions
- 
"""
IGNORES = [".ccx/inbox/", ".ccx/tasks/", ".ccx/cursors.json", ".ccx/*.lock", ".ccx/runs/", ".ccx/handoff.seen.json",
           ".ccx/undo/"]


@dataclass(frozen=True)
class ProjectPaths:
    """Duck-typed like config.Paths so ccx.memory's journal/cursor logic works unchanged."""
    root: Path

    @property
    def memory(self) -> Path:
        return self.root / ".ccx"

    @property
    def state(self) -> Path:
        return self.root / ".ccx"

    @property
    def memory_index(self) -> Path:
        return self.root / ".ccx" / "context.md"

    @property
    def snapshot_external(self) -> bool:
        return True                      # context.md is the project's own file; never templated over

    @property
    def inbox(self) -> Path:
        return self.root / ".ccx" / "inbox"


def find_root(start: Path | None = None) -> Path | None:
    """Nearest folder with .ccx/context.md, stopping at the repo top (main worktree for worktrees)."""
    cwd = (start or Path.cwd()).resolve()
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=20)
        common = Path(r.stdout.strip()) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        common = None
    candidates = [cwd, *cwd.parents]
    if common and common.name == ".git":
        candidates.append(common.parent)
    for d in candidates:
        if (d / ".ccx" / "context.md").exists():
            return d
        if (d / ".git").exists() and not (common and d == common.parent):
            # stop at the current repo top unless we are in a linked worktree (checked via common dir)
            break
    if common and (common.parent / ".ccx" / "context.md").exists():
        return common.parent
    return None


def _git_ignores(root: Path, pattern: str) -> bool:
    """True if git already ignores what the pattern covers (e.g. the whole `.ccx/` is ignored)."""
    probe = pattern.replace("*", "x") + ("x" if pattern.endswith("/") else "")
    try:
        r = subprocess.run(["git", "check-ignore", "-q", probe], cwd=root, capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def init(root: Path) -> dict:
    pp = ProjectPaths(root)
    pp.memory.mkdir(parents=True, exist_ok=True)
    pp.inbox.mkdir(exist_ok=True)
    created = []
    if not pp.memory_index.exists():
        pp.memory_index.write_text(CONTEXT_TEMPLATE, encoding="utf-8")
        created.append(str(pp.memory_index))
    (pp.memory / "journal.jsonl").touch(exist_ok=True)
    gi = root / ".gitignore"
    txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
    missing = [x for x in IGNORES if x not in txt and not _git_ignores(root, x)]
    if missing:
        with open(gi, "a", encoding="utf-8") as f:
            f.write(("" if not txt or txt.endswith("\n") else "\n") + "\n".join(missing) + "\n")
    return {"project": str(root), "created": created, "gitignore_added": missing}


def _slug(name: str) -> str:
    stem = re.sub(r"[^\w.\-]+", "-", name, flags=re.U).strip("-")
    return stem[:80] or "item"


def inbox_add(root: Path, src: Path | None, note: str, by: str, text: str | None = None,
              name: str | None = None) -> dict:
    """Keep the original in inbox/, put ONE line about it in the journal (that line is all the other
    agent reads at session start; it opens the file only if it needs the details)."""
    pp = ProjectPaths(root)
    pp.inbox.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    if src is not None:
        dst = pp.inbox / f"{stamp}-{_slug(name or src.name)}"
        shutil.copy2(src, dst)
    else:
        dst = pp.inbox / f"{stamp}-{_slug(name or 'note')}.md"
        dst.write_text(text or "", encoding="utf-8")
    rel = dst.relative_to(root).as_posix()
    entry = memory.add(pp, f"{note} (original: {rel})", by=by, topic="inbox")
    return {"saved": rel, "journal": entry}


def delta_text(root: Path, me: str, advance: bool = True) -> str:
    new = memory.delta(ProjectPaths(root), me, advance=advance)
    if not new:
        return ""
    lines = [f"[ccx project {root.name}: new since your last session]"]
    lines += [f"- #{e['seq']} ({e['by']}, {e['topic']}): {e['text']}" for e in new]
    return "\n".join(lines)


# ------------------------------------------------------------------ handoff (switch lead: Claude -> Codex or back)
HANDOFF_TEMPLATE = """## Done
- 
## Decisions (and why)
- 
## In progress / where it stopped
- 
## Next
- 
## Key files
- 
## Open questions
- 
"""


def handoff(root: Path, by: str, to: str, text: str) -> dict:
    """Write a baton for the next lead. Each handoff gets its own file in .ccx/handoffs/, so parallel sessions can't
    overwrite each other's; handoff.md is only the latest. The other side's session start lists every one it has
    not seen yet."""
    pp = ProjectPaths(root)
    if not pp.memory_index.exists():
        init(root)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    body = text.strip() or HANDOFF_TEMPLATE
    doc = f"<!-- ccx:handoff from={by} to={to} ts={ts} -->\n# Handoff {by} -> {to} ({ts})\n\n{body}\n"
    hist = root / ".ccx" / "handoffs"
    hist.mkdir(parents=True, exist_ok=True)
    stem = f"{ts.replace(':', '')}-{by}-to-{to}"
    own = hist / f"{stem}.md"
    n = 1
    while own.exists():                       # two handoffs in the same second (parallel sessions)
        n += 1
        own = hist / f"{stem}-{n}.md"
    own.write_text(doc, encoding="utf-8")
    f = root / ".ccx" / "handoff.md"
    f.write_text(doc, encoding="utf-8")
    rel = own.relative_to(root).as_posix()
    first = next((l.strip("-# ").strip() for l in body.splitlines() if l.strip("-# ").strip()), "")
    memory.add(pp, f"Handoff {by} -> {to}: {first[:160]} (full text: {rel})", by, "handoff")
    return {"handoff": str(own), "latest": str(f), "chars": len(doc), "to": to}


_HEAD = re.compile(r"<!-- ccx:handoff from=(\S+) to=(\S+) ts=(\S+) -->")


def _for_me(m: re.Match | None, me: str) -> bool:
    # to me (even from my own kind: a fresh conversation, J4), or to anyone but me
    return bool(m) and m.group(2) in (me, "any") and not (m.group(1) == me and m.group(2) == "any")


def pending_handoffs(root: Path, me: str) -> list[tuple[Path, re.Match, str]]:
    """Handoffs addressed to me (or to any) that I have not been shown yet, oldest first."""
    d = root / ".ccx"
    files = sorted((d / "handoffs").glob("*.md")) if (d / "handoffs").exists() else []
    if not files and (d / "handoff.md").exists():
        files = [d / "handoff.md"]               # written before handoffs/ existed
    seen = _seen(root).get(me)
    out = []
    for f in files:
        doc = f.read_text(encoding="utf-8", errors="replace")
        m = _HEAD.match(doc)
        if not _for_me(m, me):
            continue
        if isinstance(seen, str) and m.group(3) <= seen:    # old format: the last timestamp shown
            continue
        if isinstance(seen, list) and f.name in seen:
            continue
        out.append((f, m, doc[m.end():].strip()))
    return out


def _seen(root: Path) -> dict:
    f = root / ".ccx" / "handoff.seen.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except json.JSONDecodeError:
        return {}


def pending_handoff(root: Path, me: str, advance: bool = True) -> str:
    """Every handoff to me (or to any) not shown yet, each once per agent: the newest whole or summarised, older
    ones (parallel sessions) one line each with their file."""
    todo = pending_handoffs(root, me)
    if not todo:
        return ""
    if advance:
        seen = _seen(root)
        old = seen.get(me)
        names = old if isinstance(old, list) else []
        if isinstance(old, str):                 # convert: everything up to that timestamp was shown
            names = [f.name for f in sorted((root / ".ccx" / "handoffs").glob("*.md"))
                     if (_HEAD.match(f.read_text(encoding="utf-8", errors="replace")) or [None] * 4)[3] or "" <= old]
        seen[me] = sorted({*names, *(f.name for f, _, _ in todo)})[-200:]
        (root / ".ccx" / "handoff.seen.json").write_text(json.dumps(seen), encoding="utf-8")
    f, m, text = todo[-1]
    rel = f.relative_to(root).as_posix()
    head = f"[ccx handoff to you from {m.group(1)}, {m.group(3)}: {rel}]\n"
    body = text if len(text) <= HANDOFF_WHOLE else \
        _handoff_summary(text) + f"\n\n(summary; the full handoff is in {rel})"
    if len(todo) == 1:
        return head + body
    others = [f"- {m2.group(3)} from {m2.group(1)}: {_first_line(t)} ({f2.relative_to(root).as_posix()})"
              for f2, m2, t in todo[:-1]]
    return (f"[ccx: {len(todo)} handoffs to you not seen yet (parallel sessions); the newest first, then the others "
            f"— read the one that belongs to your task]\n" + head + body
            + "\n\n[older handoffs not seen yet]\n" + "\n".join(others))


def _first_line(text: str) -> str:
    for line in text.splitlines():
        t = line.strip("-#* _").strip()
        if t and not t.lower().startswith(("auto-assembled", "handoff ")):
            return t[:120]
    return ""


HANDOFF_WHOLE = 2000      # shorter handoffs are shown whole at session start
# sections a new lead needs to start; finished "- [x]" items are left out
HANDOFF_KEEP = ("next", "stopped", "open question", "key file", "note", "rule", "todo", "to-do",
                "接下来", "下一步", "待办", "停在", "未解决", "问题", "关键文件", "注意", "规则")


def _handoff_summary(text: str, limit: int = 2500) -> str:
    title, keep, cur, skip_item = "", [], None, False
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line
        elif line.startswith("## "):
            cur = line if any(k in line.lower() for k in HANDOFF_KEEP) else None
            if cur:
                keep.append(["", cur])
            skip_item = False
        elif cur:
            if line.lstrip().startswith(("- [x]", "- [X]")):
                skip_item = True
                continue
            if skip_item and line.startswith(("  ", "\t")) and not line.lstrip().startswith("- "):
                continue                                  # continuation lines of a finished item
            skip_item = False
            keep[-1].append(line)
    if not keep:
        return text[:limit]
    out = "\n".join([title, *("\n".join(sec).rstrip() for sec in keep)]).strip()
    return out if len(out) <= limit else out[:limit] + "\n…"
