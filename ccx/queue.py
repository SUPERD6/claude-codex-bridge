"""A durable work queue for one project: the lead's split of a big job, shared by every agent that works on it.

Stored in <project>/.ccx/queue/queue.jsonl as append-only events (add / update), so a crash loses nothing and any
agent (or the next lead) sees the same state. Each item: id, parent, title, brief, deps, kind, minutes, mode,
check, to/model (optional pins), status, run (last ccx run id), owner agent, cost, summary, depth.

status: todo -> doing -> done | failed | blocked | needs_write | split (waits for its children) ; review is set by
the lead's verdict through `ccx q done`. Ready = todo with every dependency done (and accepted by the lead when the
dependency's work is in a worktree, or under `q run --gate`). A todo item whose dependency did not finish (failed,
blocked, needs_write) becomes dep_blocked, and todo again once that dependency is settled. Layered splitting: a sub-agent that
finds its piece too big returns status blocked with a summary starting SPLIT: and the pieces as JSON in next_step;
ccx adds them as children (depth + 1, at most MAX_DEPTH), and the parent is done when all of them are."""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

MAX_DEPTH = 3
SPLIT = "SPLIT"
TERMINAL = ("done", "failed")


def qdir(root: Path) -> Path:
    return root / ".ccx" / "queue"


def _file(root: Path) -> Path:
    return qdir(root) / "queue.jsonl"


_WINDOWS = os.name == "nt"


def _can_create(d: Path) -> bool:
    """Can this process create a file in d at all? Tells a lock file that is busy (Windows "delete pending") from a
    folder it may not write (read-only, an ACL), where waiting would never help."""
    # unique per call: threads of one process probing within one clock tick (monotonic_ns is ~15 ms coarse on Windows
    # before 3.13) drew the same name, and one thread's create then hit the other's just-deleted probe ("delete
    # pending": PermissionError) and took a busy lock for a folder it may not write (CI, windows-latest 3.12)
    probe = d / f"queue.probe.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
    try:
        os.close(os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except PermissionError:
        return False
    except OSError:
        return True
    try:
        probe.unlink()
    except OSError:
        pass
    return True


def _stale(lock: Path, timeout: float, seen: dict | None = None) -> bool:
    """Is the lock older than any holder keeps it (a crashed writer's)? Judged by the lock file itself, not by how
    long this waiter has waited, so a lock another writer has just taken is never taken over: stale when its mtime is
    more than timeout ago, or when this waiter has watched the very same lock file (inode, mtime, size) sit unchanged
    for more than timeout on its own monotonic clock. The second rule needs no agreement between clocks, so a lock
    whose mtime is in the future (a file server's clock ahead, a copied or restored file) is still taken over."""
    try:
        st = lock.stat()
    except OSError:
        return False                   # gone (try again) or cannot be read (delete pending): not stale
    if time.time() - st.st_mtime > timeout:
        return True
    if seen is None:
        return False
    sig, now = (st.st_ino, st.st_mtime_ns, st.st_size), time.monotonic()
    if seen.get("sig") != sig:         # a different lock (taken again since): start watching this one
        seen["sig"], seen["since"] = sig, now
        return False
    return now - seen["since"] > timeout


class _Turns:
    """This process's threads take turns on one queue folder's lock file through this; n counts the turns taken, so
    a waiter sees whether the lock is changing hands or one holder has hung."""

    def __init__(self):
        self.lock, self.n = threading.Lock(), 0


_LOCAL: dict[str, _Turns] = {}     # one per queue folder
_LOCAL_GUARD = threading.Lock()


def _local_lock(lock: Path) -> _Turns:
    key = os.path.normcase(os.path.abspath(lock))
    with _LOCAL_GUARD:
        return _LOCAL.setdefault(key, _Turns())


def _wait_turn(turns: _Turns, lock: Path, timeout: float, t0: float) -> None:
    """Take this process's turn: the same deadline rules as the file (2 * timeout since the last time a turn was
    taken, MAX_WAIT_FACTOR * timeout in all), so a thread that hangs holding the lock stalls the others no longer than
    a hung holder in another process would."""
    seen, progress = turns.n, t0
    while not turns.lock.acquire(timeout=min(0.1, timeout)):
        now = time.time()
        if turns.n != seen:
            seen, progress = turns.n, now
        if now - progress > 2 * timeout or now - t0 > MAX_WAIT_FACTOR * timeout:
            raise RuntimeError(f"queue lock {lock} still busy in this process after {now - t0:.1f}s")
    turns.n += 1


def _holder(lock: Path):
    """Which lock file this is (not how old): a new holder creates a new file and writes its own token into it, so
    this changes when the lock changed hands; touching the same file does not. The token matters where a freed inode
    number is reused at once and there is no birth time (Linux ext4/tmpfs). None when there is none to look at."""
    try:
        st = lock.stat()
        body = lock.read_bytes()[:200]
    except OSError:
        return None
    return st.st_ino, getattr(st, "st_birthtime_ns", None), body


@contextmanager
def _lock(root: Path, timeout: float = 10.0):
    """Hold the queue lock. Waits for a held one; takes over one older than timeout (a crashed writer's); gives up
    when the lock has not changed hands for 2 * timeout (a lock that cannot be taken over, e.g. held open by a hung
    writer on Windows) with PermissionError when the last attempt was denied, else RuntimeError; and after
    MAX_WAIT_FACTOR * timeout in all (the in-process wait below included). Never waits forever, and below that cap
    never fails only because other writers kept it busy.

    Threads of this process first take turns on an in-process lock, so they never poll against each other for the
    file (polling is unfair: a writer that just released takes it again before a sleeping waiter wakes; CI windows
    3.12 saw a thread wait out the old 2 * timeout in all while others wrote). That wait has the same rules: it fails
    after 2 * timeout without a turn changing hands (a thread hung holding the lock). Other processes still meet at
    the file; there the 2 * timeout counts from when this thread got its turn, and restarts whenever it sees the lock
    file change hands."""
    d = qdir(root)
    d.mkdir(parents=True, exist_ok=True)
    lock = d / "queue.lock"
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}".encode()
    t0 = time.time()
    turns = _local_lock(lock)
    _wait_turn(turns, lock, timeout, t0)
    local = turns.lock
    try:
        fd = _take(lock, d, timeout, t0, start=time.time())    # the file's deadline counts from here, not t0
    except BaseException:
        local.release()
        raise
    try:
        try:
            token = token[:os.write(fd, token)]    # whose lock it is: a release removes only its own
        except OSError:
            token = b""                        # unmarked: ours only while it stays empty (a takeover marks it)
        yield
    finally:
        try:
            os.close(fd)
            _unlink(lock, token)
        finally:
            local.release()


