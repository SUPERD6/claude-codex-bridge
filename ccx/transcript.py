"""A handoff written from the outgoing lead's session file, for when it can't write one itself (quota out, crashed,
window closed). Code only — no model tokens. What the next lead needs, most important first: the goal, the agent's
own plan, the person's recent messages, where it stopped, what changed and what failed, the tree on disk, unfinished
tasks, and where the full transcript is.

Formats read (checked against real files, 2026-10-24):
  Codex 0.164 desktop rollouts — event_msg item_completed items: UserMessage, AgentMessage (phase final_answer),
    CommandExecution (command, exit_code, aggregated_output), FileChange (changes: {path: ...});
    task_complete.last_agent_message. Older/headless rollouts: response_item message (role user/assistant),
    function_call update_plan / apply_patch, event_msg user_message / agent_message.
  Claude Code projects/<folder>/<session>.jsonl — user / assistant records; tool_use Edit / Write / MultiEdit
    (file_path), TodoWrite (todos), the desktop app's plan tool (…update_plan, items), Bash + tool_result is_error.
Neither format always carries a plan; the git state is the ground truth and is always included."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

MAX_CHARS = 6000            # about one page (~1.5k tokens); --max-chars to change
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|gh[ousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[A-Za-z0-9-]{10,}"
    r"|(?i:bearer)\s+[A-Za-z0-9._-]{20,}|(?i:(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*)\S{6,}"
    r"|\b[0-9a-f]{40,}\b)")
_INJECTED = ("# AGENTS.md instructions", "<environment_context>", "<user_instructions>", "<permissions",
             "<command-name>", "<local-command", "<system-reminder>", "Caveat:")


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text or "")


_WRAPPED = re.compile(r"<([a-z][a-z0-9_-]*)\b[^>]*>.*?</\1>", re.S)   # app-injected blocks inside a user turn


def _user_text(t: str) -> str | None:
    t = _WRAPPED.sub("", t or "").strip()
    return None if not t or t.startswith(_INJECTED) else t


def read_codex(path: Path) -> dict:
    d = {"agent": "codex", "users": [], "final": "", "plan": [], "files": [], "failed": []}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        pl = e.get("payload") or {}
        typ = pl.get("type")
        it = pl.get("item") or {}
        if typ == "item_completed" and it.get("type") == "UserMessage":
            t = _user_text("".join(c.get("text", "") for c in it.get("content") or []))
            if t:
                d["users"].append(t)
        elif typ == "item_completed" and it.get("type") == "AgentMessage" and it.get("phase") == "final_answer":
            d["final"] = "".join(c.get("text", "") for c in it.get("content") or [])
        elif typ == "item_completed" and it.get("type") == "FileChange":
            d["files"] += list((it.get("changes") or {}).keys())
        elif typ == "item_completed" and it.get("type") == "CommandExecution" and it.get("exit_code") not in (0, None):
            cmd = it.get("command") or []
            d["failed"].append({"cmd": cmd[-1] if isinstance(cmd, list) and cmd else str(cmd),
                                "exit": it.get("exit_code"), "out": (it.get("aggregated_output") or "")[-300:]})
        elif typ == "task_complete" and pl.get("last_agent_message"):
            d["final"] = pl["last_agent_message"]
        elif typ == "user_message":
            t = _user_text(pl.get("message") or "")
            if t:
                d["users"].append(t)
        elif typ == "agent_message" and pl.get("message"):
            d["final"] = pl["message"]
        elif e.get("type") == "response_item" and typ == "function_call":
            try:
                args = json.loads(pl.get("arguments") or "{}")
            except ValueError:
                args = {}
            if pl.get("name") == "update_plan" and isinstance(args.get("plan"), list):
                d["plan"] = [{"step": s.get("step"), "status": s.get("status")} for s in args["plan"]]
            elif pl.get("name") == "apply_patch":
                d["files"] += re.findall(r"\*\*\* (?:Update|Add|Delete) File: (.+)", str(args.get("input") or args))
    if not d["users"]:                        # very old format: user turns only as response_item messages
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                pl = (json.loads(line).get("payload") or {})
            except ValueError:
                continue
            if pl.get("type") == "message" and pl.get("role") == "user":
                t = _user_text("".join(c.get("text", "") for c in pl.get("content") or []))
                if t:
                    d["users"].append(t)
    return d


def read_claude(path: Path) -> dict:
    d = {"agent": "claude", "users": [], "final": "", "plan": [], "files": [], "failed": []}
    bash: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("isSidechain") or e.get("isMeta") or e.get("isCompactSummary"):
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "user":
            if isinstance(content, str):
                t = _user_text(content)
                if t:
                    d["users"].append(t)
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "text":
                    t = _user_text(c.get("text", ""))
                    if t:
                        d["users"].append(t)
                elif c.get("type") == "tool_result" and c.get("is_error") and c.get("tool_use_id") in bash:
                    out = c.get("content")
                    out = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
                    d["failed"].append({"cmd": bash[c["tool_use_id"]], "exit": "error", "out": out[-300:]})
        elif e.get("type") == "assistant":
            texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
            if any(t.strip() for t in texts):
                d["final"] = "\n".join(t for t in texts if t.strip())
            for c in content or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name") or "", c.get("input") or {}
                if name in ("Edit", "Write", "MultiEdit", "NotebookEdit") and inp.get("file_path"):
                    d["files"].append(inp["file_path"])
                elif name == "TodoWrite" and isinstance(inp.get("todos"), list):
                    d["plan"] = [{"step": t.get("content"), "status": t.get("status")} for t in inp["todos"]]
                elif name.endswith("update_plan"):
                    _plan_update(d["plan"], inp)
                elif name == "Bash":
                    bash[c.get("id")] = inp.get("command") or ""
    return d


def _plan_update(plan: list[dict], inp: dict) -> None:
    """The desktop app's plan tool: a whole list (`items`), or a change to the last one: `advance` (finish the
    step in progress, start the next pending one), `done` (1-based steps finished), `start` (step now in progress)."""
    if isinstance(inp.get("items"), list):
        plan[:] = [{"step": t.get("content"), "status": t.get("status")} for t in inp["items"]]
        return
    if inp.get("advance"):
        cur = next((s for s in plan if s["status"] == "in_progress"), None)
        if cur:
            cur["status"] = "completed"
        nxt = next((s for s in plan if s["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"
    for i in inp.get("done") or []:
        if isinstance(i, int) and 0 < i <= len(plan):
            plan[i - 1]["status"] = "completed"
    i = inp.get("start")
    if isinstance(i, int) and 0 < i <= len(plan):
        for s in plan:
            if s["status"] == "in_progress":
                s["status"] = "pending"
        plan[i - 1]["status"] = "in_progress"


def _codex_sessions(home: Path) -> list[Path]:
    return sorted((home / "sessions").rglob("rollout-*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True) \
        if (home / "sessions").exists() else []


def find_session(agent: str, root: Path, exclude: set[str], session: str | None = None,
                 codex_home: Path | None = None, claude_home: Path | None = None) -> Path | None:
    """The newest main session of `agent` in this project folder (not a ccx sub-run, not a sub-agent)."""
    from .config import claude_home as ch, codex_home as xh
    from .usage import codex_parent
    here = str(root.resolve()).lower().rstrip("\\/")
    if agent == "codex":
        for f in _codex_sessions(codex_home or xh()):
            if session and session not in f.name:
                continue
            try:
                with f.open(encoding="utf-8", errors="replace") as fh:
                    meta = (json.loads(fh.readline()) or {}).get("payload") or {}
            except (OSError, ValueError):
                continue
            sid = meta.get("id") or meta.get("session_id")
            if session or (str(meta.get("cwd") or "").lower().rstrip("\\/") == here
                           and meta.get("originator") != "codex_exec" and not codex_parent(meta)
                           and sid not in exclude):
                return f
        return None
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
    base = (claude_home or ch()) / "projects"
    cands = sorted((base / slug).glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True) \
        if (base / slug).exists() else []
    for f in cands:
        if (session and f.stem == session) or (not session and f.stem not in exclude):
            return f
    return None


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _first_sentence(t: str) -> str:
    t = " ".join(t.split())
    m = re.match(r"(.+?[.!?。！？])(\s|$)", t)
    return (m.group(1) if m else t)[:160]


def build(d: dict, root: Path, path: Path, unfinished: str = "", max_chars: int = MAX_CHARS) -> str:
    users = d["users"]
    goal = users[0] if users else "(no user message found)"
    recent = users[-3:] if len(users) > 1 else []
    earlier = users[1:-3] if len(users) > 4 else []
    files = list(dict.fromkeys(d["files"]))
    status = _git(root, "status", "--short")
    stat = _git(root, "diff", "--stat")
    parts = [
        f"_Auto-assembled from the {d['agent']} session file by `ccx handoff --from-transcript` "
        f"({time.strftime('%Y-%m-%d %H:%M')}); the agent did not write it. Check before trusting: the files exist, "
        f"the tests named here pass, `git status` matches._",
        "## Goal (the person's first message)\n" + goal[:1200],
        "## Plan, as the agent last left it\n" + ("\n".join(f"- [{'x' if p.get('status') == 'completed' else ' '}] "
                                                         f"{p.get('step')} ({p.get('status')})" for p in d["plan"])
                                                 or "(no plan list found in the transcript: judge from the sections "
                                                    "below)"),
        "## The person's recent messages\n" + ("\n".join(f"- {u[:600]}" for u in recent) or "(none)")
        + ("\n\nEarlier, first sentences only:\n" + "\n".join(f"- {_first_sentence(u)}" for u in earlier[-8:])
           if earlier else ""),
        "## Where it stopped (the agent's last conclusion)\n" + ((d["final"] or "(none)")[-1500:]),
        "## Files it changed\n" + ("\n".join(f"- {f}" for f in files[-25:]) or "(none recorded)")
        + ("\n\nLast failed commands:\n" + "\n".join(f"- `{x['cmd'][:160]}` (exit {x['exit']}): {x['out'][-160:]}"
                                                     for x in d["failed"][-3:]) if d["failed"] else ""),
        "## On disk now\n```\n" + (status or "(clean or not a git repository)") + "\n```"
        + (f"\n```\n{stat}\n```" if stat else ""),
    ]
    if unfinished:
        parts.append("## Unfinished tasks\n" + unfinished)
    parts.append(f"## Full transcript\n`{path}` — open it for details; it is not copied here.")
    text = redact("\n\n".join(parts))
    if len(text) > max_chars:                    # trim the long free-text parts first, keep the structure
        cut = len(text) - max_chars
        text = text.replace(goal[:1200], goal[:max(200, 1200 - cut)], 1)
        if len(text) > max_chars:
            tail = "\n\n… (trimmed to one page; see the full transcript)"
            text = text[:max_chars - len(tail)] + tail
    return text


def empty(d: dict) -> bool:
    """Code found nothing it recognises (a format it doesn't know): time for the model fallback."""
    return not (d["users"] or d["final"] or d["files"] or d["plan"])


MODEL_BRIEF = """Write a handoff for the next lead from a session file ccx's code could not read (unknown format).
File: {path} ({agent}, {size} KB). Read its last part first, then earlier parts only as needed; do not change it.
Write the handoff, at most one page, to {out} (create that one file, touch nothing else), with these sections:
## Goal  ## Plan (steps and status)  ## The person's recent messages  ## Where it stopped
## Files it changed and failed commands  ## Open questions
Facts from the file only; say Unknown where it doesn't tell. Never copy keys, tokens or passwords."""


def from_model(text: str, by: str, root: Path, path: Path, unfinished: str = "", max_chars: int = MAX_CHARS) -> str:
    status = _git(root, "status", "--short")
    parts = [f"_Written by {by} from the session file (`ccx handoff --from-transcript`, model fallback: the code "
             f"could not read its format; {time.strftime('%Y-%m-%d %H:%M')}). Check before trusting._",
             text.strip()[:max_chars * 3 // 4],
             "## On disk now\n```\n" + (status or "(clean or not a git repository)") + "\n```"]
    if unfinished:
        parts.append("## Unfinished tasks\n" + unfinished)
    parts.append(f"## Full transcript\n`{path}`")
    out = redact("\n\n".join(parts))
    return out if len(out) <= max_chars else out[:max_chars - 20] + "\n\n… (trimmed)"
