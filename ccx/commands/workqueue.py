"""ccx q — the project's durable work queue (ccx/queue.py): add pieces, see them, run every ready one."""
from __future__ import annotations

import functools
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import lanes, queue as wq
from ..config import load_config, paths
from ..delegate import Request, compact, run, verify
from ..modes import resolve_mode
from .common import _caller, _out, resolve


def _root(a) -> Path:
    from .. import project
    root = project.find_root(Path(a.cwd) if getattr(a, "cwd", None) else None)
    if root:
        return root
    return Path(getattr(a, "cwd", None) or os.getcwd())


def cmd_q(a) -> int:
    root = _root(a)
    if a.q_cmd == "add":
        if a.plan:
            _out(wq.add_plan(root, json.loads(Path(a.plan).read_text(encoding="utf-8"))))
            return 0
        it = wq.add(root, a.title, a.brief or a.title, deps=a.dep or [], parent=a.parent, check=a.check,
                    minutes=a.minutes, mode=a.mode, kind=a.kind, to=a.to, budget_usd=a.budget)
        _out(it)
    elif a.q_cmd in ("ls", "tree"):
        from ..recover import sweep
        sweep(paths())                  # as `ccx stats` does: a run whose ccx was killed shows as interrupted
        q = wq.view(wq.load(root))      # a stuck dependency shows on what waits for it (shown, not written)
        if a.q_cmd == "tree":
            print("\n".join(wq.tree(q)) or "(queue empty)")
        else:
            gate = bool(getattr(a, "gate", False))
            _out({"items": [q["items"][i] for i in q["order"]], "ready": [x["id"] for x in wq.ready(q, gate)],
                  "spent_usd": wq.spent(q), "budget_usd": q["budget_usd"]})
    elif a.q_cmd == "budget":
        wq.set_budget(root, a.usd)
        _out({"budget_usd": a.usd})
    elif a.q_cmd == "done":
        q = wq.load(root)
        it = q["items"][a.id]
        if it.get("run"):
            verify(paths(), it["run"], bool(a.ok), a.note or "")
        wq.update(root, a.id, status="done" if a.ok else "failed", verdict=bool(a.ok))
        out = {"id": a.id, "closed_parents": wq.close_parents(root)}
        moved = wq.propagate(root)
        out.update({k: v for k, v in moved.items() if v})
        _out(out)
    elif a.q_cmd in ("run", "resume"):
        return _run(a, root)
    return 0


RESUME_NOTE = ("ccx was stopped while you were working on this piece. Go on from where you were: check what is "
               "already done before redoing anything.\n\n")


def _cost(rec: dict) -> float:
    return sum(a.get("ae_usd") or 0 for a in rec.get("attempts", [])) + ((rec.get("review") or {}).get("usd") or 0)


def item_runs(p, root: Path, it: dict) -> list[dict]:
    """The ccx runs this item started since it last went 'doing' (label q:<id>, this project), oldest first: the
    first run and a review's fix round. Found from the runs folder because the item hears of them only when
    run() returns, which a killed `q run` never reaches."""
    from .. import ledger
    import time as _t
    if not p.runs.exists():
        return []
    since = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(float(it.get("updated") or it.get("added") or 0) - 5))
    out = []
    for d in sorted(p.runs.iterdir()):
        if d.name < since or not (d / "run.json").exists():
            continue
        try:
            rec = ledger.read_record(d / "run.json")
            if rec.get("label") == f"q:{it['id']}" and _here(Path(rec.get("cwd") or ""), root):
                out.append(rec)
        except (OSError, ValueError):
            continue
    return out


@functools.lru_cache(maxsize=64)
def _top(root: str) -> str | None:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _here(cwd: Path, root: Path) -> bool:
    """A run in this project: in its folder, or in a ccx worktree of it (workspace.make_worktree's layout, named
    after the repository's top folder, which is not the project folder when the queue lives in a subfolder)."""
    cwd, root = cwd.resolve(), root.resolve()
    if cwd == root:
        return True
    tops = {root}
    top = _top(str(root))
    if top:
        tops.add(Path(top).resolve())
    return any(cwd.parent == t.parent / ".ccx-worktrees" / t.name for t in tops)


def _mode(it: dict) -> dict:
    """An item's read/write mode, decided the same way when `q run` counts its writers and when it runs: from its
    own words (task-split's title for a piece without a brief), never from SPLIT_HINT, whose "JSON list" read as
    analysis and made a plain "Disk backend" piece read-only."""
    return resolve_mode(it.get("mode"), it.get("mode_from") or it.get("brief", ""))