MAX_WAIT_FACTOR = 30            # a waiter that keeps seeing progress still gives up after this many timeouts


def _take(lock: Path, d: Path, timeout: float, t0: float, start: float | None = None) -> int:
    """Create the lock file (O_EXCL) -> its fd; the waiting and takeover rules of _lock. The 2 * timeout deadline
    counts from start (when this thread got its in-process turn) or the last change of hands; t0 is only for the
    MAX_WAIT_FACTOR * timeout cap on the whole wait."""
    probed, seen, holder, progress, pause = False, {}, None, (t0 if start is None else start), 0.002
    while True:
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError) as e:
            last = e
            if isinstance(e, PermissionError):
                # Windows: a lock file the last holder just unlinked stays "delete pending" for a moment, and creating
                # it then is denied, not FileExistsError: busy, so wait. Anywhere else, or when no file at all can be
                # created here, the denial is real and lasting: say so at once.
                if not _WINDOWS:
                    raise
                if not probed:
                    probed = True
                    if not _can_create(d):
                        raise
            now_holder = _holder(lock)
            if now_holder is not None:
                if holder is not None and now_holder != holder:
                    progress, pause = time.time(), 0.002     # changed hands: others are writing, not stuck
                holder = now_holder
            if _stale(lock, timeout, seen):    # a crashed writer left it: take it over
                try:
                    lock.unlink()
                    continue
                except FileNotFoundError:
                    continue
                except PermissionError as e2:  # held open (a hung writer, Windows): wait, up to the deadline
                    last = e2
            now = time.time()
            if now - progress > 2 * timeout or now - t0 > MAX_WAIT_FACTOR * timeout:
                msg = f"queue lock {lock} still busy after {now - t0:.1f}s ({type(last).__name__}: {last})"
                raise (PermissionError(msg) if isinstance(last, PermissionError) else RuntimeError(msg)) from last
            time.sleep(pause * (0.5 + random.random()))       # short at first, jittered: waiters do not move in step
            pause = min(0.05, pause * 1.5)


