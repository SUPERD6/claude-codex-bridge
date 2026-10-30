"""`ccx ui` page "Measured & where tokens go" (B1). Display only: everything here is read from what ccx and the two
tools already write; nothing is written, no model is called.

1. Measured results: the published numbers, from one small data file shipped in the package (ccx/data/measured.json;
   tests check that every number in it appears in docs/measured.md, so they cannot drift), then the person's own
   numbers from their ledger (runs, ok rate, API-equivalent $ per ok run, by mode and by agent): their runs, not a
   controlled comparison.
2. Where tokens go: one ledger across Claude and Codex. Runs are grouped by task (else label, else run); each run
   shows its tokens (fresh / cached / cache_write / output) and API-equivalent $, then its own child sessions:
   Codex children from run.json `codex_children` (child id -> running input / cached / output, input includes
   cached; a resumed or continued run carries the totals of the run it went on from, so that run's own record is
   taken off and only the growth is shown), Claude children from the sub-run's <session>/subagents/*.jsonl
   (usage.session_files / _helper_parent / _claude_file), each session once per run and only the helper turns from
   the run's start to the next run that took up the same session. A run's own total
   already includes its children (Codex: delegate adds their growth; Claude: modelUsage covers the Agent tool), so
   the share is children / run total.
3. Lead conversations: the lead sessions that delegated (ledger `lead_session`), newest first; one is parsed only
   when asked (/api/leadcost), with the same functions as `ccx lead --breakdown` and `ccx lead --cache`
   (leadcost.breakdown / leadcost.cache_breaks), cached by the file's mtime and size.

Everything returned is capped (rows, children, text lengths, bytes); labels and session text are untrusted, the page
escapes them. Files read: <hub>/ccx/ledger.jsonl and runs/<id>/run.json, prompt.md; the tools' own session folders
(CLAUDE_CONFIG_DIR/projects, CODEX_HOME/sessions) for one session id that the ledger names.
"""
from __future__ import annotations

import bisect
import json
import re
import statistics
import time
from pathlib import Path

from .config import Paths

DATA = Path(__file__).resolve().parent / "data" / "measured.json"
TASKS_MAX = 40                 # newest task groups shown; the rest is counted and said
RUNS_PER_TASK_MAX = 25         # newest runs of one task
KIDS_MAX = 20                  # child sessions listed under one run (the sums cover all of them)
LEADS_MAX = 10                 # lead conversations listed
LABEL_MAX = 160                # characters of a title / label / id as sent to the page
PARTS_MAX = 40                 # --breakdown parts sent
BREAKS_MAX = 40                # --cache breaks sent (the newest)
ADVICE_MAX = 20
TEXT_MAX = 400                 # one advice line / cause
BODY_MAX = 1_500_000           # bytes of one /api/tokens answer; above, fewer tasks are sent
PERIODS = ("today", "7d", "all")
_SID = re.compile(r"[A-Za-z0-9_-]{1,80}")
LEAD_AGENTS = {"claude": "claude", "codex": "codex", "anthropic": "claude", "openai": "codex"}


def clip(s, n: int = LABEL_MAX) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def measured() -> dict:
    """The published numbers (docs/measured.md), as shipped in the package."""
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def since_of(period: str, now: float) -> float:
    if period == "today":
        t = time.localtime(now)
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    if period == "7d":
        return now - 7 * 86400
    return 0.0


def tokens_of(row: dict) -> dict:
    """fresh / cached / cache_write / output of a ledger row (usage4 when it has it, else its sum_usage form)."""
    u4 = row.get("usage4") or {}
    if u4:
        t = {"fresh": int(u4.get("input_tokens", 0) or 0), "cached": int(u4.get("cached_input_tokens", 0) or 0),
             "cache_write": int(u4.get("cache_write_tokens", 0) or 0), "output": int(u4.get("output_tokens", 0) or 0)}
    else:
        u = row.get("usage") or {}
        w = int(u.get("cache_write", 0) or 0)
        t = {"fresh": max(0, int(u.get("input", 0) or 0) - w), "cached": int(u.get("cached", 0) or 0),
             "cache_write": w, "output": int(u.get("output", 0) or 0)}
    t["total"] = t["fresh"] + t["cached"] + t["cache_write"] + t["output"]
    return t


