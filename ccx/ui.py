"""`ccx ui`: a read-only live view on this machine (proposal G1).

What it shows, all read from files ccx and the two tools already write — no model is ever called and the quota
probe is never started (an open page must not cost anything):
  run records      <hub>/ccx/runs/<id>/run.json (+ prompt.md for the task text); live ones are 'running'
  verdicts         <hub>/ccx/ledger.jsonl rows with type=verify (read incrementally)
  work queues      <project>/.ccx/queue/queue.jsonl of every project a recent run worked in (and --project)
  live tokens      the sub-agent's own session file while it runs (Codex rollout-*.jsonl, Claude <session>.jsonl);
                   its last write time is the heartbeat
  quota            quota.pace() over the readings already kept (Codex session logs, <hub>/ccx/quota.jsonl)
  leads            main Claude / Codex conversations written to in the last 15 minutes: model, own sub-agents

Grouping: a project = the folder a run worked in (worktrees fold back into their repo). A task = one project's work
queue (pieces = its items, split items drill down a level, at most 3), or the runs one lead conversation sent out
(pieces = runs; a fix round or a follow-up stays on its piece). Strings shown to people are keys into
ui_static/strings.json; data (titles, summaries) is sent as plain text and the page escapes it.

Server: standard-library HTTP on 127.0.0.1, a random port. The token rides after '#' in the URL (never sent to the
server, never in a request line) and comes back in an X-CCX-Token header on every data request; Host must be
127.0.0.1 or localhost with this port (DNS rebinding), there are no CORS headers, and the page loads only its own
files (CSP). The page polls every 3 s and says 'still open' every 10 s; 60 s without that and the server exits.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import agents
from . import queue as wq
from .config import Paths, claude_home, codex_home, load_config
from .ledger import is_eval
from .usage import _ts

STATIC = Path(__file__).resolve().parent / "ui_static"
INTERNAL = ("review:", "quota-probe", "selftest", "handoff-from-transcript")
STALE_MIN = 10                # a running run with no write for this long may be stuck
LEAD_MIN = 15                 # a lead conversation counts as current when written to this recently
POLL_S, BEAT_S, IDLE_S, FIRST_BEAT_S = 3, 10, 60, 120
QUOTA_EVERY_S, LEADS_EVERY_S = 60, 15
TITLE_MAX = 90
VERDICTS_TO_KNOW = 30         # verdicts before "how much was saved" is worth a number


# ------------------------------------------------------------------ reading files (cached by mtime)
class Reader:
    """Keeps what it read between polls: a file is parsed again only when its mtime or size changed, and the
    ledger and live session files are read from where the last read stopped."""

    def __init__(self, p: Paths):
        self.p = p
        self._json: dict[Path, tuple] = {}
        self._tail: dict[tuple, dict] = {}
        self._busy: set[str] = set()
        self._found: dict[str, Path | None] = {}
        self._timed: dict[str, tuple[float, object]] = {}

    def json_file(self, f: Path):
        try:
            st = f.stat()
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        hit = self._json.get(f)
        if hit and hit[0] == key:
            return hit[1]
        try:
            val = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return hit[1] if hit else None          # half-written: keep the last good copy
        self._json[f] = (key, val)
        return val

    def lines(self, f: Path, fold, start):
        """Fold each new complete line into a running state (fold(state, line) -> state); returns the state."""
        try:
            size = f.stat().st_size
        except OSError:
            return start
        key = (f, fold.__name__)                     # one file can be read for different things
        t = self._tail.get(key)
        if t is None or size < t["pos"]:            # new, or rewritten (e.g. ccx repair): start over
            t = self._tail[key] = {"pos": 0, "state": start, "rest": b""}
        if size > t["pos"]:
            try:
                with open(f, "rb") as fh:
                    fh.seek(t["pos"])
                    chunk = fh.read(size - t["pos"])
            except OSError:
                return t["state"]
            t["pos"] = size
            data = t["rest"] + chunk
            *full, t["rest"] = data.split(b"\n")
            for raw in full:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    t["state"] = fold(t["state"], line)
        return t["state"]

    def cfg(self) -> dict:
        return self.every("cfg", 30, lambda: load_config(self.p))

    def every(self, key: str, seconds: float, make):
        hit = self._timed.get(key)
        if hit and time.time() - hit[0] < seconds:
            return hit[1]
        val = make()
        self._timed[key] = (time.time(), val)
        return val

    def find(self, key: str, search):
        if key not in self._found or self._found[key] is None:
            self._found[key] = search()
        return self._found[key]


def _verdict_rows(state: dict, line: str) -> dict:
    if '"verify"' in line:
        try:
            r = json.loads(line)
        except ValueError:
            return state
        if r.get("type") == "verify" and r.get("run_id"):
            state[r["run_id"]] = r                  # the last one wins
    return state


def project_root(cwd: str | None) -> Path | None:
    """The project a run worked in: worktrees fold back into their repo, then the nearest folder with a .ccx
    folder or a .git; else the folder itself. No subprocess, no writes."""
    if not cwd:
        return None
    try:
        c = Path(cwd).resolve()                     # one spelling per folder (Windows short names, symlinks)
    except OSError:
        c = Path(cwd)
    parts = c.parts
    if ".ccx-worktrees" in parts:                   # <parent>/.ccx-worktrees/<repo>/<run_id> (delegate.make_worktree)
        i = parts.index(".ccx-worktrees")
        if i + 1 < len(parts):
            c = Path(*parts[:i]) / parts[i + 1]
    home = Path.home()
    for d in (c, *c.parents):
        if d == home and c != home:                 # ~/.ccx is ccx's own settings, not a project
            break
        if (d / ".ccx" / "context.md").exists() or (d / ".ccx" / "queue").is_dir() or (d / ".git").exists():
            return d
    return c


def _pid(root: Path) -> str:
    return "p" + hashlib.sha1(str(root).lower().encode("utf-8")).hexdigest()[:10]


def _sid(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", text)[:64]


def _brief_of(run_dir: Path) -> str:
    try:
        text = (run_dir / "prompt.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r"## Task\n(.*?)(?:\n## Finish|\Z)", text, re.S)
    if m:
        return m.group(1).strip()
    return "\n".join(text.splitlines()[1:]).strip()       # a follow-up: the brief follows its first line


def _short(text: str) -> str:
    line = next((x.strip() for x in (text or "").splitlines() if x.strip()), "")
    return line if len(line) <= TITLE_MAX else line[:TITLE_MAX - 1] + "…"


# ------------------------------------------------------------------ live usage from the sub-agent's session file
def _fold_codex(state: dict, line: str) -> dict:
    if '"token_count"' in line:
        try:
            info = ((json.loads(line).get("payload") or {}).get("info") or {})
        except ValueError:
            return state
        tot = info.get("total_token_usage")
        if tot:
            state = {**state, "tokens": int(tot.get("input_tokens", 0) or 0) + int(tot.get("output_tokens", 0) or 0)}
    return state


def _fold_claude(state: dict, line: str) -> dict:
    if '"assistant"' in line and '"usage"' in line:
        try:
            e = json.loads(line)
        except ValueError:
            return state
        m = e.get("message") or {}
        u = m.get("usage") or {}
        if e.get("type") == "assistant" and u and m.get("id") not in state["ids"]:
            state["ids"].add(m.get("id"))
            state["tokens"] += sum(int(u.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                    "cache_read_input_tokens", "output_tokens"))
            state["model"] = m.get("model") or state.get("model")
    return state


def _session_file(rd: Reader, agent: str, sid: str) -> Path | None:
    """The session file of `sid` under the agent's own folder (its adapter's home). Only Codex and Claude Code
    sessions are read; the layout is each tool's own (see their adapters' session_files)."""
    def search():
        home = agents.get(agent).home() if agent in agents.NAMES and agents.get(agent).home else None
        if home is None:
            return None
        if agent == "codex":
            root = home / "sessions"
            hits = sorted(root.rglob(f"rollout-*{sid}.jsonl")) if root.exists() else []
        elif agent == "claude":
            root = home / "projects"
            hits = sorted(root.glob(f"*/{sid}.jsonl")) if root.exists() else []
        else:
            hits = []
        return hits[-1] if hits else None
    return rd.find(f"{agent}:{sid}", search)


def cli_of(name: str | None, cfg: dict) -> str | None:
    """The CLI an agent name runs on: itself, or for a provider (e.g. deepseek) the CLI it is configured on."""
    pv = (cfg.get("providers") or {}).get(name or "")
    return str(pv.get("agent", "claude")) if pv is not None else name


def live(rd: Reader, rec: dict) -> dict:
    """Tokens so far and the last sign of life of a running run."""
    beat = 0.0
    run_dir = rd.p.runs / rec["run_id"]
    for f in (run_dir, run_dir / "run.json"):
        try:
            beat = max(beat, f.stat().st_mtime)
        except OSError:
            pass
    out = {"beat": beat, "tokens": None}
    sid = rec.get("session_id")
    cli = cli_of(rec.get("to"), rd.cfg())
    if sid and cli in ("codex", "claude"):
        f = _session_file(rd, cli, sid)
        if f:
            try:
                out["beat"] = max(beat, f.stat().st_mtime)
            except OSError:
                pass
            st = rd.lines(f, _fold_codex, {"tokens": 0}) if cli == "codex" else \
                rd.lines(f, _fold_claude, {"tokens": 0, "ids": set(), "model": None})
            out["tokens"] = st["tokens"]
    return out


# ------------------------------------------------------------------ one run -> one piece on the chart
def _usd(rec: dict) -> float:
    return round(sum(a.get("ae_usd") or 0 for a in rec.get("attempts") or [])
                 + float((rec.get("review") or {}).get("usd") or 0), 6)


def _tokens(rec: dict) -> int:
    return sum(int(v or 0) for a in rec.get("attempts") or [] for v in (a.get("usage") or {}).values())


def _q(s: str) -> str:
    """Quote one argument for the copied command line (double quotes work in PowerShell, cmd and sh)."""
    s = str(s).replace('"', "'")
    return f'"{s}"' if re.search(r"\s|[&|<>^;]", s) or not s else s


def _btn(label: str, cmd: str, style: str = "") -> dict:
    return {"label": label, "cmd": cmd, "style": style}


def _act(rec: dict, verdict: dict | None, now: float, beat: float | None) -> dict | None:
    """What the person is asked to do about this run, or None. kind: decide (red) | review (amber)."""
    rid = rec["run_id"]
    res = rec.get("result") or {}
    kind = rec.get("kind")
    show = _btn("b_see", f"ccx show {rid} --full")
    if rec.get("state") == "running":
        if beat and now - beat > STALE_MIN * 60:
            return {"kind": "decide", "what": "a_stale", "why": ["w_stale", {"m": int((now - beat) // 60)}],
                    "buttons": [show, _btn("b_resume_later", f"ccx resume {rid}")]}
        return None
    if verdict is not None or (rec.get("verdict") or {}).get("ok") is not None:
        return None                                  # judged (by the person, the lead or ccx's soft verdict)
    if kind == "needs_write":
        return {"kind": "decide", "what": "a_needs_write", "why": ["w_needs_write", {}],
                "buttons": [show, _btn("b_allow_write",
                                       f"ccx run --mode write --cwd {_q(rec.get('cwd') or '.')} "
                                       f"{_q(f'Make the changes run {rid} listed as needed (see ccx show {rid} --full)')}",
                                       "primary"),
                            _btn("b_not_needed", f"ccx verify {rid} --ok 0 --reason other --note {_q('not needed')}")]}
    if kind == "review_failed":
        issues = "; ".join((rec.get("review") or {}).get("issues") or [])[:300]
        return {"kind": "decide", "what": "a_review_failed", "why": ["w_review_failed", {"by": _who_rung(
            (rec.get("review") or {}).get("by"))}],
                "issues": (rec.get("review") or {}).get("issues") or [],
                "buttons": [show, _btn("b_one_more", f"ccx resume {rid} {_q('The review still finds: ' + issues)}",
                                       "primary"),
                            _btn("b_myself", f"ccx verify {rid} --ok 0 --reason wrong --note {_q('handled by hand')}")]}
    if kind == "check_failed":
        c = rec.get("check") or {}
        return {"kind": "decide", "what": "a_check_failed", "why": ["w_check_failed", {"cmd": c.get("cmd") or "",
                                                                                         "exit": c.get("exit")}],
                "buttons": [show, _btn("b_fix_check", f"ccx resume {rid} {_q('the check fails: fix it')}", "primary")]}
    if kind in ("quota", "timeout"):
        ra = ((rec.get("attempts") or [{}])[-1]).get("retry_after")
        return {"kind": "decide", "what": "a_quota" if kind == "quota" else "a_timeout",
                "why": ["w_quota" if kind == "quota" else "w_timeout", {"at": ra}],
                "buttons": [_btn("b_resume", f"ccx resume {rid}", "primary"), show]}
    if kind == "over_budget":
        return {"kind": "decide", "what": "a_over_budget", "why": ["w_over_budget", {}],
                "buttons": [show, _btn("b_resume", f"ccx resume {rid}", "primary")]}
    if rec.get("auth_problem"):
        return {"kind": "decide", "what": "a_auth", "why": ["w_auth", {"agent": rec.get("to")}],
                "buttons": [_btn("b_login", f"{rec.get('to')} login", "primary")]}
    if not rec.get("ok") or res.get("status") in ("failed", "blocked"):
        return {"kind": "decide", "what": "a_failed", "why": ["w_failed", {}],
                "buttons": [show, _btn("b_retry", f"ccx resume {rid} {_q('Try again: ' + (res.get('summary') or rec.get('error') or '')[:200])}",
                                       "primary")]}
    if res.get("status") in ("done", "partial"):
        return {"kind": "review", "what": "a_review", "why": None, "reasons": True,
                "buttons": [_btn("b_ok", f"ccx verify {rid} --ok 1", "good"),
                            _btn("b_bad", f"ccx verify {rid} --ok 0 --reason {{reason}} --note {{note}}", "bad"),
                            _btn("b_see_change", _diff_cmd(rec))]}
    return None


def _diff_cmd(rec: dict) -> str:
    files = (rec.get("result") or {}).get("files_changed") or []
    cwd = rec.get("cwd") or "."
    return f"git -C {_q(cwd)} diff -- " + " ".join(_q(f) for f in files[:8]) if files else \
        f"ccx show {rec['run_id']} --full"


def _who_rung(rung: str | None) -> str:
    if not rung:
        return ""
    bits = str(rung).split(":")
    return " · ".join(b for b in bits[:2] if b)


STEP = {"sent": 0, "working": 1, "self": 2, "check": 3, "review": 4, "verdict": 5, "done": 6}


def piece_of_run(rd: Reader, rec: dict, verdict: dict | None, now: float, title: str) -> dict:
    atts = rec.get("attempts") or []
    last = atts[-1] if atts else {}
    first = rec.get("first_rung") or ""
    model = last.get("model") or (first.split(":")[1] if first.count(":") >= 1 else "")
    res = rec.get("result") or {}
    running = rec.get("state") == "running"
    lv = live(rd, rec) if running else {"beat": None, "tokens": None}
    act = _act(rec, verdict, now, lv["beat"])
    v = verdict if verdict is not None else rec.get("verdict")
    skip = []
    if not rec.get("check"):
        skip.append(STEP["check"])
    if not rec.get("review") or (rec.get("review") or {}).get("verdict") == "not-run":
        skip.append(STEP["review"])
    if running:
        status, step = "run", STEP["working"]
    elif act and act["kind"] == "decide":
        status = "decide"
        step = {"check_failed": STEP["check"], "review_failed": STEP["review"]}.get(rec.get("kind"), STEP["working"])
    elif act and act["kind"] == "review":
        status, step = "review", STEP["verdict"]
    elif v is not None and v.get("ok") is False:
        status, step = "fail", STEP["verdict"]
    else:
        status, step = "done", STEP["done"]
    secs = round(sum(a.get("seconds") or 0 for a in atts), 1)
    if running:
        secs = round(now - float(rec.get("ts") or now), 1)
    rv = rec.get("review") or {}
    piece = {
        "id": _sid(rec["run_id"]), "run_id": rec["run_id"], "title": title, "worker": rec.get("to"),
        "model": model, "effort": last.get("effort"), "mode": rec.get("mode"), "status": status, "step": step,
        "skip": skip, "secs": secs, "usd": _usd(rec), "tokens": lv["tokens"] if running and lv["tokens"] else _tokens(rec),
        "live": running, "beat": lv["beat"], "ts": rec.get("ts"),
        "reviewer": _who_rung(rv.get("by")) if rv.get("verdict") not in (None, "not-run") else None,
        "summary": res.get("summary") or rec.get("error") or "", "files": res.get("files_changed") or [],
        "check": ({"cmd": rec["check"].get("cmd"), "passed": rec["check"].get("passed")} if rec.get("check") else None),
        "review": ({"verdict": rv.get("verdict"), "issues": rv.get("issues") or []} if rv else None),
        "verdict": ({"ok": v.get("ok"), "soft": bool(v.get("soft")), "reason": v.get("reason")} if v else None),
        "attempts": len(atts), "rungs": [a.get("rung") for a in atts],
        "native": [{"id": k[-8:], "tokens": int(sum(x.values())) if isinstance(x, dict) else 0}
                   for k, x in (rec.get("codex_children") or {}).items()],
        "act": act,
    }
    return piece


def hist_of_run(rec: dict, title: str) -> list[dict]:
    """The 'history' timeline of one run: sent, escalations, review, outcome, verdict."""
    out = [{"ts": rec.get("ts"), "k": "h_sent", "p": {"t": title, "w": rec.get("to") or "",
                                                       "m": ((rec.get("attempts") or [{}])[0]).get("model") or ""}}]
    t = float(rec.get("ts") or 0)
    prev = None
    for a in rec.get("attempts") or []:
        t += float(a.get("seconds") or 0)
        if prev and a.get("rung") != prev.get("rung"):
            out.append({"ts": t, "k": "h_moved", "p": {"from": prev.get("rung") or "", "to": a.get("rung") or ""}})
        prev = a
    rv = rec.get("review") or {}
    if rv.get("verdict") in ("pass", "issues", "unclear"):
        out.append({"ts": t, "k": "h_review_" + rv["verdict"], "p": {"by": _who_rung(rv.get("by")), "t": title},
                    "tone": "bad" if rv["verdict"] == "issues" else "ok" if rv["verdict"] == "pass" else ""})
    if rec.get("state") == "finished":
        k = rec.get("kind")
        st = (rec.get("result") or {}).get("status")
        key = ("h_" + k) if k in ("needs_write", "check_failed", "review_failed", "quota", "timeout", "over_budget") \
            else "h_done" if rec.get("ok") and st in ("done", "partial") else "h_failed"
        out.append({"ts": t, "k": key, "p": {"t": title}, "tone": "ok" if key == "h_done" else "bad"})
    v = rec.get("verdict") or {}
    if v.get("ok") is not None:
        out.append({"ts": v.get("ts") or t, "k": "h_verdict_ok" if v["ok"] else "h_verdict_bad",
                    "p": {"t": title, "soft": bool(v.get("soft"))}, "tone": "ok" if v["ok"] else "bad"})
    return out


# ------------------------------------------------------------------ lead conversations
def _first_user_text(f: Path, agent: str) -> str:
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if n > 400:
                    break
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                text = ""
                if agent == "claude" and e.get("type") == "user" and not e.get("isSidechain"):
                    c = (e.get("message") or {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
                    text = c if isinstance(c, str) else ""
                elif agent == "codex" and (e.get("payload") or {}).get("type") == "user_message":
                    text = (e.get("payload") or {}).get("message") or ""
                lines = [x for x in text.splitlines() if x.strip() and not x.lstrip().startswith("<")]
                if lines:                                # "1" or "ok" names nothing: the run's own title is better
                    return _short("\n".join(lines)) if len(lines[0].strip()) >= 6 else ""
    except OSError:
        pass
    return ""


def _tail_lines(f: Path, nbytes: int = 200_000) -> list[str]:
    try:
        with open(f, "rb") as fh:
            fh.seek(max(0, f.stat().st_size - nbytes))
            return fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _claude_leads(since: float, mine: set[str]) -> list[dict]:
    root = claude_home() / "projects"
    out = []
    for f in (root.glob("*/*.jsonl") if root.exists() else []):
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if mt < since or f.stem in mine:
            continue
        model, cwd = "", ""
        for line in reversed(_tail_lines(f)):
            if '"assistant"' in line and '"model"' in line:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("isSidechain"):
                    continue
                model, cwd = (e.get("message") or {}).get("model") or "", e.get("cwd") or ""
                break
        if not model or model.startswith("<"):
            continue
        helpers = []
        sub = f.parent / f.stem / "subagents"
        for h in (sub.glob("agent-*.jsonl") if sub.is_dir() else []):
            try:
                if h.stat().st_mtime >= since:
                    helpers.append({"id": h.stem[-8:], "model": _last_model(h)})
            except OSError:
                pass
        out.append({"agent": "claude", "model": model, "session": f.stem, "cwd": cwd, "last": mt,
                    "helpers": helpers})
    return out


def _last_model(f: Path) -> str:
    for line in reversed(_tail_lines(f, 60_000)):
        if '"model"' in line:
            try:
                return ((json.loads(line).get("message") or {}).get("model")) or ""
            except ValueError:
                continue
    return ""


def _codex_leads(since: float, mine: set[str]) -> list[dict]:
    root = codex_home() / "sessions"
    days = {time.strftime("%Y/%m/%d", time.localtime(t)) for t in (since, time.time())}
    out = []
    for d in days:
        for f in ((root / d).glob("rollout-*.jsonl") if (root / d).is_dir() else []):
            try:
                mt = f.stat().st_mtime
                with open(f, encoding="utf-8", errors="replace") as fh:
                    meta = (json.loads(fh.readline() or "{}").get("payload") or {})
            except (OSError, ValueError):
                continue
            sid = meta.get("id") or f.stem
            if mt < since or sid in mine or meta.get("originator") == "codex_exec":
                continue
            src = meta.get("source")
            if isinstance(src, dict) and src.get("subagent"):
                continue
            model = ""
            for line in reversed(_tail_lines(f)):
                if '"turn_context"' in line:
                    try:
                        model = ((json.loads(line).get("payload") or {}).get("model")) or ""
                    except ValueError:
                        continue
                    break
            from .usage import codex_children
            kids = codex_children(sid, since)
            out.append({"agent": "codex", "model": model, "session": sid, "cwd": meta.get("cwd") or "",
                        "last": mt, "helpers": [{"id": k[-8:], "model": ""} for k in kids]})
    return out


def leads(rd: Reader, mine: set[str]) -> list[dict]:
    def make():
        since = time.time() - LEAD_MIN * 60
        found = []
        for fn in (_claude_leads, _codex_leads):
            try:
                found += fn(since, mine)
            except Exception:  # noqa: BLE001 — a tool's odd file never breaks the page
                pass
        return sorted(found, key=lambda x: -x["last"])[:6]
    return rd.every("leads", LEADS_EVERY_S, make)


def _lead_of_session(rd: Reader, sid: str, caller: str | None) -> dict:
    """agent/model/title of the conversation that sent runs out (read once per session)."""
    def look():
        for agent in ([caller] if caller in ("claude", "codex") else []) + ["claude", "codex"]:
            f = _session_file(rd, agent, sid)
            if f:
                model = _last_model(f) if agent == "claude" else ""
                if agent == "codex":
                    for line in reversed(_tail_lines(f)):
                        if '"turn_context"' in line:
                            try:
                                model = ((json.loads(line).get("payload") or {}).get("model")) or ""
                            except ValueError:
                                continue
                            break
                return {"agent": agent, "model": model, "title": _first_user_text(f, agent)}
        return {"agent": caller if caller in ("claude", "codex") else None, "model": "", "title": ""}
    return rd.every(f"lead:{sid}", 30, look)


# ------------------------------------------------------------------ quota (readings only, never the probe)
def _fold_rate(state: list, line: str) -> list:
    """Codex quota samples, as usage.codex_events reads them (token_count lines carry rate_limits)."""
    if '"rate_limits"' not in line:
        return state
    try:
        e = json.loads(line)
    except ValueError:
        return state
    pl = e.get("payload") or {}
    t = _ts(e.get("timestamp"))
    if pl.get("type") != "token_count" or t is None:
        return state
    for win in ("primary", "secondary"):
        w = (pl.get("rate_limits") or {}).get(win) or {}
        if w.get("used_percent") is not None:
            state.append({"ts": t, "agent": "codex", "window": win, "used": w["used_percent"] / 100,
                          "resets_at": w.get("resets_at"), "window_minutes": w.get("window_minutes")})
    return state


def _codex_rates(rd: Reader, days: float = 8) -> list[dict]:
    """quota.codex_readings(), but only the new part of each session file is read on later calls."""
    root = codex_home() / "sessions"
    since = time.time() - days * 86400
    out = []
    for k in range(int(days) + 2):
        d = root / time.strftime("%Y/%m/%d", time.localtime(time.time() - k * 86400))
        for f in (d.glob("rollout-*.jsonl") if d.is_dir() else []):
            try:
                if f.stat().st_mtime < since:
                    continue
            except OSError:
                continue
            out += [r for r in rd.lines(f, _fold_rate, []) if r["ts"] >= since]
    return out


def quota_view(rd: Reader, wait: bool = True) -> list[dict]:
    """Pace of every quota window from the readings already on disk. wait=False (the server): the first read of
    a week of Codex logs takes seconds, so it runs in the background and the page shows quota a moment later."""
    def make():
        from . import quota
        out = []
        for agent, readings in (("codex", _codex_rates(rd)), ("claude", quota.claude_readings(rd.p))):
            for win, w in (quota.pace(readings) if readings else {}).items():
                out.append({"agent": agent, "window": win, **{k: w.get(k) for k in (
                    "used", "projected", "resets_at", "hours_left", "reading_age_min", "note")},
                    "minutes": next((r.get("window_minutes") for r in readings if r["window"] == win), None)})
        return out

    def safe():
        try:
            return make()
        except Exception:  # noqa: BLE001 — odd log lines never break the page
            return []
    hit = rd._timed.get("quota")
    if wait or (hit and time.time() - hit[0] < QUOTA_EVERY_S):
        return rd.every("quota", QUOTA_EVERY_S, safe)
    if "quota" not in rd._busy:
        rd._busy.add("quota")

        def bg():
            try:
                rd._timed["quota"] = (time.time(), safe())
            finally:
                rd._busy.discard("quota")
        threading.Thread(target=bg, daemon=True).start()
    return hit[1] if hit else []


# ------------------------------------------------------------------ the whole page's data
def _queue_pieces(rd: Reader, root: Path, q: dict, recs: dict, verdicts: dict, now: float) -> list[dict]:
    items = q["items"]

    def one(it: dict) -> dict:
        rec = recs.get(it.get("run")) if it.get("run") else None
        title = it.get("title") or _short(it.get("brief") or "")
        if rec:
            pc = piece_of_run(rd, rec, verdicts.get(rec["run_id"]), now, title)
        else:
            pc = {"id": _sid(it["id"]), "run_id": it.get("run"), "title": title, "worker": it.get("agent") or it.get("to"),
                  "model": "", "status": "queued", "step": STEP["sent"], "skip": [], "secs": 0,
                  "usd": float(it.get("cost_usd") or 0), "tokens": 0, "live": False, "summary": it.get("summary") or "",
                  "files": [], "check": None, "review": None, "verdict": None, "attempts": 0, "rungs": [], "native": [],
                  "act": None, "ts": it.get("added")}
        pc["id"], pc["qid"] = _sid(it["id"]), it["id"]
        pc["usd"] = round(float(it.get("cost_usd") or pc["usd"] or 0), 6)
        st = it.get("status")
        cmd_done = f"ccx q done {it['id']} --ok 1 --cwd {_q(str(root))}"
        if st == "todo":
            pc.update(status="queued", act=None)
        elif st == "doing" and pc["status"] not in ("run", "decide"):
            pc["status"] = "run"
        elif st == "done" and it.get("verdict") is not None:
            pc.update(status="done" if it["verdict"] else "fail", step=STEP["done"], act=None)
        elif st == "done" and pc.get("act") and pc["act"]["kind"] == "review":
            pc["act"]["buttons"][0]["cmd"] = cmd_done
            pc["act"]["buttons"][1]["cmd"] = (f"ccx q done {it['id']} --ok 0 --note {{note}} --cwd {_q(str(root))}")
        elif st in ("needs_write", "blocked", "failed") and not pc.get("act"):
            show = _btn("b_see", f"ccx show {it['run']} --full") if it.get("run") else _btn("b_tree", "ccx q tree")
            pc.update(status="decide", act={"kind": "decide", "what": "a_q_" + st, "why": ["w_q_" + st,
                                                                                             {"s": it.get("summary") or ""}],
                                            "buttons": [show, _btn("b_q_resume", f"ccx q resume --cwd {_q(str(root))}",
                                                                   "primary")]})
        kids = wq.children(q, it["id"])
        if kids:
            pc["children"] = [one(k) for k in kids]
            if st == "split":                         # waits on its parts: they carry the status, a level down
                pc.update(status="split", act=None, step=STEP["working"])
        return pc
    return [one(items[i]) for i in q["order"] if not items[i].get("parent")]


def collect(p: Paths, project: Path | None = None, days: float = 7, rd: Reader | None = None,
            now: float | None = None, quota_wait: bool = True) -> dict:
    rd = rd or Reader(p)
    now = now or time.time()
    since = now - days * 86400
    cfg = load_config(p)
    verdicts = rd.lines(p.ledger, _verdict_rows, {}) if p.ledger.exists() else {}
    recs: dict[str, dict] = {}
    if p.runs.exists():
        for d in p.runs.iterdir():
            f = d / "run.json"
            try:
                if f.stat().st_mtime < since:
                    continue
            except OSError:
                continue
            rec = rd.json_file(f)
            if isinstance(rec, dict) and rec.get("run_id"):
                recs[rec["run_id"]] = rec
    proj = project.resolve() if project else None
    shown = {rid: r for rid, r in recs.items()
             if not r.get("ephemeral") and not str(r.get("label") or "").startswith(INTERNAL)}
    mine = {s for r in recs.values() for s in [r.get("session_id"), *[a.get("session_id") for a in r.get("attempts") or []]] if s}

    # projects and their queues
    roots: dict[Path, dict] = {}

    def root_of(r: dict) -> Path:
        return project_root(r.get("cwd")) or Path(".")

    for r in shown.values():
        roots.setdefault(root_of(r), {})
    if proj:
        roots = {k: v for k, v in roots.items() if k == proj}
        roots.setdefault(proj, {})
    tasks_by_root: dict[Path, list[dict]] = {k: [] for k in roots}
    in_queue: set[str] = set()
    for root in roots:
        qf = wq.qdir(root) / "queue.jsonl"
        if not qf.exists():
            continue
        try:
            st = qf.stat()
            key = ("queue", st.st_mtime_ns, st.st_size)
        except OSError:
            continue
        hit = rd._json.get(qf)
        q = hit[1] if hit and hit[0] == key else wq.load(root)
        rd._json[qf] = (key, q)
        if not q["items"]:
            continue
        last = max(float(it.get("updated") or it.get("added") or 0) for it in q["items"].values())
        open_ = any(it["status"] not in wq.TERMINAL for it in q["items"].values())
        if not open_ and last < since:
            continue
        in_queue |= {it["run"] for it in q["items"].values() if it.get("run")}
        in_queue |= {rid for rid, r in shown.items() if str(r.get("label") or "").startswith("q:") and root_of(r) == root}
        pieces = _queue_pieces(rd, root, q, recs, verdicts, now)
        q_runs = [recs[it["run"]] for it in q["items"].values() if it.get("run") in recs]
        lead_sid = next((r.get("lead_session") for r in q_runs if r.get("lead_session")), None)
        lead = _lead_of_session(rd, lead_sid, q_runs[0].get("caller")) if lead_sid else \
            {"agent": (q_runs[0].get("caller") if q_runs else None), "model": "", "title": ""}
        roots_items = [q["items"][i] for i in q["order"] if not q["items"][i].get("parent")]
        hist = []
        for r in sorted(q_runs, key=lambda r: r.get("ts") or 0):
            it = next((x for x in q["items"].values() if x.get("run") == r["run_id"]), {})
            hist += hist_of_run(r, it.get("title") or "")
        tasks_by_root[root].append({
            "id": "queue", "kind": "queue", "title": lead.get("title") or (roots_items[0]["title"] if len(roots_items) == 1 else ""),
            "asked": min(float(it.get("added") or now) for it in q["items"].values()), "last": last,
            "lead": {"agent": lead.get("agent"), "model": lead.get("model")}, "helpers": [],
            "spent": wq.spent(q), "budget": q.get("budget_usd"), "pieces": pieces,
            "hist": sorted(hist, key=lambda h: h.get("ts") or 0)[-40:]})

    # the rest: one task per lead conversation (or per run when no lead is known)
    chains: dict[str, str] = {}
    for rid, r in sorted(shown.items(), key=lambda x: x[1].get("ts") or 0):
        if rid in in_queue:
            continue
        base = r.get("review_of") or (r.get("resumed_from") if not r.get("continued") else None)
        chains[rid] = chains.get(base, base) if base and base in shown else rid
    groups: dict[str, list[str]] = {}
    for rid, head in chains.items():
        r = shown[head]
        key = r.get("lead_session") or f"run-{head}"
        if proj and root_of(r) != proj:
            continue
        groups.setdefault(key, [])
        if head not in groups[key]:
            groups[key].append(head)
    for key, heads in groups.items():
        first = shown[heads[0]]
        root = root_of(first)
        lead = _lead_of_session(rd, first["lead_session"], first.get("caller")) if first.get("lead_session") else \
            {"agent": first.get("caller") if first.get("caller") in ("claude", "codex") else None, "model": "", "title": ""}
        pieces, hist, last = [], [], 0.0
        for head in heads:
            runs = sorted([rid for rid, h in chains.items() if h == head], key=lambda x: shown[x].get("ts") or 0)
            latest = shown[runs[-1]]
            title = (shown[head].get("label") if shown[head].get("label") and not str(shown[head]["label"]).startswith("q:")
                     else "") or _short(_brief_of(p.runs / head)) or head
            pc = piece_of_run(rd, latest, verdicts.get(latest["run_id"]), now, title)
            pc["id"] = _sid(head)
            pc["usd"] = round(sum(_usd(shown[x]) for x in runs), 6)
            pc["rounds"] = len(runs)
            pieces.append(pc)
            for x in runs:
                hist += hist_of_run(shown[x], title)
                last = max(last, float(shown[x].get("ts") or 0) + sum(a.get("seconds") or 0 for a in shown[x].get("attempts") or []))
        tasks_by_root.setdefault(root, []).append({
            "id": _sid(key), "kind": "lead" if first.get("lead_session") else "run",
            "title": lead.get("title") or (pieces[0]["title"] if len(pieces) == 1 else ""),
            "asked": min(float(shown[h].get("ts") or now) for h in heads), "last": last,
            "lead": {"agent": lead.get("agent"), "model": lead.get("model")}, "helpers": [],
            "spent": round(sum(x["usd"] for x in pieces), 6), "budget": None, "pieces": pieces,
            "hist": sorted(hist, key=lambda h: h.get("ts") or 0)[-40:]})

    current = leads(rd, mine)
    by_session = {x["session"]: x for x in current}
    projects = []
    for root, tasks in tasks_by_root.items():
        if not tasks:
            continue
        for t in tasks:
            if t["kind"] == "lead":
                cur = by_session.get(t["id"])
                if cur:
                    t["helpers"] = cur["helpers"]
                    t["lead"]["model"] = t["lead"]["model"] or cur["model"]
        tasks.sort(key=lambda t: -(t["last"] or t["asked"] or 0))
        projects.append({"id": _pid(root), "name": root.name or str(root), "path": str(root), "tasks": tasks[:30]})
    projects.sort(key=lambda pr: -max(t["last"] or t["asked"] or 0 for t in pr["tasks"]))

    providers = set((cfg.get("providers") or {}).keys())
    week = [r for r in recs.values() if float(r.get("ts") or 0) >= now - 7 * 86400]
    hard = [v for v in verdicts.values() if not v.get("soft")]
    agents = sorted({pc["worker"] for pr in projects for t in pr["tasks"] for pc in _walk(t["pieces"])
                     if pc.get("worker")} | {x["agent"] for x in current})
    from . import discuss, ways
    try:
        track = rd.every("track", 60, lambda: ways.track(p))      # H9: who is good at what (judged pieces)
    except Exception:  # noqa: BLE001 — the page still shows the rest
        track = {}
    talks =[discuss.view(d) for d in discuss.recent(p, since)
             if not proj or project_root(d.get("cwd")) == proj][:10]
    return {
        "v": 1, "generated": now, "lang": ui_lang(cfg), "poll_s": POLL_S, "beat_s": BEAT_S,
        "projects": projects, "quota": quota_view(rd, quota_wait), "leads": current, "agents": agents,
        "discussions": talks, "track": track, "track_min": ways.MIN_JUDGED,
        "week": {"usd": round(sum(_usd(r) for r in week), 4),
                 "cash_usd": round(sum(_usd(r) for r in week if r.get("to") in providers or r.get("provider")), 4),
                 "runs": len(week), "verdicts": len(hard), "verdicts_needed": VERDICTS_TO_KNOW},
    }


def _walk(pieces: list[dict]):
    for pc in pieces:
        yield pc
        yield from _walk(pc.get("children") or [])


def ui_lang(cfg: dict) -> str | None:
    v = (cfg.get("ui") or {}).get("lang")
    return v if v in ("zh", "en") else None


def run_detail(p: Paths, run_id: str) -> dict:
    """One run for the side panel's 'details': compact facts, no logs."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id or ""):
        raise ValueError("bad run id")
    from .delegate import compact
    from .ledger import load_run
    rec = load_run(p, run_id)
    out = compact(rec)
    out["cwd"], out["mode"], out["ts"] = rec.get("cwd"), rec.get("mode"), rec.get("ts")
    out["logs"] = str(p.runs / run_id)
    return out


