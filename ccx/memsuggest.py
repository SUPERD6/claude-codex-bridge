"""Notes worth keeping, gathered when a piece of work ends or is handed over (proposal H5): what the person asked to
be done a certain way, decisions the lead stated, pitfalls it ran into. Code only, from the lead's own session file;
nothing is written to shared memory until the person says yes (`ccx mem accept`). Each suggestion carries its
source, so the note can be checked later (E7)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .config import Paths

# A preference is a standing rule in the person's words ("from now on ...", "以后不要 ..."), not an instruction for the
# task at hand: "改成"/"统一" name an edit as often as a rule, so they are not markers; "继续"/"第 N 步" are the task.
PREFERENCE = re.compile(r"\b(always|never|from now on|prefer|please (?:use|keep|write)|don'?t|do not|instead of|"
                        r"make sure|by default)\b|以后|不要|别再|总是|一律|默认|记住|优先|不用|每次|永远|必须", re.I)
TASK = re.compile(r"\b(continue|carry on|go ahead|next step|steps? \d+)\b|继续|接着|下一步|这一步|"
                  r"第\s*[0-9一二三四五六七八九十]+(?:\s*[-–~～到]\s*[0-9一二三四五六七八九十]+)?\s*步|"
                  r"[A-Za-z]:\\|(?:^|\s)/(?:Users|home)/|"     # an absolute path: this machine, this task
                  r"`[^`\s]*/[^`\s]*`|"                       # a file to change (`ccx/review.py`): a work item
                  r"写进|写到|放进|放到", re.I)                  # "put this into F": where this task's text goes
# "E8 真跑发现…", "J6：…", "H5–H7 …", "PR #21 …": a progress line about one proposal or PR, not a lasting pitfall
PROGRESS = re.compile(r"^\s*(?:\*\*)?(?:[A-Z]{1,2}\d{1,2}[a-z]?(?:\s*[-–/、,]\s*[A-Z]{0,2}\d{1,2})*|(?:PR\s*)?#\d+)"
                      r"(?:\*\*)?(?=[\s:：,，)）]|$)")
DECISION = re.compile(r"\b(decided|decision|we(?:'ll| will) use|chose|going with|settled on)\b|决定|改为|采用|定下|结论[:：]",
                      re.I)
# bare "原来" mostly means "the original ..."; only "原来是/原来其实/原来没 ..." reports something that turned out
PITFALL = re.compile(r"\b(turned out|gotcha|pitfall|found that|careful|the cause was|root cause)\b|注意|坑|"
                     r"原来(?:是|其实|并|没|不|只|一直)|发现|根因", re.I)
# The lead's report to the person rather than a lasting fact: "已推送 / tests pass / 提交号 abc1234", a heading, or a
# fragment too short to stand alone ("还没做 / 需要注意"). A "pitfall" said to "你" is about this conversation.
REPORT = re.compile(r"已推送|已提交|已合并|都过了|测试通过|\b(?:pushed|merged|tests? pass(?:ed)?)\b|"
                    r"`[0-9a-f]{7,40}`|^#", re.I)
MIN_LEAD_TEXT = 14
MAX_TEXT = 220


def _file(p: Paths) -> Path:
    return p.state / "mem-suggestions.json"


def load(p: Paths) -> list[dict]:
    try:
        return json.loads(_file(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(p: Paths, items: list[dict]) -> None:
    _file(p).parent.mkdir(parents=True, exist_ok=True)
    _file(p).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|(?<=[。！？；])\s*|\n+", text or "")   # "a.txt" is not a sentence end
    out = [s.strip(" -*•\t") for s in parts]
    # a note is one short statement: not a question, not a lead-in to a list, not a whole paragraph
    return [s for s in out if 8 <= len(s) <= 160 and not s.endswith((":", "：", "?", "？"))]


def _clip(s: str) -> str:
    from .transcript import redact
    s = redact(" ".join(s.replace("**", "").split()))
    return s if len(s) <= MAX_TEXT else s[: MAX_TEXT - 1] + "…"


def gather(d: dict, path: Path, limit: int = 8) -> list[dict]:
    """Candidates from a session read by transcript.read_claude / read_codex: the person's words first."""
    src = f"{d.get('agent')} session {d.get('session') or path.stem} ({path.name})"
    out: list[dict] = []
    for u in d.get("users") or []:
        for s in _sentences(u):
            if PREFERENCE.search(s) and not TASK.search(s) and not PROGRESS.match(s):
                out.append({"kind": "preference", "text": _clip(s), "by": "user", "source": src})
    for t in d.get("texts") or []:
        for s in _sentences(t):
            if len(s.replace("*", "").strip()) < MIN_LEAD_TEXT or REPORT.search(s):
                continue
            if DECISION.search(s):
                out.append({"kind": "decision", "text": _clip(s), "by": d.get("agent"), "source": src})
            elif PITFALL.search(s) and not PROGRESS.match(s) and "你" not in s:
                out.append({"kind": "pitfall", "text": _clip(s), "by": d.get("agent"), "source": src})
    seen, uniq = set(), []
    for c in out:
        k = _norm(c["text"])
        if k and k not in seen:
            seen.add(k)
            uniq.append(c)
    order = {"preference": 0, "decision": 1, "pitfall": 2}
    uniq.sort(key=lambda c: order[c["kind"]])
    return uniq[:limit]


def add(p: Paths, cands: list[dict]) -> list[dict]:
    """Keep the new ones (not already a note or a suggestion); returns what was added."""
    from . import memory
    items = load(p)
    known = {_norm(i["text"]) for i in items} | {_norm(e["text"]) for e in memory.entries(p)}
    nxt = max((i["id"] for i in items), default=0) + 1
    added = []
    for c in cands:
        if _norm(c["text"]) in known:
            continue
        known.add(_norm(c["text"]))
        item = {"id": nxt, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "status": "pending", **c}
        items.append(item)
        added.append(item)
        nxt += 1
    _save(p, items)
    return added


def pending(p: Paths) -> list[dict]:
    return [i for i in load(p) if i["status"] == "pending"]


def decide(p: Paths, sid: int, accept: bool, text: str | None = None, topic: str | None = None) -> dict:
    """The person's answer. Accepting writes the note (with its source) to shared memory."""
    from . import memory
    items = load(p)
    it = next((i for i in items if i["id"] == sid), None)
    if it is None:
        raise ValueError(f"no suggestion #{sid}")
    if it["status"] != "pending":
        raise ValueError(f"suggestion #{sid} is already {it['status']}")
    out = {"id": sid}
    if accept:
        note = memory.add(p, text or it["text"], "user", topic or it["kind"], source=it["source"])
        it["status"], it["note"] = "accepted", note.get("seq")
        out["note"] = note
    else:
        it["status"] = "rejected"
    out["status"] = it["status"]
    _save(p, items)
    return out


def from_session(p: Paths, agent: str, path: Path, limit: int = 8) -> list[dict]:
    from .transcript import read_claude, read_codex
    d = (read_claude if agent == "claude" else read_codex)(path)
    return add(p, gather(d, path, limit))
