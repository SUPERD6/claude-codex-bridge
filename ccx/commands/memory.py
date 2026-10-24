"""Shared memory and the project layer: mem, ctx, project, inbox, handoff."""
from __future__ import annotations

import os
import sys

from pathlib import Path

from .. import learn, memory
from ..config import AGENTS, DELEGATE_AGENTS, data_dir, paths
from .common import _caller, _out


def cmd_handoff(a) -> int:
    """Switch leads mid-project (e.g. Claude did tasks 1-4, Codex continues with 5-8)."""
    from .. import project
    import contextlib
    import io
    root = project.find_root() or learn.cp_root(Path.cwd())
    by = a.by or a.from_transcript or _caller(None)    # from a transcript, the old lead is the one handing off
    if by == "user":
        raise ValueError("say who hands off: --by claude|codex|gemini")
    text = Path(a.file).read_text(encoding="utf-8") if a.file else (" ".join(a.text) if a.text else "")
    src = None
    if a.from_transcript:
        src = transcript_handoff(paths(), root, a.from_transcript, a.session, a.max_chars, not a.no_model,
                                 where=Path.cwd())
        if src is None:
            raise ValueError(f"no {a.from_transcript} session file found for {root} (give --session ID)")
        by = a.by or a.from_transcript
        text = src[1] + (f"\n\n## Added by hand\n{text}" if text else "")
    out = project.handoff(root, by, a.to, text)
    if src:
        out["from_transcript"] = str(src[0])
    if a.next:
        p = paths()
        cp = learn.module(p, "checkpoint")
        os.environ["CHECKPOINT_ROOT"] = str(root)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cp.main(["init", "--title", a.title or f"continued by {a.to}", "--agent", a.to,
                     *[x for n in a.next for x in ("--step", n)]])
        out["task"] = buf.getvalue().strip()
        out["next"] = f"in {a.to}: the session start shows this handoff; continue with ccx task resume {out['task']}"
    if not text:
        out["note"] = f"empty template written: fill in {out['handoff']} before switching"
    _out(out)
    return 0


def transcript_handoff(p, root: Path, agent: str, session: str | None = None, max_chars: int | None = None,
                       use_model: bool = True, where: Path | None = None) -> tuple[Path, str] | None:
    """(session file, handoff text) assembled by code from `agent`'s newest main session in `where` (the lead's own
    folder) or else `root`. They differ in a git worktree inside the main checkout: the project layer is the main
    checkout's, but the lead's session and its git state belong to the worktree."""
    from .. import ledger, queue, transcript
    import contextlib
    import io
    mine = {s for r in ledger.rows(p) for s in [r.get("session_id"), *(r.get("sessions") or [])] if s}
    f = None
    for here in dict.fromkeys(x.resolve() for x in (where, root) if x):
        f = transcript.find_session(agent, here, mine, session)
        if f:
            break
    if f is None:
        return None
    d = transcript.read_codex(f) if agent == "codex" else transcript.read_claude(f)
    buf = io.StringIO()
    try:
        cp = learn.module(p, "checkpoint")
        os.environ.setdefault("CHECKPOINT_ROOT", str(root))
        with contextlib.redirect_stdout(buf):
            cp.main(["status", "--quiet"])
    except Exception:                                   # no checkpoint skill / no tasks: nothing to add
        pass
    unfinished = "\n".join(x for x in (buf.getvalue().strip(), queue.unfinished_line(root)) if x)
    cap = max_chars or transcript.MAX_CHARS
    if transcript.empty(d) and use_model:
        made = _handoff_by_model(p, root, agent, f)
        if made:
            return f, transcript.from_model(made[1], made[0], here, f, unfinished, cap)
    return f, transcript.build(d, here, f, unfinished, cap)


def _handoff_by_model(p, root: Path, agent: str, f: Path) -> tuple[str, str] | None:
    """Code couldn't read the session file: a routed sub-agent reads it and writes the handoff (no fixed model)."""
    from .. import transcript
    from ..config import load_config
    from ..delegate import Request, run
    from .common import resolve
    out = root / ".ccx" / "handoff-by-model.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    brief = transcript.MODEL_BRIEF.format(path=f, agent=agent, size=f.stat().st_size // 1024, out=out)
    kw, _ = resolve({"to": "auto", "brief": brief, "mode": "write", "kind": "write", "minutes": 10, "force": True,
                     "tier": "auto", "cwd": str(root)}, _caller(None), p, load_config(p))
    if kw is None:
        return None
    rec = run(Request(brief=brief, mode="write", mode_source="explicit", cwd=root, caller=_caller(None),
                      review="off", ephemeral=True, fallback=True, label="handoff-from-transcript", **kw), p)
    if not rec.get("ok") or not out.exists():
        return None
    last = (rec.get("attempts") or [{}])[-1]
    text = out.read_text(encoding="utf-8", errors="replace")
    out.unlink(missing_ok=True)
    return f"{rec['to']}:{last.get('model')}:{last.get('effort')} (run {rec['run_id']})", text