def _unlink(lock: Path, token: bytes | None = None, tries: int = 100) -> None:
    """Release the lock file, if it is still ours (token): one taken over from us belongs to the next writer now.
    On Windows the unlink can be denied for a moment (another writer's create racing with it, a virus scanner
    holding it open): retry for up to about 2 s, since a lock left behind stalls every other writer until it is
    stale (timeout). Left behind anyway, it is taken over then, so a release never fails the write it guarded.
    The check and the unlink are two steps: a takeover landing between them (only after we held the lock past
    timeout, and only where an open file can be deleted, i.e. not Windows) can still lose the new holder's lock;
    closing that needs OS file locking, which a plain lock file does not have."""
    for _ in range(tries):
        try:
            if token is not None and lock.read_bytes() != token:
                return
            lock.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.02)
        except OSError:
            return


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


def accepted(it: dict, gate: bool = False, q: dict | None = None) -> bool:
    """Does a finished item release the items that wait on it? Done, and, when its work sits in a worktree (not in
    the project folder, so a dependent started now would not see it) or under `q run --gate`, also accepted by
    the lead (`ccx q done <id> --ok 1`, after merging that worktree's branch). A split item (q given) releases
    them when every part does: its parts' work may sit in worktrees too."""
    if it.get("status") != "done":
        return False
    kids = children(q, it["id"]) if q else []
    if kids:
        return all(accepted(k, gate, q) for k in kids)
    return it.get("verdict") is True if (gate or it.get("worktree")) else True


def _unaccepted(it: dict, gate: bool, q: dict) -> list[dict]:
    """The finished pieces behind `it` (it, or its parts) that still wait for the lead's verdict."""
    kids = children(q, it["id"])
    if kids:
        return [x for k in kids for x in _unaccepted(k, gate, q)]
    return [] if accepted(it, gate, q) else [it]


def held_by(q: dict, it: dict, gate: bool = False) -> list[str]:
    """Items that name a common file (task-split `files`) never run side by side, and one never starts from code
    that lacks the other's change: it waits while the other runs, while the other is finished but not accepted
    (its work still in a worktree), or while the other is earlier in the queue and still todo. Items without
    `files` are never held (as before)."""
    if not it.get("files"):
        return []
    out, before = [], True
    for j in q["order"]:
        if j == it["id"]:
            before = False
            continue
        o = q["items"][j]
        if not overlaps(it, o):
            continue
        st = o["status"]
        if st == "doing" or (st == "done" and not accepted(o, gate, q)) or (before and st == "todo"):
            out.append(j)
    return out


def ready(q: dict, gate: bool = False) -> list[dict]:
    items = q["items"]
    return [items[i] for i in q["order"] if items[i]["status"] == "todo"
            and all(accepted(items.get(d, {}), gate, q) for d in items[i].get("deps", []))
            and not held_by(q, items[i], gate)]


def waiting(q: dict, gate: bool = False) -> list[dict]:
    """Todo items whose dependencies are all done but not yet accepted (see accepted), or that share a file with a
    finished piece not yet accepted (see held_by): they wait on the lead."""
    items = q["items"]
    out = []
    for i in q["order"]:
        it = items[i]
        deps = [items.get(d, {}) for d in it.get("deps", [])]
        if it["status"] != "todo" or not all(d.get("status") == "done" for d in deps):
            continue
        on = [x for d in deps for x in _unaccepted(d, gate, q)]
        on += [items[j] for j in held_by(q, it, gate) if items[j]["status"] == "done"]
        if not on:
            continue
        row = {"id": i, "on": list(dict.fromkeys(x["id"] for x in on))}
        trees = {x["id"]: x["worktree"] for x in on if x.get("worktree")}
        if trees:
            row["worktrees"] = trees                 # merge each branch into the project first, then accept it
        out.append(row)
    return out