def _tree_fields(rec: dict) -> tuple[dict, str | None]:
    """Fields for a finished run's item: where its work sits. In a ccx worktree its work is not in the project
    folder: one commit there, and whatever waits on it waits for the lead to merge that branch and accept the item
    (`ccx q done <id> --ok 1`; queue.accepted). In the project folder the fields are cleared, so a worktree or a
    verdict left from an earlier run of the item does not stick."""
    cwd = str(rec.get("cwd") or "")
    if "/.ccx-worktrees/" not in cwd.replace("\\", "/"):
        return {"worktree": None, "branch": None, "verdict": None}, None
    from ..lanes import commit_block
    from ..workspace import _git
    sha = commit_block(rec)
    _, branch = _git(Path(cwd), "rev-parse", "--abbrev-ref", "HEAD")
    return {"worktree": cwd, "branch": branch or None, "verdict": None}, sha


def restored(old_run: str, rec: dict) -> str:
    """How an interrupted piece came back (OpenRig's taxonomy): resumed | fresh | decide | failed."""
    if rec.get("kind") in ("quota", "auth", "needs_write", "over_budget", "user_stopped", "interrupted",
                               "check_broken"):
        return "decide"                 # something only the user or the lead can settle
    if not rec.get("ok") or rec.get("kind") in ("check_failed", "timeout", "error"):
        return "failed"
    return "resumed" if rec.get("continued") or rec.get("resumed_from") == old_run else "fresh"


def _one(it: dict, root: Path, caller: str, p, cfg, warm: str | None = None, got: dict | None = None,
         worktree: bool = False) -> dict:
    """Route and run one queue item; write its outcome back. Never raises (a thread must report).
    warm: a lane's last run (ccx/lanes.py), whose session takes this item as a new task; got["rec"]: its record.
    worktree: a write item that runs beside other writers works in its own git worktree (as `ccx batch`)."""
    try:
        if it.get("budget_usd") is not None and float(it.get("cost_usd") or 0) >= float(it["budget_usd"]):
            wq.update(root, it["id"], status="blocked", summary="its budget is used up")
            return {"id": it["id"], "status": "blocked", "why": "budget"}
        m = _mode(it)                                      # before SPLIT_HINT is added (see _mode)
        spec = {"brief": it["brief"] + ("\n\n" + wq.SPLIT_HINT if it.get("depth", 0) < wq.MAX_DEPTH else ""),
                "to": it.get("to"), "minutes": it.get("minutes"), "kind": it.get("kind"), "mode": m["mode"],
                "mode_source": m["source"], "mode_why": m["why"], "cwd": str(root), "force": True}
        if not spec["minutes"]:
            spec["clarity"] = "goal"                       # switch on routing even without an estimate
        kw, route = resolve(spec, caller, p, cfg)
        if kw is None:
            wq.update(root, it["id"], status="todo", summary=route.get("advice"))
            return {"id": it["id"], "status": "todo", "skipped": route.get("advice")}
        wq.update(root, it["id"], status="doing", agent=kw["to"])
        resume = it.get("run") if it.get("resume") else None
        left = (max(0.0, float(it["budget_usd"]) - float(it.get("cost_usd") or 0))   # F11: the cap is what it has left
                if it.get("budget_usd") is not None else None)
        brief = (RESUME_NOTE + spec["brief"]) if resume else spec["brief"]
        rec = run(Request(brief=brief, mode=spec["mode"], mode_source=spec["mode_source"],
                          mode_why=spec["mode_why"], cwd=root, caller=caller, label=f"q:{it['id']}",
                          check=it.get("check"), resume_run=resume or warm, continued=bool(warm and not resume),
                          budget_usd=left, worktree=worktree, **kw), p)
        if got is not None:
            got["rec"] = rec
        res = compact(rec)
        status = res.get("status")
        cost = _cost(rec)
        fields = {"run": rec["run_id"], "agent": rec["to"], "summary": (res.get("summary") or "")[:300],
                  "cost_usd": round(float(it.get("cost_usd") or 0) + cost, 6), "resume": False}
        where, sha = _tree_fields(rec)
        fields.update(where)
        pieces = wq.parse_split(rec.get("result")) if status == "blocked" else None
        if pieces and it.get("depth", 0) < wq.MAX_DEPTH:
            wq.update(root, it["id"], **fields)
            kids = wq.add_split(root, it, pieces)
            return {"id": it["id"], "split_into": kids}
        if rec.get("kind") == "needs_write":
            fields["status"] = "needs_write"
        elif rec.get("kind") in ("check_failed", "check_broken", "review_failed", "review_issues") or not rec["ok"] or status in ("failed",):
            fields["status"] = "failed"
        elif status == "blocked":
            fields["status"] = "blocked"
        else:
            fields["status"] = "done"
        wq.update(root, it["id"], **fields)
        out = {"id": it["id"], "status": fields["status"], "run": rec["run_id"]}
        if fields.get("worktree"):
            out.update(worktree=fields["worktree"], branch=fields.get("branch"))
            if sha:
                out["commit"] = sha
        if resume:
            out["restored"] = restored(resume, rec)
        return out
    except Exception as e:  # noqa: BLE001
        why = f"{type(e).__name__}: {e}"[:300]
        row = {"id": it["id"], "status": "failed", "error": why}
        try:
            wq.update(root, it["id"], status="failed", summary=why)
        except Exception as e2:  # noqa: BLE001   writing the failure back failed too: still report, never raise
            row["not_recorded"] = f"{type(e2).__name__}: {e2}"[:300]
        return row