# ------------------------------------------------------------------ the server
def _static(name: str) -> bytes:
    return (STATIC / name).read_bytes()


CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
TYPES = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
         "app.css": "text/css; charset=utf-8", "strings.json": "application/json; charset=utf-8"}


class UI:
    """The running server. `serve()` blocks until the page has been gone for IDLE_S (or stop())."""

    def __init__(self, p: Paths, project: Path | None = None, days: float = 7, port: int = 0,
                 idle_s: float = IDLE_S, first_beat_s: float = FIRST_BEAT_S):
        self.p, self.project, self.days = p, project, days
        self.token = secrets.token_urlsafe(24)
        self.idle_s, self.first_beat_s = idle_s, first_beat_s
        self.started = time.time()
        self.last_beat: float | None = None
        self.reader = Reader(p)
        self.lock = threading.Lock()
        self.why_stopped = ""
        ui = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ccx-ui"
            sys_version = ""

            def log_message(self, *a):            # quiet: the terminal shows only the URL and the exit
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", CSP)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _deny(self, why: str):
                self._send(403, json.dumps({"error": why}).encode())

            def _host_ok(self) -> bool:
                port = self.server.server_address[1]
                return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

            def _token_ok(self) -> bool:
                return hmac.compare_digest(self.headers.get("X-CCX-Token", ""), ui.token)

            def do_GET(self):
                if not self._host_ok():
                    return self._deny("host")
                path = urlsplit(self.path).path
                name = {"/": "index.html"}.get(path, path.lstrip("/"))
                if name in TYPES:
                    return self._send(200, _static(name), TYPES[name])
                if not path.startswith("/api/"):
                    return self._send(404, b'{"error":"not found"}')
                if not self._token_ok():
                    return self._deny("token")
                try:
                    if path == "/api/data":
                        with ui.lock:
                            data = collect(ui.p, ui.project, ui.days, ui.reader, quota_wait=False)
                        return self._send(200, json.dumps(data, ensure_ascii=False, default=list).encode("utf-8"))
                    if path.startswith("/api/run/"):
                        return self._send(200, json.dumps(run_detail(ui.p, path[len("/api/run/"):]),
                                                          ensure_ascii=False).encode("utf-8"))
                except (FileNotFoundError, ValueError) as e:
                    return self._send(404, json.dumps({"error": str(e)[:200]}).encode())
                except Exception as e:  # noqa: BLE001 — an odd record answers 500, the server keeps going
                    return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"[:200]}).encode())
                return self._send(404, b'{"error":"not found"}')

            def do_POST(self):
                if not self._host_ok():
                    return self._deny("host")
                if not self._token_ok():
                    return self._deny("token")
                if urlsplit(self.path).path == "/api/alive":
                    ui.last_beat = time.time()
                    return self._send(200, b'{"ok":true}')
                return self._send(404, b'{"error":"not found"}')

            do_HEAD = do_GET

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#k={self.token}"

    def idle_for(self, now: float | None = None) -> float:
        now = now or time.time()
        return now - (self.last_beat or self.started)

    def should_stop(self, now: float | None = None) -> bool:
        limit = self.idle_s if self.last_beat else max(self.idle_s, self.first_beat_s)
        return self.idle_for(now) > limit

    def _watch(self):
        while not self._done.wait(1.0):
            if self.should_stop():
                self.why_stopped = "page closed" if self.last_beat else "page never opened"
                self.httpd.shutdown()
                return

    def serve(self) -> str:
        self._done = threading.Event()
        threading.Thread(target=self._watch, daemon=True).start()
        try:
            self.httpd.serve_forever(poll_interval=0.5)
        finally:
            self._done.set()
            self.httpd.server_close()
        return self.why_stopped or "stopped"

    def stop(self):
        self.why_stopped = "stopped"
        self.httpd.shutdown()


