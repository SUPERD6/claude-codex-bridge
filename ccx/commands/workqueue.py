"""ccx q — the project's durable work queue (ccx/queue.py): add pieces, see them, run every ready one."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from .. import lanes, queue as wq
from ..config import load_config, paths
from ..delegate import Request, compact, run, verify
from .common import _caller, _out, apply_mode, resolve


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
            ids: dict[str, str] = {}
            for t in json.loads(Path(a.plan).read_text(encoding="utf-8"))["tasks"]:
                it = wq.add(root, t.get("title") or t["brief"][:60], t["brief"],
                            deps=[ids[d] for d in t.get("deps", []) if d in ids], check=t.get("check"),
                            minutes=t.get("minutes"), mode=t.get("mode"), kind=t.get("kind"), to=t.get("to"))
                ids[t.get("id") or it["id"]] = it["id"]
            _out({"added": list(ids.values())})
            return 0
        it = wq.add(root, a.title, a.brief or a.title, deps=a.dep or [], parent=a.parent, check=a.check,
                    minutes=a.minutes, mode=a.mode, kind=a.kind, to=a.to, budget_usd=a.budget)
        _out(it)
    elif a.q_cmd in ("ls", "tree"):
        from ..recover import sweep
        sweep(paths())                  # as `ccx stats` does: a run whose ccx was killed shows as interrupted
        q = wq.load(root)
        if a.q_cmd == "tree":
            print("\n".join(wq.tree(q)) or "(queue empty)")
        else:
            out = {"items": [q["items"][i] for i in q["order"]], "ready": [x["id"] for x in wq.ready(q)],
                   "spent_usd": wq.spent(q), "budget_usd": q["budget_usd"]}
            held = runner(root)
            if held:
                out["runner"] = held                 # a `q run` (--bg or not) is working on it now
            try:
                out["last_run"] = json.loads((wq.qdir(root) / LAST).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            _out(out)
    elif a.q_cmd == "budget":
        wq.set_budget(root, a.usd)
        _out({"budget_usd": a.usd})
    elif a.q_cmd == "done":
        q = wq.load(root)
        it = q["items"][a.id]
        if it.get("run"):
            verify(paths(), it["run"], bool(a.ok), a.note or "")
        wq.update(root, a.id, status="done" if a.ok else "failed", verdict=bool(a.ok))
        _out({"id": a.id, "closed_parents": wq.close_parents(root)})
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
            if rec.get("label") == f"q:{it['id']}" and Path(rec.get("cwd") or "").resolve() == root.resolve():
                out.append(rec)
        except (OSError, ValueError):
            continue
    return out


def restored(old_run: str, rec: dict) -> str:
    """How an interrupted piece came back (OpenRig's taxonomy): resumed | fresh | decide | failed."""
    if rec.get("kind") in ("quota", "auth", "needs_write", "over_budget", "user_stopped", "interrupted",
                               "check_broken"):
        return "decide"                 # something only the user or the lead can settle
    if not rec.get("ok") or rec.get("kind") in ("check_failed", "timeout", "error"):
        return "failed"
    return "resumed" if rec.get("continued") or rec.get("resumed_from") == old_run else "fresh"


def _one(it: dict, root: Path, caller: str, p, cfg, warm: str | None = None, got: dict | None = None) -> dict:
    """Route and run one queue item; write its outcome back. Never raises (a thread must report).
    warm: a lane's last run (ccx/lanes.py), whose session takes this item as a new task; got["rec"]: its record."""
    try:
        if it.get("budget_usd") is not None and float(it.get("cost_usd") or 0) >= float(it["budget_usd"]):
            wq.update(root, it["id"], status="blocked", summary="its budget is used up")
            return {"id": it["id"], "status": "blocked", "why": "budget"}
        spec = {"brief": it["brief"] + ("\n\n" + wq.SPLIT_HINT if it.get("depth", 0) < wq.MAX_DEPTH else ""),
                "to": it.get("to"), "minutes": it.get("minutes"), "kind": it.get("kind"), "mode": it.get("mode"),
                "cwd": str(root), "force": True}
        if not spec["minutes"]:
            spec["clarity"] = "goal"                       # switch on routing even without an estimate
        apply_mode(spec)
        kw, route = resolve(spec, caller, p, cfg)
        if kw is None:
            wq.update(root, it["id"], status="todo", summary=route.get("advice"))
            return {"id": it["id"], "skipped": route.get("advice")}
        # named up front: `ccx q ls` shows it as `live` while it runs, so a lead can `ccx show <ids> --any --wait`
        live = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        wq.update(root, it["id"], status="doing", agent=kw["to"], live=live)
        resume = it.get("run") if it.get("resume") else None
        left = (max(0.0, float(it["budget_usd"]) - float(it.get("cost_usd") or 0))   # F11: the cap is what it has left
                if it.get("budget_usd") is not None else None)
        brief = (RESUME_NOTE + spec["brief"]) if resume else spec["brief"]
        rec = run(Request(brief=brief, mode=spec["mode"], mode_source=spec["mode_source"], run_id=live,
                          mode_why=spec["mode_why"], cwd=root, caller=caller, label=f"q:{it['id']}",
                          check=it.get("check"), resume_run=resume or warm, continued=bool(warm and not resume),
                          budget_usd=left, **kw), p)
        if got is not None:
            got["rec"] = rec
        res = compact(rec)
        status = res.get("status")
        cost = _cost(rec)
        fields = {"run": rec["run_id"], "agent": rec["to"], "summary": (res.get("summary") or "")[:300],
                  "cost_usd": round(float(it.get("cost_usd") or 0) + cost, 6), "resume": False, "live": None}
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
        if resume:
            out["restored"] = restored(resume, rec)
        return out
    except Exception as e:  # noqa: BLE001
        wq.update(root, it["id"], status="failed", summary=f"{type(e).__name__}: {e}"[:300], live=None)
        return {"id": it["id"], "error": str(e)}


PRESSURE_KINDS = ("quota", "auth")   # an attempt that hit these (runners.py: rate limits are `quota`): start nothing new


def _pressure(rec: dict | None) -> str | None:
    """The quota/auth kind any attempt of this run hit (a fallback to another agent included), else None."""
    for x in (rec or {}).get("attempts") or []:
        if x.get("kind") in PRESSURE_KINDS:
            return x["kind"]
    return (rec or {}).get("kind") if (rec or {}).get("kind") in PRESSURE_KINDS else None


def _over_budget(root: Path) -> dict | None:
    q = wq.load(root)
    if q["budget_usd"] is not None and wq.spent(q) >= float(q["budget_usd"]):
        return {"stopped": "budget reached", "spent_usd": wq.spent(q), "budget_usd": q["budget_usd"],
                "ask": "raise it with `ccx q budget <usd>` if the rest is worth it"}
    return None


def _waves(a, root: Path, caller: str, p, cfg, width: int, n: int, done: list) -> dict | None:
    """Warm lanes: ready items for the same agent and mode share at most n sessions, one after another. An item is
    tried once per `q run` (one routing skipped stays todo and would otherwise be picked again and again)."""
    started: set[str] = set()
    while True:
        stop = _over_budget(root)
        if stop:
            return stop
        batch = [it for it in wq.ready(wq.load(root)) if it["id"] not in started]
        if not batch:
            return None
        started.update(it["id"] for it in batch)
        def step(it, warm):
            got: dict = {}
            return _one(it, root, caller, p, cfg, warm=warm, got=got), got.get("rec")
        done += lanes.run_lanes(lanes.split(batch, n, lambda it: (it.get("to"), it.get("mode"))), step,
                                lanes.limits(cfg), width)
        wq.close_parents(root)
        if a.once:
            return None


def _refill(a, root: Path, caller: str, p, cfg, width: int, done: list) -> dict | None:
    """At most `width` runs at once; whenever one finishes, the slot goes to the next ready item (submit +
    wait-first-completed, not wave by wave). --once: only the items ready at the start. A run any of whose attempts
    hit quota/auth: nothing new starts, the runs in flight finish, then it stops (`stopped: backpressure`)."""
    started: set[str] = set()           # an item is tried once per `q run` (one routing skipped stays todo)
    stop: dict | None = None
    first = True
    with ThreadPoolExecutor(max_workers=max(1, width)) as ex:
        live: dict = {}
        while True:
            if stop is None and (first or not a.once):
                stop = _over_budget(root)
                if stop is None:
                    for it in wq.ready(wq.load(root)):
                        if len(live) >= width:
                            break
                        if it["id"] in started:
                            continue
                        started.add(it["id"])
                        got: dict = {}
                        live[ex.submit(_one, it, root, caller, p, cfg, None, got)] = got
            first = False
            if not live:
                return stop
            fin, _ = wait(list(live), return_when=FIRST_COMPLETED)
            for fu in fin:
                got = live.pop(fu)
                done.append(fu.result())
                kind = _pressure(got.get("rec"))
                if kind and stop is None:
                    stop = {"stopped": "backpressure", "kind": kind, "run": (got.get("rec") or {}).get("run_id"),
                            "ask": "a run hit a quota/auth limit (its fallback may have finished the item): nothing "
                                   "new was started; run `ccx q run --max 1` when it has reset"}
            wq.close_parents(root)


RUNNER = "run.lock"                     # the live `q run` / `q resume` of this queue: {"pid", "started"}
LAST = "last-run.json"                  # how the last one ended (read by `ccx q ls`, for a --bg run's lead)


def runner(root: Path) -> dict | None:
    """The `q run` working on this queue now, or None (no lock, or its process is gone)."""
    from ..runners import pid_alive
    try:
        info = json.loads((wq.qdir(root) / RUNNER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) and pid_alive(info.get("pid")) else None


def _claim(root: Path) -> dict | None:
    """Take the queue's runner lock; the holder's info if another live `q run` has it (two runners would hand
    the same ready item out twice, and `q resume` would re-dispatch items the other one is running)."""
    wq.qdir(root).mkdir(parents=True, exist_ok=True)
    f = wq.qdir(root) / RUNNER
    for _ in range(2):
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = runner(root)
            if held:
                return held
            try:
                f.unlink()              # left by a `q run` that was killed
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "started": time.time()}, fh)
        return None
    return runner(root) or {"pid": None}