def _add(a: dict, b: dict) -> dict:
    for k in ("fresh", "cached", "cache_write", "output", "total"):
        a[k] = a.get(k, 0) + int(b.get(k, 0) or 0)
    return a


def _zero() -> dict:
    return {"fresh": 0, "cached": 0, "cache_write": 0, "output": 0, "total": 0}


def _model(row: dict) -> str:
    rungs = row.get("rungs") or []
    if rungs and isinstance(rungs[-1], str) and rungs[-1].count(":") >= 1:
        return rungs[-1].split(":")[1]
    return ""


def _request_stats(rows: list[tuple]) -> dict:
    """Over the runs that recorded their requests: how many there are, the mean requests a run, the median over
    runs of the input per request, and of the first request's input. {} when none did, so the page shows nothing
    rather than zeros."""
    if not rows:
        return {}
    pre = [int(p) for _, p, _ in rows if p]
    first = [int(x) for _, _, x in rows if x]
    return {"measured_runs": len(rows), "requests_per_run": round(sum(n for n, _, _ in rows) / len(rows), 1),
            "prefix_median": int(statistics.median(pre)) if pre else None,
            "first_input_median": int(statistics.median(first)) if first else None}


def _is_review(row: dict) -> str | None:
    label = str(row.get("label") or "")
    return label[len("review:"):] if label.startswith("review:") else None


# ------------------------------------------------------------------ child sessions
def codex_kids(rec: dict, before: dict | None = None) -> list[dict]:
    """A run's Codex children from its record: {child: {input, cached, output}} running totals, input including
    cached. A resumed or continued run's record starts from the totals of the run it went on from (delegate.py
    copies them), so `before` is that run's `codex_children` and only the growth is this run's."""
    out = []
    before = before or {}
    for child, tot in (rec.get("codex_children") or {}).items():
        if not isinstance(tot, dict):
            continue
        b = before.get(child) if isinstance(before.get(child), dict) else {}
        d = {k: max(0, int(tot.get(k, 0) or 0) - int(b.get(k, 0) or 0)) for k in ("input", "cached", "output")}
        t = {"fresh": max(0, d["input"] - d["cached"]), "cached": d["cached"], "cache_write": 0, "output": d["output"]}
        t["total"] = t["fresh"] + t["cached"] + t["output"]
        if t["total"]:
            out.append({"id": str(child), "vendor": "codex", "tokens": t,
                        "usage": {"input_tokens": t["fresh"], "cached_input_tokens": t["cached"],
                                  "output_tokens": t["output"]}})
    return out


def claude_kids(session: str, since: float = 0.0, until: float | None = None,
                home: Path | None = None) -> list[dict]:
    """A Claude sub-run's own sub-agents (Agent tool), one entry per helper file under <session>/subagents/, read
    with the same helpers as the lead-side accounting (usage.session_files, _helper_parent, _claude_file). Only the
    messages in [since, until): a later run that resumes the same session (ccx resume, a review fix round, ccx run
    auto-continue) keeps the session id, so each run takes the helper turns of its own time window."""
    from .usage import _claude_file, _helper_parent, session_files
    out = []
    for f in session_files(session, home):
        if _helper_parent(f) != session:
            continue                                   # the conversation's own file: that is the run itself
        msgs: dict[str, dict] = {}
        _claude_file(f, since, set(), msgs)
        if until is not None:
            msgs = {k: m for k, m in msgs.items() if m["ts"] < until}
        if not msgs:
            continue
        u = {"input_tokens": 0, "cache_write_tokens": 0, "cache_write_1h_tokens": 0, "cached_input_tokens": 0,
             "output_tokens": 0}
        model = ""
        for m in msgs.values():
            for k in u:
                u[k] += int(m["usage"].get(k, 0) or 0)
            model = m.get("model") or model
        t = {"fresh": u["input_tokens"], "cached": u["cached_input_tokens"], "cache_write": u["cache_write_tokens"],
             "output": u["output_tokens"]}
        t["total"] = sum(t.values())
        out.append({"id": f.stem, "vendor": "claude", "model": model, "tokens": t, "usage": u})
    return out