def _in_git(root: Path) -> bool:
    return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True,
                          stdin=subprocess.DEVNULL).returncode == 0


def _clean(root: Path) -> bool:
    """No uncommitted change in the repository (ccx's own .ccx folders aside). A worktree starts from the last
    commit, so with uncommitted work (an earlier piece that ran in the project folder, the lead's own edits) a
    writer in a worktree would start from code that lacks it."""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        for path in line[3:].split(" -> "):
            if ".ccx" not in path.strip().strip('"').replace("\\", "/").split("/"):
                return False
    return True


def _run(a, root: Path) -> int:
    p = paths()
    cfg = load_config(p)
    caller = _caller(a.caller)
    from ..recover import sweep
    sweep(p)                # runs whose ccx was killed (with the whole `q run`): interrupted, their spend in the ledger
    done: list[dict] = []
    if a.q_cmd == "resume":
        # in progress when the machine stopped: continue the same session where there is one, else start again
        q = wq.load(root)
        for it in q["items"].values():
            if it["status"] == "doing":
                runs = item_runs(p, root, it)
                spent = sum(_cost(r) for r in runs)                      # never reached the item: run() didn't return
                cost = round(float(it.get("cost_usd") or 0) + spent, 6)
                last = runs[-1] if runs else {}
                if last.get("ok") and last.get("state") == "finished" and (last.get("result") or {}).get("status") == "done":
                    # it finished; only writing it back to the queue was cut off. In a worktree: commit it there
                    # and keep its branch, so what waits on it still waits for the lead's merge (as in _one)
                    where, sha = _tree_fields(last)
                    wq.update(root, it["id"], status="done", run=last["run_id"], agent=last.get("to"), cost_usd=cost,
                              summary=str((last.get("result") or {}).get("summary") or "")[:300], resume=False,
                              **where)
                    row = {"id": it["id"], "status": "done", "run": last["run_id"], "restored": "finished"}
                    if where["worktree"]:
                        row.update(worktree=where["worktree"], branch=where["branch"], **({"commit": sha} if sha else {}))
                    done.append(row)
                    continue
                # the run it was in the middle of (a review's fix round included): its session goes on
                run_id = last["run_id"] if last.get("session_id") else it.get("run")
                wq.update(root, it["id"], status="todo", resume=bool(run_id), run=run_id, cost_usd=cost)
    width = int(a.max or cfg["defaults"].get("max_parallel", 3))
    gate = bool(getattr(a, "gate", False))
    git = None
    shared: list[str] = []
    while True:
        wq.propagate(root)             # a stuck dependency: what waits for it is dep_blocked, not left todo forever
        q = wq.load(root)
        if q["budget_usd"] is not None and wq.spent(q) >= float(q["budget_usd"]):
            _out({"stopped": "budget reached", "spent_usd": wq.spent(q), "budget_usd": q["budget_usd"],
                  "results": done, "ask": "raise it with `ccx q budget <usd>` if the rest is worth it"})
            return 2
        n = lanes.width(getattr(a, "lanes", None), cfg)
        batch = wq.ready(q, gate)      # pieces naming a common file are never in one round (queue.held_by)
        batch = batch if n else batch[:width]
        if not batch:
            break
        writers = [it["id"] for it in batch if _mode(it)["mode"] == "write"]
        if len(writers) > 1 and git is None:
            git = _in_git(root)
        # parallel writers in one repo must not trample each other: each gets a worktree, as in `ccx batch`.
        # Outside git there is no worktree, and with uncommitted changes a worktree (made from the last commit)
        # would miss them: then they share the folder, as before; task-split's `files` keep them apart
        split = len(writers) > 1 and bool(git)
        if split and not _clean(root):
            split = False
            shared += writers
        tree = {i: split for i in writers}
        if n:
            # warm lanes: ready items for the same agent and mode share at most n sessions, one after another
            def step(it, warm):
                got: dict = {}
                return (_one(it, root, caller, p, cfg, warm=warm, got=got, worktree=tree.get(it["id"], False)),
                        got.get("rec"))
            done += lanes.run_lanes(lanes.split(batch, n, lambda it: (it.get("to"), it.get("mode"))), step,
                                    lanes.limits(cfg), width)
        else:
            with ThreadPoolExecutor(max_workers=width) as ex:
                done += list(ex.map(lambda it: _one(it, root, caller, p, cfg, worktree=tree.get(it["id"], False)),
                                    batch))
        wq.close_parents(root)
        if a.once:
            break
    wq.propagate(root)
    q = wq.load(root)
    out = {"results": done, "open": [i for i in q["order"] if q["items"][i]["status"] not in ("done", "failed")],
           "spent_usd": wq.spent(q), "tree": wq.tree(q)}
    stuck = [i for i in q["order"] if q["items"][i]["status"] == "dep_blocked"]
    if stuck:
        # {piece: the pieces that did not finish behind it}: settle those (fix, then `ccx q done <id> --ok 1`)
        out["dep_blocked"] = {i: q["items"][i].get("blocked_by") or [] for i in stuck}
        out["settle"] = ("each piece under dep_blocked waits on the pieces listed with it, which failed, got "
                         "blocked or need write access: fix or redo those, then `ccx q done <id> --ok 1` and "
                         "`ccx q run` again (or drop the waiting pieces)")
    wait = wq.waiting(q, gate)
    if wait:
        out["waiting"] = wait
        out["next"] = ("they wait for your verdict on what they depend on: check it (merge its worktree branch "
                       "first, if it has one), then `ccx q done <id> --ok 1` and `ccx q run` again")
    waited_on = {x for w in wait for x in w["on"]}
    loose = [u for u in wq.unmerged(q) if u["id"] not in waited_on]
    if loose:
        out["unmerged"] = loose          # nothing waits on them, but their work is only on these branches
    if shared:
        out["shared_folder"] = {"ids": list(dict.fromkeys(shared)), "why": (
            "the project has uncommitted changes, which a worktree (made from the last commit) would not see: these "
            "writers worked side by side in the project folder, as before; commit first to give each its own "
            "worktree")}
    back = {r["id"]: r["restored"] for r in done if r.get("restored")}
    if back:
        # resumed = same session; fresh = started again; decide = needs you; finished = it had finished already
        out["restored"] = back
    _out(out)
    return 0