def unmerged(q: dict) -> list[dict]:
    """Finished pieces whose work sits in a worktree branch the lead has not accepted yet (merge it, then
    `ccx q done <id> --ok 1`), so a branch nothing waits on is not forgotten."""
    items = q["items"]
    return [{"id": i, "branch": items[i].get("branch"), "worktree": items[i]["worktree"]} for i in q["order"]
            if items[i]["status"] == "done" and items[i].get("worktree") and items[i].get("verdict") is not True]


# a dependency in one of these will not release what waits on it until the lead settles it
STUCK = ("failed", "blocked", "needs_write")


def stuck_on(q: dict) -> dict[str, list[str]]:
    """{todo or dep_blocked item: the pieces that did not finish (failed, blocked, needs_write) that it waits on,
    directly or through other waiting pieces}. Names the piece to fix, never a piece that only waits itself."""
    items, memo = q["items"], {}

    def causes(i: str) -> list[str]:
        if i not in memo:
            memo[i] = []                        # a guard; add() and add_plan never make a cycle
            out = []
            for d in items.get(i, {}).get("deps", []):
                st = items.get(d, {}).get("status")
                if st in STUCK:
                    out.append(d)
                elif st in ("todo", "dep_blocked"):
                    out += causes(d)
            memo[i] = list(dict.fromkeys(out))
        return memo[i]
    return {i: causes(i) for i in q["order"] if items[i]["status"] in ("todo", "dep_blocked") and causes(i)}


def view(q: dict) -> dict:
    """The queue as propagate would leave it, without writing (`q ls` / `q tree` only read)."""
    stuck = stuck_on(q)
    items = {}
    for i, it in q["items"].items():
        if i in stuck:
            it = {**it, "status": "dep_blocked", "blocked_by": stuck[i]}
        elif it["status"] == "dep_blocked":
            it = {**it, "status": "todo", "blocked_by": []}
        items[i] = it
    return {**q, "items": items}


def propagate(root: Path) -> dict:
    """A dependency that did not finish (failed, blocked, needs_write) can never release its dependents: mark them
    (and theirs) dep_blocked with the piece to fix in blocked_by, so a run ends with an answer instead of leaving
    them todo forever. Once the lead settles it (`ccx q done <id> --ok 1`), they go back to todo. One read and its
    writes under the queue lock; the summary is left alone. -> {"dep_blocked": [ids], "unblocked": [ids]}"""
    out: dict[str, list[str]] = {"dep_blocked": [], "unblocked": []}
    with _lock(root):
        q = load(root)
        stuck = stuck_on(q)
        for i in q["order"]:
            it = q["items"][i]
            if it["status"] == "todo" and i in stuck:
                _append(root, {"ev": "update", "id": i, "status": "dep_blocked", "blocked_by": stuck[i]})
                out["dep_blocked"].append(i)
            elif it["status"] == "dep_blocked" and i not in stuck:
                _append(root, {"ev": "update", "id": i, "status": "todo", "blocked_by": []})
                out["unblocked"].append(i)
            elif it["status"] == "dep_blocked" and it.get("blocked_by") != stuck[i]:
                _append(root, {"ev": "update", "id": i, "blocked_by": stuck[i]})
    return out


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


def _piece_brief(t: dict, plan_title: str, titles: dict[str, str], deps: list[str]) -> str:
    """A task-split piece has a title, not a brief: give the sub-agent what the plan knows about it."""
    lines = [str(t["title"]).rstrip(".") + "."]
    if plan_title:
        lines.append(f"This is one piece of a larger plan: {plan_title}.")
    if t.get("files"):
        lines.append("Files: " + ", ".join(str(f) for f in t["files"]) + ".")
    done_before = [titles[d] for d in deps if d in titles]
    if done_before:
        lines.append("Already done before this piece: " + "; ".join(done_before) + ".")
    return "\n".join(lines)