# ------------------------------------------------------------------ the page's data
class Flow:
    """Caches what is slow to read again: a finished run's children (by its record's mtime/size) and a parsed lead
    conversation (by the session file's mtime/size)."""

    def __init__(self, p: Paths):
        self.p = p
        self._kids: dict[str, tuple] = {}
        self._lead: dict[tuple, tuple] = {}

    # ---- /api/tokens
    def tokens(self, rows: list[dict], period: str = "7d", project: str | None = None, tests: bool = False,
               now: float | None = None) -> dict:
        from . import ledger
        from .ui import _brief_of, _pid, _short, project_root, is_scratch, scratch_roots
        now = now or time.time()
        period = period if period in PERIODS else "7d"
        since = since_of(period, now)
        scratch = scratch_roots(self.p)
        roots: dict[str, Path | None] = {}

        def root(cwd):
            if cwd not in roots:
                roots[cwd] = project_root(cwd)
            return roots[cwd]

        runs = [r for r in rows if not r.get("type") and r.get("run_id") and not r.get("ephemeral")
                and (r.get("ts") or 0) >= since]
        if not tests:
            runs = [r for r in runs if not (ledger.is_eval(r) or is_scratch(r.get("cwd"), scratch))]
        projects: dict[str, str] = {}
        for r in runs:
            rt = root(r.get("cwd"))
            if rt is not None:
                projects.setdefault(_pid(rt), rt.name)
        if project:
            runs = [r for r in runs if root(r.get("cwd")) is not None and _pid(root(r.get("cwd"))) == project]

        # 1b: the person's own numbers
        mine = {"runs": 0, "ok": 0, "usd": 0.0, "by_mode": {}, "by_agent": {}}
        for r in runs:
            if _is_review(r) is not None:
                continue
            for bucket in (mine, mine["by_mode"].setdefault(str(r.get("actual_mode") or r.get("mode") or "?"),
                                                             {"runs": 0, "ok": 0, "usd": 0.0}),
                           mine["by_agent"].setdefault(str(r.get("to") or "?"), {"runs": 0, "ok": 0, "usd": 0.0})):
                bucket["runs"] += 1
                bucket["ok"] += bool(r.get("ok"))
                bucket["usd"] += float(r.get("ae_usd") or 0.0)
        for b in (mine, *mine["by_mode"].values(), *mine["by_agent"].values()):
            b["ok_rate"] = round(b["ok"] / b["runs"], 3) if b["runs"] else None
            b["usd_per_ok"] = round(b["usd"] / b["ok"], 4) if b["ok"] else None
            b["usd"] = round(b["usd"], 4)

        # 2: totals across vendors, every run in the filter
        totals = {"runs": len(runs), "tokens": _zero(), "usd": 0.0, "by_agent": {}}
        reqs: dict[str, list[tuple]] = {}        # agent -> (requests, input a request, first input) of the runs that have them
        for r in runs:
            t = tokens_of(r)
            _add(totals["tokens"], t)
            totals["usd"] += float(r.get("ae_usd") or 0.0)
            a = totals["by_agent"].setdefault(str(r.get("to") or "?"), {"runs": 0, "tokens": _zero(), "usd": 0.0})
            a["runs"] += 1
            _add(a["tokens"], t)
            if r.get("requests"):
                reqs.setdefault(str(r.get("to") or "?"), []).append((int(r["requests"]), r.get("prefix_tokens"),
                                                                     r.get("first_input")))
            by = r.get("ae_by_agent") or {}
            if by:
                for ag, v in by.items():
                    totals["by_agent"].setdefault(str(ag), {"runs": 0, "tokens": _zero(), "usd": 0.0})["usd"] += \
                        float(v or 0.0)
            else:
                a["usd"] += float(r.get("ae_usd") or 0.0)
        totals["usd"] = round(totals["usd"], 4)
        for name, a in totals["by_agent"].items():
            a["usd"] = round(a["usd"], 4)
            a.update(_request_stats(reqs.get(name) or []))
        totals.update(_request_stats([x for v in reqs.values() for x in v]))
        totals["by_agent"] = dict(sorted(totals["by_agent"].items(),          # the biggest first
                                         key=lambda x: (-x[1]["tokens"]["total"], -x[1]["usd"])))

        # when each Claude session was taken up by a run (every ledger row, not only the filtered ones), so a run
        # that resumes a session gets only the helper turns after it, and the earlier run only those before it
        starts: dict[str, list[float]] = {}
        for r in rows:
            if r.get("type") or not r.get("run_id"):
                continue
            for sid in set(r.get("sessions") or []) | ({r["session_id"]} if r.get("session_id") else set()):
                starts.setdefault(str(sid), []).append(float(r.get("ts") or 0))
        for v in starts.values():
            v.sort()

        # 2: the tree, grouped by task, else label, else run; a review run goes with the run it reviewed
        key_of: dict[str, str] = {}
        groups: dict[str, list[dict]] = {}
        for r in sorted(runs, key=lambda x: x.get("ts") or 0):
            target = _is_review(r)
            came_from = self.resumed_from(r) if not r.get("task") and not r.get("label") else None
            if target is not None and target in key_of:
                k = key_of[target]
            elif r.get("task"):
                k = "task:" + str(r["task"])
            elif r.get("label") and target is None:
                k = "label:" + str(r["label"])
            elif came_from and came_from in key_of:  # a resume without a task or label sits with its chain
                k = key_of[came_from]
            else:
                k = "run:" + str(target or r["run_id"])
            key_of[r["run_id"]] = k
            groups.setdefault(k, []).append(r)
        order = sorted(groups, key=lambda k: -max(x.get("ts") or 0 for x in groups[k]))
        tasks = []
        kid_tot = _zero()
        for k in order[:TASKS_MAX]:
            rs = groups[k]
            shown = rs[-RUNS_PER_TASK_MAX:]
            items = []
            gt, gusd = _zero(), 0.0
            for r in rs:
                _add(gt, tokens_of(r))
                gusd += float(r.get("ae_usd") or 0.0)
            for r in shown:                       # each run's own children, from its own chain (not the filter)
                items.append(self.run_item(r, self.kids(r, starts)))
            for it in items:
                _add(kid_tot, it["children_tokens"])
            kind, _, name = k.partition(":")
            title = name
            if kind in ("run", "task"):              # what was asked, from the first run's brief (prompt.md)
                first = next((x for x in rs if _is_review(x) is None), rs[0])
                rid = str(first.get("run_id") or "")
                if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", rid):
                    title = _short(_brief_of(self.p.runs / rid)) or name
            tasks.append({"key": clip(k, 200), "kind": kind, "name": clip(name), "title": clip(title), "runs": list(reversed(items)),
                          "runs_total": len(rs), "runs_cut": len(rs) - len(shown), "tokens": gt,
                          "usd": round(gusd, 4), "last": max(x.get("ts") or 0 for x in rs)})
        if project and project not in projects:      # filtered on a project with no runs in this period
            projects[project] = project
        out = {"period": period, "project": project or None,
               "projects": [{"id": i, "name": clip(n, 80)} for i, n in sorted(projects.items(), key=lambda x: x[1])],
               "measured": measured(), "mine": mine, "totals": totals, "tasks": tasks,
               "children_shown": kid_tot,
               "cut": {"tasks": max(0, len(order) - TASKS_MAX),
                       "runs": sum(len(groups[k]) for k in order[TASKS_MAX:]),
                       "tokens": sum(tokens_of(r)["total"] for k in order[TASKS_MAX:] for r in groups[k]),
                       "usd": round(sum(float(r.get("ae_usd") or 0.0) for k in order[TASKS_MAX:]
                                        for r in groups[k]), 4)},
               "leads": self.leads(runs), "caps": {"tasks": TASKS_MAX, "runs": RUNS_PER_TASK_MAX, "kids": KIDS_MAX}}
        while len(json.dumps(out, ensure_ascii=False)) > BODY_MAX and out["tasks"]:
            dropped = out["tasks"].pop()
            out["cut"]["tasks"] += 1
            out["cut"]["runs"] += dropped["runs_total"]
            out["cut"]["tokens"] += dropped["tokens"]["total"]
            out["cut"]["usd"] = round(out["cut"]["usd"] + dropped["usd"], 4)
        return out

    def record(self, run_id) -> dict:
        rid = str(run_id or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", rid):
            return {}
        try:
            rec = json.loads((self.p.runs / rid / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return rec if isinstance(rec, dict) else {}

    def resumed_from(self, r: dict) -> str | None:
        """The run this one went on from (run.json `resumed_from`); read only for rows that say they follow one."""
        if not (r.get("resume_chain") or r.get("continue_depth")):
            return None
        prev = self.record(r.get("run_id")).get("resumed_from")
        return str(prev) if prev else None

    def kids(self, r: dict, starts: dict[str, list[float]]) -> list[dict]:
        rid = str(r.get("run_id"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", rid):
            return []
        f = self.p.runs / rid / "run.json"
        try:
            st = f.stat()
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(rec, dict):
            return []
        # Codex: the record carries the totals of the run it went on from; take those off (that run's own record,
        # whether or not it is in this answer's filter or group)
        before = self.record(rec["resumed_from"]).get("codex_children") if rec.get("resumed_from") else None
        out = codex_kids(rec, before if isinstance(before, dict) else None)
        # Claude: each session once, only the helper turns from this run's start to the next run on that session
        since = float(rec.get("ts") or r.get("ts") or 0.0)
        sids = sorted({str(a.get("session_id")) for a in rec.get("attempts") or []
                       if a.get("agent") == "claude" and a.get("session_id") and _SID.fullmatch(str(a["session_id"]))})
        windows = []
        for sid in sids:
            later = starts.get(sid) or []
            j = bisect.bisect_right(later, since)
            windows.append((sid, later[j] if j < len(later) else None))
        key = (st.st_mtime_ns, st.st_size, since, tuple(windows))
        hit = self._kids.get(rid)
        if hit and hit[0] == key:
            claude = hit[1]
        else:
            claude = []
            for sid, until in windows:
                claude += claude_kids(sid, since, until)
            if rec.get("state") != "running":       # still running: its helpers may write more
                if len(self._kids) > 2000:
                    self._kids.clear()
                self._kids[rid] = (key, claude)
        return out + claude

    def run_item(self, r: dict, kids: list[dict]) -> dict:
        from . import learn
        t = tokens_of(r)
        model = _model(r)
        ct = _zero()
        shown = []
        for c in kids:
            _add(ct, c["tokens"])
        for c in sorted(kids, key=lambda c: -c["tokens"]["total"])[:KIDS_MAX]:
            usd = learn.price_usd(self.p, c["vendor"], c.get("model") or model, c["usage"])
            shown.append({"id": clip(c["id"], 80), "vendor": c["vendor"], "tokens": c["tokens"],
                          "usd": None if usd is None else round(usd, 5)})
        return {"run_id": clip(r.get("run_id"), 80), "agent": clip(r.get("to"), 40), "model": clip(model, 60),
                "status": clip(r.get("status"), 40), "ok": bool(r.get("ok")), "ts": r.get("ts"),
                "mode": clip(r.get("actual_mode") or r.get("mode"), 20), "review": _is_review(r) is not None,
                "label": clip(r.get("label")), "tokens": t,
                # B3 ruler (ccx/reqstats.py): requests this run made and the median input of one; null for a run
                # that recorded none (older runs, gemini / dsh, a session file that was gone)
                "requests": int(r["requests"]) if r.get("requests") else None,
                "prefix_tokens": int(r["prefix_tokens"]) if r.get("prefix_tokens") else None,
                "first_input": int(r["first_input"]) if r.get("first_input") else None,
                "usd": None if r.get("ae_usd") is None else round(float(r["ae_usd"]), 5),
                "children": shown, "children_more": max(0, len(kids) - KIDS_MAX), "children_tokens": ct,
                # not capped: above 1 the counts disagree, and the page says so
                "children_share": round(ct["total"] / t["total"], 3) if t["total"] and kids else None}

    @staticmethod
    def leads(runs: list[dict]) -> list[dict]:
        """The lead conversations that delegated, newest first (no parsing here: that is /api/leadcost)."""
        by: dict[tuple, dict] = {}
        for r in runs:
            sid = r.get("lead_session")
            agent = LEAD_AGENTS.get(str(r.get("caller") or "")) or LEAD_AGENTS.get(str(r.get("caller_vendor") or ""))
            if not sid or not agent or not _SID.fullmatch(str(sid)):
                continue
            g = by.setdefault((agent, str(sid)), {"agent": agent, "session": str(sid), "runs": 0, "usd": 0.0,
                                                   "last": 0})
            g["runs"] += 1
            g["usd"] = round(g["usd"] + float(r.get("ae_usd") or 0.0), 4)
            g["last"] = max(g["last"], r.get("ts") or 0)
        return sorted(by.values(), key=lambda g: -g["last"])[:LEADS_MAX]

    # ---- /api/leadcost
    def lead_file(self, agent: str, session: str) -> Path | None:
        from .transcript import claude_session_file, find_session
        if agent == "claude":
            return claude_session_file(session)
        return find_session("codex", Path("."), set(), session)

    def leadcost(self, rows: list[dict], agent: str, session: str) -> dict:
        """One lead conversation: what each turn re-reads, part by part, the cache breaks and their likely cause, and
        the advice: exactly what `ccx lead --breakdown` / `--cache` compute. Only a session the ledger names."""
        from . import leadcost
        if agent not in ("claude", "codex") or not _SID.fullmatch(session or ""):
            raise ValueError("bad lead session")
        if not any(str(r.get("lead_session") or "") == session for r in rows if not r.get("type")):
            raise FileNotFoundError("not a lead session in the ledger")
        f = self.lead_file(agent, session)
        if not f:
            return {"agent": agent, "session": session, "found": False}
        try:
            st = f.stat()
        except OSError:
            return {"agent": agent, "session": session, "found": False}
        key = (str(f), st.st_mtime_ns, st.st_size)
        hit = self._lead.get((agent, session))
        if hit and hit[0] == key:
            return hit[1]
        b = leadcost.breakdown(self.p, agent, f)
        c = leadcost.cache_breaks(self.p, agent, f)
        parts = [{"part": clip(x.get("part"), 200), "tokens": x.get("tokens"), "share": x.get("share"),
                  "usd_per_100_turns": x.get("usd_per_100_turns")} for x in (b.get("parts") or [])[:PARTS_MAX]]
        breaks = [{"ts": clip(x.get("ts"), 40), "rewritten_tokens": x.get("rewritten_tokens"),
                   "read_tokens": x.get("read_tokens"), "model": clip(x.get("model"), 60),
                   "why": [clip(w, TEXT_MAX) for w in (x.get("why") or [])[:8]], "extra_usd": x.get("extra_usd")}
                  for x in (c.get("breaks") or [])[-BREAKS_MAX:]]
        out = {"agent": agent, "session": session, "found": True, "file": clip(f.name, 120),
               "model": clip(b.get("model"), 60), "first_turn_tokens": b.get("first_turn_tokens"),
               "parts": parts, "parts_cut": max(0, len(b.get("parts") or []) - PARTS_MAX),
               "advice": [clip(a, TEXT_MAX) for a in (b.get("advice") or [])[:ADVICE_MAX]],
               "breaks": breaks, "breaks_total": len(c.get("breaks") or []), "extra_usd": c.get("extra_usd"),
               "causes": {clip(k, TEXT_MAX): v for k, v in list((c.get("causes") or {}).items())[:20]},
               "note": clip(c.get("note"), TEXT_MAX)}
        if len(self._lead) > 50:
            self._lead.clear()
        self._lead[(agent, session)] = (key, out)
        return out