def register(sub) -> None:
    qp = sub.add_parser("q", help="the project's durable work queue: add pieces, see them, run every ready one")
    qs = qp.add_subparsers(dest="q_cmd", required=True)
    ad = qs.add_parser("add", help="add a piece (or --plan plan.json with ids and deps)")
    ad.add_argument("title", nargs="?", default="")
    ad.add_argument("--brief")
    ad.add_argument("--dep", action="append", help="id it waits for (repeat)")
    ad.add_argument("--parent")
    ad.add_argument("--check", metavar="CMD")
    ad.add_argument("--minutes", type=float)
    ad.add_argument("--mode", choices=["read", "write"])
    ad.add_argument("--kind", choices=["code", "read", "research", "write"])
    ad.add_argument("--to")
    ad.add_argument("--budget", type=float, help="this item's budget (API-equivalent USD); split parts share it")
    ad.add_argument("--plan", help="plan JSON: {\"tasks\": [{id, title?, brief, deps?, check?, minutes?, mode?, kind?, "
                    "to?, files?}]} or task-split's {\"pieces\": [{id, title, depends_on?, files?}]}; a dependency may "
                    "name a later piece; an unknown id is an error")
    for name, hlp in (("ls", "items as JSON"), ("tree", "items as a tree")):
        ls = qs.add_parser(name, help=hlp)
        if name == "ls":
            ls.add_argument("--gate", action="store_true", help="list as ready what `q run --gate` would start")
    bu = qs.add_parser("budget", help="stop `q run` when the queue has spent this much (API-equivalent USD)")
    bu.add_argument("usd", type=float)
    dn = qs.add_parser("done", help="the lead's verdict on an item (also `ccx verify` on its run)")
    dn.add_argument("id")
    dn.add_argument("--ok", type=int, choices=[0, 1], required=True)
    dn.add_argument("--note")
    for name, hlp in (("run", "route and run every ready item, in parallel, until nothing is ready"),
                      ("resume", "after a crash or a closed window: items left 'doing' continue, then run")):
        r = qs.add_parser(name, help=hlp)
        r.add_argument("--max", type=int, help="parallel runs (default: defaults.max_parallel)")
        r.add_argument("--once", action="store_true", help="one round only")
        r.add_argument("--lanes", type=int, metavar="N", help="warm lanes: ready items for the same agent share at "
                       "most N sub-sessions, one item after another (default: [lanes] default, 0 = off)")
        r.add_argument("--gate", action="store_true", help="an item's dependents start only after your verdict "
                       "on it (`ccx q done <id> --ok 1`), not as soon as its run reports done (default: off)")
        r.add_argument("--from", dest="caller")
    for x in (ad, bu, dn):
        x.add_argument("--cwd")
    qp.add_argument("--cwd")
    qp.set_defaults(fn=cmd_q)