def cmd_mem(a) -> int:
    p = paths()
    if a.mem_cmd == "add":
        if a.project:
            from .. import project
            root = project.find_root()
            if not root:
                raise ValueError("no project here: run `ccx project init` in the project folder first")
            e = memory.add(project.ProjectPaths(root), " ".join(a.text), by=a.by or _caller(None), topic=a.topic,
                           source=a.source, supersedes=a.supersedes)
        else:
            e = memory.add(p, " ".join(a.text), by=a.by or _caller(None), topic=a.topic, source=a.source,
                           supersedes=a.supersedes)
        _out(e)
    elif a.mem_cmd == "verify":
        _out(memory.verify(p, a.seq, by=_caller(None)))
    elif a.mem_cmd == "search":
        _out({"hits": memory.search(p, a.words)})
    elif a.mem_cmd == "stale":
        _out({"stale": memory.stale(p), "next": "check each: `ccx mem verify N`, or replace: "
                                                "`ccx mem add \"...\" --supersedes N`"})
    elif a.mem_cmd == "delta":
        if os.environ.get("CCX_ROLE") == "subagent":
            return 0          # sub-agents get their context from the brief, not memory deltas
        from .. import project
        parts = [memory.format_delta(memory.delta(p, a.as_, advance=not a.peek))]
        old = memory.stale(p)
        if old:
            parts.append(f"[ccx shared memory: {len(old)} note(s) not checked for {memory.STALE_DAYS}+ days — "
                         f"treat them as 'to check': `ccx mem stale`]")
        root = project.find_root()
        if root:
            parts.append(project.pending_handoff(root, a.as_, advance=not a.peek))
            parts.append(project.delta_text(root, a.as_, advance=not a.peek))
        parts.append(_unfinished_tasks())
        if root:
            try:
                from .. import queue as wq
                parts.append(wq.unfinished_line(root))
            except Exception:  # noqa: BLE001 — never break session start
                pass
        out = "\n\n".join(x for x in parts if x)
        if out:
            print(out)
        if not a.peek:
            try:                       # quiet: probable verdicts for runs nobody judged (H13); never blocks the start
                from ..delegate import soft_verdicts
                soft_verdicts(p)
            except Exception:  # noqa: BLE001
                pass
            try:                       # quiet housekeeping: old finished sub-sessions out of the apps' history
                from .. import archive as arc
                arc.auto(p)
            except Exception:  # noqa: BLE001 — never break session start
                pass
            if os.environ.get("CCX_NO_BENCH_REFRESH") != "1":
                try:                   # weekly public benchmark data for routing, in the background
                    from .. import learn
                    learn.refresh_benchmarks_later(p)
                except Exception:  # noqa: BLE001
                    pass
    elif a.mem_cmd == "show":
        print(p.memory_index.read_text(encoding="utf-8") if p.memory_index.exists() else "(empty)")
        es = memory.entries(p)
        if es:
            print("\n# journal (not yet compacted)")
            for e in es:
                print(f"- #{e['seq']} ({e['by']}, {e['topic']}): {e['text']}")
    elif a.mem_cmd == "status":
        _out({"snapshot": str(p.memory_index), "snapshot_seq": memory.snapshot_seq(p),
              "snapshot_bytes": p.memory_index.stat().st_size if p.memory_index.exists() else 0,
              "journal_entries": len(memory.entries(p)), "cursors": memory.load_cursors(p)})
    elif a.mem_cmd == "compact":
        res = memory.compact(p)
        from ..sync import Plan, sync_memory
        plan = Plan(apply=True)
        sync_memory(p, plan)     # re-render Codex's inlined copy
        res["synced"] = plan.actions
        _out(res)
    return 0