def add_plan(root: Path, plan) -> dict:
    """Queue a whole plan: `{"tasks": [...]}` (ids + deps, as `ccx batch`), task-split's `{"pieces": [...]}`
    (ids + depends_on + files; a piece without a brief gets one from its title, the plan's title, its files and
    what comes before it, and its read/write mode is inferred from its own title) or a bare list. Dependencies may
    name any piece of the plan, earlier or later, or an item already in the queue (a plan id wins over a queue id
    of the same name); they are resolved once every id is known, and an unknown id or a cycle is an error before
    anything is added (it used to be dropped silently, so a piece ran before what it needed).
    -> {"added": [queue ids in plan order], "ids": {plan id: queue id}, "warnings": [...] when there are any}"""
    tasks = plan if isinstance(plan, list) else (plan.get("tasks") or plan.get("pieces") or [])
    plan_title = "" if isinstance(plan, list) else str(plan.get("title") or "")
    if not tasks:
        raise ValueError('the plan has no tasks: give {"tasks": [...]} or task-split\'s {"pieces": [...]}')
    existing = load(root)["items"]
    keys: list[str] = []
    for n, t in enumerate(tasks):
        if not (t.get("brief") or t.get("title")):
            raise ValueError(f"plan task {t.get('id') or n}: needs a brief or a title")
        k = str(t.get("id") or f"#{n}")
        if k in keys:
            raise ValueError(f"plan id {k!r} is used twice")
        keys.append(k)
    deps: dict[str, list[str]] = {}
    unknown = []
    for k, t in zip(keys, tasks):
        named = [str(d) for d in [*(t.get("deps") or []), *(t.get("depends_on") or [])]]
        deps[k] = list(dict.fromkeys(named))
        unknown += [f"{k} -> {d}" for d in deps[k] if d not in keys and d not in existing]
    if unknown:
        raise ValueError(f"unknown dependencies in the plan: {', '.join(unknown)} (plan ids: {', '.join(keys)})")
    warnings = [f"plan id {k!r} is also a queue item: inside this plan it means the plan's piece"
                for k in keys if k in existing and any(k in deps[o] for o in keys)]
    order, placed = [], set()
    while len(order) < len(keys):              # earlier pieces first, each after what it waits for
        nxt = next((k for k in keys if k not in placed and all(d in placed or d not in keys for d in deps[k])), None)
        if nxt is None:
            raise ValueError("the plan's dependencies form a cycle: " + ", ".join(k for k in keys if k not in placed))
        order.append(nxt)
        placed.add(nxt)
    titles = {k: str(t.get("title") or t.get("brief") or "")[:80] for k, t in zip(keys, tasks)}
    thin = [k for k, t in zip(keys, tasks) if not t.get("brief")]
    if thin:
        warnings.append(f"{', '.join(thin)}: no brief, so each one's brief was built from its title, the plan's "
                        "title, its files and what comes before it; give a brief where that is not enough")
    ids: dict[str, str] = {}
    for k in order:
        t = tasks[keys.index(k)]
        own = str(t.get("brief") or t["title"])
        brief = own if t.get("brief") else _piece_brief(t, plan_title, titles, deps[k])
        files = [str(f) for f in t.get("files") or []] or None
        it = add(root, str(t.get("title") or own[:60]), brief,
                 deps=[ids.get(d, d) for d in deps[k]], check=t.get("check"), minutes=t.get("minutes"),
                 mode=t.get("mode"), kind=t.get("kind"), to=t.get("to"), files=files,
                 mode_from=None if t.get("brief") else own,     # read or write: from the piece's own words
                 budget_usd=t.get("budget_usd", t.get("budget")))
        ids[k] = it["id"]
    out = {"added": [ids[k] for k in keys], "ids": {k: ids[k] for k in keys if not k.startswith("#")}}
    if warnings:
        out["warnings"] = warnings
    return out


def overlaps(a: dict, b: dict) -> bool:
    """Two items that name a common file (`files`, from task-split) must not run side by side."""
    fa = {f.replace("\\", "/").removeprefix("./") for f in a.get("files") or []}
    return bool(fa & {f.replace("\\", "/").removeprefix("./") for f in b.get("files") or []})


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
        if it["status"] == "dep_blocked" and it.get("blocked_by"):
            who += f"  (fix {', '.join(it['blocked_by'])} first)"
        elif it["status"] == "done" and it.get("worktree") and it.get("verdict") is not True:
            who += f"  (unmerged: {it.get('branch') or it['worktree']})"
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