def _release(root: Path) -> None:
    f = wq.qdir(root) / RUNNER
    try:
        if json.loads(f.read_text(encoding="utf-8")).get("pid") == os.getpid():
            f.unlink()
    except (OSError, ValueError):
        pass


def _background(a, root: Path) -> int:
    """`ccx q run --bg`: the same command detached (hidden console on Windows), its output in the queue folder.
    detach() drops --bg from the child's arguments, so the child runs in the foreground of its hidden console."""
    from .common import detach
    held = runner(root)
    if held:
        _out(_busy(held))
        return 2
    log = wq.qdir(root) / f"run-bg-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.log"
    detach(sys.argv[1:], log, {})
    _out({"state": "started", "log": str(log),
          "next": "ccx q ls: an item being run shows its run id as `live`; `ccx show <live ids> --any --wait` hands "
                  "back each one as it finishes; `runner` is set while the batch runs, `last_run` says how it ended"})
    return 0


def _busy(held: dict) -> dict:
    return {"stopped": "already running", "pid": held.get("pid"),
            "ask": "another `ccx q run` is working on this queue: follow it with `ccx q ls`, or stop that process "
                   "first"}


def _finish(root: Path, done: list, stop: dict | None) -> tuple[dict, int]:
    """The summary `q run` prints and its exit code. A stop adds its fields (exit 2) unless it is backpressure and
    nothing is left open: then every item is closed and the summary only notes the limit (exit 0)."""
    q = wq.load(root)
    out = {"results": done, "open": [i for i in q["order"] if q["items"][i]["status"] not in ("done", "failed")],
           "spent_usd": wq.spent(q), "tree": wq.tree(q)}
    back = {r["id"]: r["restored"] for r in done if r.get("restored")}
    if back:
        # resumed = same session; fresh = started again; decide = needs you; finished = it had finished already
        out["restored"] = back
    if stop and stop.get("stopped") == "backpressure" and not out["open"]:
        out["backpressure"] = {"kind": stop["kind"], "run": stop.get("run")}
        stop = None
    if stop:
        return {**stop, **out}, 2       # out's spent_usd: counted after the runs in flight finished
    return out, 0