def _unfinished_tasks() -> str:
    """One line per unfinished task-checkpoint task in this repo; '' when none (hook stays silent)."""
    import importlib.util
    script = data_dir("skills") / "task-checkpoint" / "scripts" / "checkpoint.py"
    if not script.exists():
        return ""
    try:
        spec = importlib.util.spec_from_file_location("ccx_checkpoint", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main(["status", "--quiet"])
        return buf.getvalue().strip()
    except (Exception, SystemExit):  # noqa: BLE001 — a hook must never break session start
        return ""


def cmd_project(a) -> int:
    from .. import project
    if a.project_cmd == "init":
        _out(project.init(Path(a.cwd or os.getcwd()).resolve()))
        return 0
    root = project.find_root()
    if not root:
        raise ValueError("no project here: run `ccx project init` first")
    if a.project_cmd == "status":
        pp = project.ProjectPaths(root)
        _out({"project": str(root), "journal_entries": len(memory.entries(pp)),
              "cursors": memory.load_cursors(pp), "inbox": sorted(x.name for x in pp.inbox.glob("*"))
              if pp.inbox.exists() else []})
    elif a.project_cmd == "compact":
        _out(memory.compact(project.ProjectPaths(root)))
    return 0


def cmd_inbox(a) -> int:
    from .. import project
    root = project.find_root()
    if not root:
        raise ValueError("no project here: run `ccx project init` first")
    src = Path(a.file) if a.file else None
    if src is not None and not src.exists():
        raise FileNotFoundError(f"{src} not found")
    text = None if src else (sys.stdin.read() if not sys.stdin.isatty() else "")
    _out(project.inbox_add(root, src, " ".join(a.note), by=a.by or _caller(None), text=text, name=a.name))
    return 0


def cmd_ctx(a) -> int:
    root = Path(a.cwd or os.getcwd())
    f = root / ".ccx" / "context.md"
    if a.ctx_cmd == "init":
        from .. import project
        _out(project.init(root.resolve()))
    elif a.ctx_cmd == "show":
        print(f.read_text(encoding="utf-8") if f.exists() else "(no .ccx/context.md)")
    elif a.ctx_cmd == "add":
        if not f.exists():
            raise SystemExit("run `ccx ctx init` first")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"- {' '.join(a.text)}\n")
        print("ok")
    return 0


def register(sub) -> None:
    ho = sub.add_parser("handoff", help="pass the baton to the other lead (what's done, decisions, next)")
    ho.add_argument("text", nargs="*", help="the handoff text (or --file); empty = write the template")
    ho.add_argument("--to", choices=[*DELEGATE_AGENTS, "any"], required=True)
    ho.add_argument("--by", choices=list(DELEGATE_AGENTS))
    ho.add_argument("--file")
    ho.add_argument("--next", action="append", help="a next task; repeat. Creates a task-checkpoint plan")
    ho.add_argument("--title", help="title for that plan")
    ho.add_argument("--from-transcript", choices=["claude", "codex"],
                    help="assemble the handoff by code from that lead's newest session file in this folder "
                         "(for when it can't write one: quota out, crashed, window closed)")
    ho.add_argument("--session", help="with --from-transcript: a specific session id instead of the newest")
    ho.add_argument("--no-model", action="store_true", help="with --from-transcript: code only; when the code "
                    "can't read the session file's format, don't fall back to a routed sub-agent reading it")
    ho.add_argument("--max-chars", type=int, help="with --from-transcript: size cap (default about one page)")
    ho.set_defaults(fn=cmd_handoff)
    m = sub.add_parser("mem", help="shared incremental memory")
    msub = m.add_subparsers(dest="mem_cmd", required=True)
    ma = msub.add_parser("add")
    ma.add_argument("text", nargs="+")
    ma.add_argument("--by", choices=[*AGENTS, "user"])
    ma.add_argument("--topic", default="general")
    ma.add_argument("--project", action="store_true", help="add to this project's journal instead of the personal one")
    ma.add_argument("--source", help="where the fact came from (file, command, page) — shown with it")
    ma.add_argument("--supersedes", type=int, metavar="N", help="this note replaces note #N")
    mv = msub.add_parser("verify", help="mark note #N as checked today")
    mv.add_argument("seq", type=int)
    ms = msub.add_parser("search", help="notes containing every word")
    ms.add_argument("words", nargs="+")
    msub.add_parser("stale", help="notes not written or checked for 30 days")
    md = msub.add_parser("delta")
    md.add_argument("--as", dest="as_", choices=AGENTS, required=True)
    md.add_argument("--peek", action="store_true", help="do not move the cursor")
    msub.add_parser("show")
    msub.add_parser("status")
    msub.add_parser("compact")
    m.set_defaults(fn=cmd_mem)
    c = sub.add_parser("ctx", help="per-project context file read by every sub-agent")
    csub = c.add_subparsers(dest="ctx_cmd", required=True)
    csub.add_parser("init")
    csub.add_parser("show")
    cadd = csub.add_parser("add")
    cadd.add_argument("text", nargs="+")
    c.add_argument("--cwd")
    c.set_defaults(fn=cmd_ctx)
    pj = sub.add_parser("project", help="project layer (.ccx/): init, status, compact")
    pjs = pj.add_subparsers(dest="project_cmd", required=True)
    pjs.add_parser("init")
    pjs.add_parser("status")
    pjs.add_parser("compact")
    pj.add_argument("--cwd")
    pj.set_defaults(fn=cmd_project)
    ib = sub.add_parser("inbox", help="keep a file/email the user gave you in .ccx/inbox + one journal line")
    ib.add_argument("note", nargs="+", help="one line: what it is and what it asks for")
    ib.add_argument("--file", help="file to keep (omit to read text from stdin, e.g. an email body)")
    ib.add_argument("--name", help="name for the kept copy")
    ib.add_argument("--by", choices=[*AGENTS, "user"])
    ib.set_defaults(fn=cmd_inbox)