def export(p: Paths, out: Path, project: Path | None = None, days: float = 7) -> Path:
    """A static snapshot: one HTML file with the page, its strings and the data; no server, no polling."""
    data = collect(p, project, days)
    page = _static("index.html").decode("utf-8")
    css = _static("app.css").decode("utf-8")
    js = _static("app.js").decode("utf-8")
    strings = _static("strings.json").decode("utf-8")

    def inline_json(obj_text: str) -> str:      # nothing in the data can close the script element
        return obj_text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = page.replace('<link rel="stylesheet" href="app.css">', f"<style>{css}</style>")
    page = page.replace('<script src="app.js"></script>',
                        f'<script type="application/json" id="ccx-strings">{inline_json(strings)}</script>'
                        f'<script type="application/json" id="ccx-snapshot">'
                        f'{inline_json(json.dumps(data, ensure_ascii=False, default=list))}</script>'
                        f"<script>{js}</script>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def waiting(p: Paths, days: float = 7) -> int:
    """How many recent runs wait for the person (for the session-start line), evaluation runs left out. Run records
    only: cheap."""
    now = time.time()
    rd = Reader(p)
    verdicts = rd.lines(p.ledger, _verdict_rows, {}) if p.ledger.exists() else {}
    n = 0
    for f in (p.runs.glob("*/run.json") if p.runs.exists() else []):
        try:
            if f.stat().st_mtime < now - days * 86400:
                continue
        except OSError:
            continue
        rec = rd.json_file(f)
        if not isinstance(rec, dict) or rec.get("ephemeral") or str(rec.get("label") or "").startswith(INTERNAL):
            continue
        if is_eval({**rec, "no_ab": (rec.get("route") or {}).get("no_ab")}):
            continue                                 # an evaluation's run (eval-*, --no-ab): nobody waits on it
        if rec.get("state") == "running" or not rec.get("run_id"):
            continue
        if _act(rec, verdicts.get(rec["run_id"]), now, None):
            n += 1
    return n


def open_browser(url: str) -> bool:
    import webbrowser
    try:
        return webbrowser.open(url)
    except Exception:  # noqa: BLE001
        return False