def _run(a, root: Path) -> int:
    if getattr(a, "bg", False):
        return _background(a, root)
    held = _claim(root)
    if held:
        _out(_busy(held))
        return 2
    try:
        out, code = _locked_run(a, root)
    finally:
        _release(root)
    try:
        (wq.qdir(root) / LAST).write_text(json.dumps(
            {"ended": time.time(), "code": code, "stopped": out.get("stopped"), "kind": out.get("kind"),
             "open": out.get("open"), "ask": out.get("ask")}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    _out(out)
    return code


def _locked_run(a, root: Path) -> tuple[dict, int]:
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
                    # it finished; only writing it back to the queue was cut off
                    wq.update(root, it["id"], status="done", run=last["run_id"], agent=last.get("to"), cost_usd=cost,
                              summary=str((last.get("result") or {}).get("summary") or "")[:300], resume=False,
                              live=None)
                    done.append({"id": it["id"], "status": "done", "run": last["run_id"], "restored": "finished"})
                    continue
                # the run it was in the middle of (a review's fix round included): its session goes on
                run_id = last["run_id"] if last.get("session_id") else it.get("run")
                wq.update(root, it["id"], status="todo", resume=bool(run_id), run=run_id, cost_usd=cost, live=None)
    width = int(a.max or cfg["defaults"].get("max_parallel", 3))
    n = lanes.width(getattr(a, "lanes", None), cfg)
    if n:
        stop = _waves(a, root, caller, p, cfg, width, n, done)
    else:
        stop = _refill(a, root, caller, p, cfg, width, done)
    return _finish(root, done, stop)


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
    ad.add_argument("--plan", help="tasks JSON: [{id, title?, brief, deps?, check?, minutes?, mode?, kind?, to?}]")
    for name, hlp in (("ls", "items as JSON"), ("tree", "items as a tree")):
        qs.add_parser(name, help=hlp)
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
        r.add_argument("--from", dest="caller")
        r.add_argument("--bg", action="store_true", help="run detached; its output goes to a log in the queue "
                       "folder; `ccx q ls` shows each running item's run id (`live`), the runner and how the last "
                       "run ended")
    for x in (ad, bu, dn):
        x.add_argument("--cwd")
    qp.add_argument("--cwd")
    qp.set_defaults(fn=cmd_q)
