"""A durable work queue for one project: the lead's split of a big job, shared by every agent that works on it.

Stored in <project>/.ccx/queue/queue.jsonl as append-only events (add / update), so a crash loses nothing and any
agent (or the next lead) sees the same state. Each item: id, parent, title, brief, deps, kind, minutes, mode,
check, to/model (optional pins), status, run (last ccx run id), owner agent, cost, summary, depth.

status: todo -> doing -> done | failed | blocked | needs_write | split (waits for its children) ; review is set by
the lead's verdict through `ccx q done`. Ready = todo with every dependency done. Layered splitting: a sub-agent that
finds its piece too big returns status blocked with a summary starting SPLIT: and the pieces as JSON in next_step;
ccx adds them as children (depth + 1, at most MAX_DEPTH), and the parent is done when all of them are."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

MAX_DEPTH = 3
SPLIT = "SPLIT"
TERMINAL = ("done", "failed")


def qdir(root: Path) -> Path:
    return root / ".ccx" / "queue"


def _file(root: Path) -> Path:
    return qdir(root) / "queue.jsonl"


@contextmanager
def _lock(root: Path, timeout: float = 10.0):
    qdir(root).mkdir(parents=True, exist_ok=True)
    lock = qdir(root) / "queue.lock"
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - t0 > timeout:      # a crashed writer left it: take it over
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass
                continue
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _append(root: Path, ev: dict) -> None:
    with open(_file(root), "a", encoding="utf-8") as f:
        f.write(json.dumps({**ev, "ts": time.time()}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load(root: Path) -> dict:
    """-> {"items": {id: item}, "order": [ids], "budget_usd": float|None, "meta": {...}}"""
    items, order, meta = {}, [], {}
    try:
        lines = _file(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("ev") == "add":
            it = {k: v for k, v in ev.items() if k not in ("ev", "ts")}
            it.setdefault("status", "todo")
            it["added"] = ev["ts"]
            items[it["id"]] = it
            order.append(it["id"])
        elif ev.get("ev") == "update" and ev.get("id") in items:
            items[ev["id"]].update({k: v for k, v in ev.items() if k not in ("ev", "ts", "id")})
            items[ev["id"]]["updated"] = ev["ts"]
        elif ev.get("ev") == "meta":
            meta.update({k: v for k, v in ev.items() if k not in ("ev", "ts")})
    return {"items": items, "order": order, "budget_usd": meta.get("budget_usd"), "meta": meta}


def add(root: Path, title: str, brief: str, deps=(), parent: str | None = None, **extra) -> dict:
    with _lock(root):
        q = load(root)
        n = 1 + max((int(i[1:]) for i in q["items"] if i[1:].isdigit()), default=0)
        depth = (q["items"][parent]["depth"] + 1) if parent in q["items"] else 0
        unknown = [d for d in deps if d not in q["items"]]
        if unknown:
            raise ValueError(f"unknown dependencies: {', '.join(unknown)}")
        it = {"id": f"q{n}", "title": title, "brief": brief, "deps": list(deps), "parent": parent, "depth": depth,
              **{k: v for k, v in extra.items() if v is not None}}
        _append(root, {"ev": "add", **it})
        return {**it, "status": "todo"}


def update(root: Path, item_id: str, **fields) -> None:
    with _lock(root):
        _append(root, {"ev": "update", "id": item_id, **fields})


def set_budget(root: Path, usd: float | None) -> None:
    with _lock(root):
        _append(root, {"ev": "meta", "budget_usd": usd})


def spent(q: dict) -> float:
    return round(sum(float(it.get("cost_usd") or 0) for it in q["items"].values()), 6)


def ready(q: dict) -> list[dict]:
    items = q["items"]
    return [items[i] for i in q["order"] if items[i]["status"] == "todo"
            and all(items.get(d, {}).get("status") == "done" for d in items[i].get("deps", []))]


def children(q: dict, item_id: str) -> list[dict]:
    return [q["items"][i] for i in q["order"] if q["items"][i].get("parent") == item_id]


def close_parents(root: Path) -> list[str]:
    """A split item is done when every child is; failed when a child failed. Repeats up the tree."""
    closed = []
    while True:
        q = load(root)
        changed = False
        for it in q["items"].values():
            if it["status"] != "split":
                continue
            kids = children(q, it["id"])
            if kids and all(k["status"] == "done" for k in kids):
                update(root, it["id"], status="done", summary=f"all {len(kids)} parts done")
                closed.append(it["id"])
                changed = True
            elif any(k["status"] == "failed" for k in kids):
                update(root, it["id"], status="failed", summary="a part failed")
                changed = True
        if not changed:
            return closed


def parse_split(result: dict | None) -> list[dict] | None:
    """The pieces a sub-agent proposes (summary starts with SPLIT:, pieces as a JSON list in next_step)."""
    r = result or {}
    if not str(r.get("summary") or "").lstrip().upper().startswith(SPLIT):
        return None
    try:
        pieces = json.loads(r.get("next_step") or "[]")
    except ValueError:
        return None
    out = []
    for p in pieces if isinstance(pieces, list) else []:
        if isinstance(p, dict) and p.get("brief"):
            out.append({"title": str(p.get("title") or p["brief"][:60]), "brief": str(p["brief"]),
                        "deps": [int(d) for d in p.get("deps", []) if isinstance(d, int)],
                        "check": p.get("check")})
    return out or None


def add_split(root: Path, parent: dict, pieces: list[dict]) -> list[str]:
    """Children of `parent`, their deps given as indexes into the pieces list; the parent waits on them."""
    ids: list[str] = []
    left = None
    if parent.get("budget_usd") is not None:       # each part gets an equal share of what the parent has left
        left = max(0.0, float(parent["budget_usd"]) - float(parent.get("cost_usd") or 0)) / max(1, len(pieces))
    for p in pieces:
        deps = [ids[d] for d in p["deps"] if 0 <= d < len(ids)]
        it = add(root, p["title"], p["brief"], deps=deps, parent=parent["id"], check=p.get("check"),
                 kind=parent.get("kind"), mode=parent.get("mode"), to=parent.get("to"),
                 budget_usd=round(left, 6) if left is not None else None)
        ids.append(it["id"])
    update(root, parent["id"], status="split", summary=f"split into {', '.join(ids)}")
    return ids


SPLIT_HINT = ("If this piece is clearly too big to finish well in one go, don't do half of it: stop with status "
              "blocked, start the summary with SPLIT: and put the parts in next_step as a JSON list of "
              '{"title", "brief", "deps": [indexes of earlier parts], "check"}. ccx queues and routes each part.')


def tree(q: dict) -> list[str]:
    items = q["items"]
    lines = []

    def walk(i: str, depth: int) -> None:
        it = items[i]
        deps = f"  after {', '.join(it['deps'])}" if it.get("deps") else ""
        who = f"  [{it.get('agent')} {it.get('run')}]" if it.get("run") else ""
        lines.append(f"{'  ' * depth}{it['id']} {it['status']:<11} {it['title']}{deps}{who}")
        for k in children(q, i):
            walk(k["id"], depth + 1)
    for i in q["order"]:
        if not items[i].get("parent"):
            walk(i, 0)
    return lines


def unfinished_line(root: Path) -> str:
    """For the session-start hook: one line when this project's queue has open work, else ''."""
    q = load(root)
    open_ = [it for it in q["items"].values() if it["status"] not in TERMINAL + ("split",)]
    if not open_:
        return ""
    from .lang import say
    return say("hint_queue", n=len(open_), r=len(ready(q)))
