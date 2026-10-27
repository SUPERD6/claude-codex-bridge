"""Shared, incremental memory for Claude Code and Codex.

    snapshot  memory/MEMORY.md      "1"  short, stable, loaded by both at startup
                                         (stable text = prompt-cache hits = cheap)
    journal   memory/journal.jsonl  "+2" append-only; either side adds lines
    cursors   ccx/cursors.json           how far each side has already seen

At session start a hook runs `ccx mem delta --as <me>`: it prints only entries
newer than <me>'s cursor that the *other* side wrote, then moves the cursor.
Nothing new -> prints nothing -> costs zero tokens.

`ccx mem compact` folds the journal into the snapshot (rarely), so the
snapshot stays the single source of "1" and the journal stays short.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from .config import Paths

NOTES_BEGIN = re.compile(r"<!--\s*ccx:notes begin seq=(\d+)\s*-->")
NOTES_END = "<!-- ccx:notes end -->"
NOTES_TITLE = "## 共享记录 / Shared notes（ccx mem compact 合并，勿手改 / merged by ccx, do not edit）"
SNAPSHOT_TEMPLATE = """# 共享记忆（Claude Code 与 Codex 共用） / Shared memory

这是两边开局都会读的“快照”。保持简短（建议 < 3 KB）：只放长期有效、两边都用得上的事实与偏好。
新内容不要直接改这里：用 `ccx mem add "..."` 追加到日志，攒够了再 `ccx mem compact` 合并进来。

## 用户与偏好 / User & preferences
- 
"""
SNAP_TAG = NOTES_BEGIN   # backwards-compatible name


def _journal(p: Paths) -> Path:
    return p.memory / "journal.jsonl"


def _cursors(p: Paths) -> Path:
    return p.state / "cursors.json"


@contextmanager
def _lock(p: Paths, timeout: float = 10.0):
    p.state.mkdir(parents=True, exist_ok=True)
    lock = p.state / "memory.lock"
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - t0 > timeout:
                # stale lock (crashed writer) -> take it over
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


def ensure(p: Paths) -> None:
    p.memory.mkdir(parents=True, exist_ok=True)
    if not p.memory_index.exists() and not p.snapshot_external:
        p.memory_index.parent.mkdir(parents=True, exist_ok=True)
        p.memory_index.write_text(SNAPSHOT_TEMPLATE, encoding="utf-8")
    _journal(p).touch(exist_ok=True)


def snapshot_seq(p: Paths) -> int:
    if not p.memory_index.exists():
        return 0
    m = NOTES_BEGIN.search(p.memory_index.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else 0


def entries(p: Paths) -> list[dict]:
    f = _journal(p)
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _last_seq(p: Paths) -> int:
    es = entries(p)
    return max([snapshot_seq(p)] + [e["seq"] for e in es])


def load_cursors(p: Paths) -> dict:
    f = _cursors(p)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_cursors(p: Paths, c: dict) -> None:
    _cursors(p).parent.mkdir(parents=True, exist_ok=True)
    _cursors(p).write_text(json.dumps(c, indent=2), encoding="utf-8")


STALE_DAYS = 30
DELTA_CHARS = 2400          # ~600 tokens: what a session start may spend on new memory lines


def _meta(p: Paths) -> Path:
    return p.memory / "journal-meta.jsonl"


def verify(p: Paths, seq: int, by: str = "user") -> dict:
    """Mark a note as checked again today (append-only, next to the journal)."""
    if not any(e["seq"] == seq for e in entries(p)):
        raise ValueError(f"no memory note #{seq} in the journal")
    ev = {"ev": "verify", "seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": by}
    with _lock(p):
        with open(_meta(p), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
    return ev


def verified_at(p: Paths) -> dict[int, str]:
    """seq -> when it was last written or checked."""
    out = {e["seq"]: e.get("ts") for e in entries(p)}
    try:
        for line in _meta(p).read_text(encoding="utf-8").splitlines():
            ev = json.loads(line)
            if ev.get("ev") == "verify":
                out[ev["seq"]] = max(out.get(ev["seq"]) or "", ev["ts"])
    except (OSError, ValueError):
        pass
    return out


def live_entries(p: Paths) -> list[dict]:
    """Journal notes not replaced by a newer one (`--supersedes N`)."""
    es = entries(p)
    gone = {e.get("supersedes") for e in es if e.get("supersedes")}
    return [e for e in es if e["seq"] not in gone]


def stale(p: Paths, days: int = STALE_DAYS) -> list[dict]:
    """Notes nobody has written or checked for `days`: shown as 'to check' at session start."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    va = verified_at(p)
    return [{**e, "checked": va.get(e["seq"])} for e in live_entries(p) if (va.get(e["seq"]) or "") < cutoff]


def search(p: Paths, words: list[str], all_words: bool = False, limit: int | None = None) -> list[dict]:
    """Notes (journal and snapshot lines), best first by BM25 (L1): a rare word counts more than a common one, and
    a note needn't contain every word. `all_words`: only notes containing every word (the old filter), still ranked."""
    ws = [w.lower() for w in words if w.strip()]
    docs = [({"seq": e["seq"], "by": e.get("by"), "topic": e.get("topic"), "kind": kind_of(e), "text": e["text"]},
             f"{e.get('topic') or ''} {e['text']}") for e in live_entries(p)]
    if p.memory_index.exists():
        for i, line in enumerate(p.memory_index.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                docs.append(({"seq": None, "where": f"{p.memory_index.name}:{i}", "text": line.strip()}, line))
    scores = bm25(query_terms(" ".join(ws)), [d for _h, d in docs])
    hits = []
    for n, ((h, d), s) in enumerate(zip(docs, scores)):
        if ws and not s:
            continue
        if all_words and not all(w in d.lower() for w in ws):
            continue
        hits.append((-s, h["seq"] is None, -(h["seq"] or 0), n, {**h, "score": round(s, 3)}))
    return [h for *_k, h in sorted(hits, key=lambda x: x[:4])][:limit]


KINDS = {"preference": "偏好", "constraint": "约束", "fact": "事实", "pitfall": "坑", "event": "事件",
         "other": "其他"}
START_KINDS = ("preference", "constraint")     # with [memory] by_kind: the only kinds a session start carries
BRIEF_SKIP = ("event",)                         # ... and the one a brief never carries (searchable only)
_KIND_ALIASES = {"decision": "constraint", "rule": "constraint", "rules": "constraint", "gotcha": "pitfall",
                 "pitfalls": "pitfall", "preferences": "preference", "facts": "fact", "events": "event"}
_KIND_WORDS = [     # first match wins: an old note without a kind is sorted by its words when read (L2)
    ("pitfall", r"坑|小心|注意|别忘|踩|陷阱|会失败|失败时|会被|报错|不生效|gotcha|pitfall|careful|beware|watch out|breaks|"
                r"silently|\btrap"),
    ("constraint", r"必须|只能|不能|不得|禁止|不要|不许|务必|之前不|\bmust\b|\bnever\b|\bonly\b|do not|don't|"
                   r"not allowed|required|\bshould\b"),
    ("preference", r"偏好|喜欢|希望|想要|习惯|默认|倾向|讨厌|\bprefers?\b|\b(dis)?likes?\b|\bwants?\b|"
                   r"rather|default to"),
    ("event", r"\b20\d\d-\d\d-\d\d\b|今天|昨天|上周|已上线|已发布|已合并|发生|\breleased\b|\bmerged\b|\bshipped\b|"
              r"\btagged\b|happened|yesterday|today"),
    ("fact", r"是|在|用|位于|路径|命令|版本|\buses?\b|lives? in|\bruns?\b|\bis\b|\bare\b|\bpath|\bversion|"
             r"\bbuilds?\b|\bgoe?s? in\b|\.py\b|/"),
]


def parse_kind(s: str) -> str:
    """'pitfall' or '坑' -> 'pitfall'; anything else is an error."""
    k = (s or "").strip().lower()
    k = _KIND_ALIASES.get(k, k)
    if k in KINDS:
        return k
    for en, zh in KINDS.items():
        if s.strip() == zh:
            return en
    raise ValueError(f"unknown kind {s!r}; one of: " + ", ".join(f"{k} ({v})" for k, v in KINDS.items()))


def kind_of(e: dict) -> str:
    """The note's kind: its own `kind`, else its topic when that names a kind, else guessed from its words, else
    'other'. Computed when read: old journal lines are never rewritten."""
    for v in (e.get("kind"), e.get("topic")):
        try:
            if v:
                return parse_kind(str(v))
        except ValueError:
            pass
    t = (e.get("text") or "").lower()
    for k, rx in _KIND_WORDS:
        if re.search(rx, t):
            return k
    return "other"


def by_kind_on(p: Paths) -> bool:
    """[memory] by_kind (default false; to be decided by measurement, H11 voided): kinds decide what a start and a brief carry,
    and a brief picks notes by BM25 instead of by shared words."""
    try:
        from .config import load_config
        return bool((load_config(p).get("memory") or {}).get("by_kind", False))
    except Exception:  # noqa: BLE001 — a bad config never changes what a session gets
        return False


def add(p: Paths, text: str, by: str, topic: str = "general", source: str | None = None,
        supersedes: int | None = None, kind: str | None = None) -> dict:
    text = " ".join(text.split())
    if not text:
        raise ValueError("empty memory text")
    ensure(p)
    with _lock(p):
        es = entries(p)
        if any(e["text"] == text for e in es):
            return {"seq": None, "duplicate": True, "text": text}
        seq = _last_seq(p) + 1
        e = {"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": by,
             "topic": topic, "text": text}
        if kind:
            e["kind"] = parse_kind(kind)
        if source:
            e["source"] = source           # where the fact came from (a file, a command, a page)
        if supersedes:
            if not any(x["seq"] == supersedes for x in es):
                raise ValueError(f"no memory note #{supersedes} to replace")
            e["supersedes"] = int(supersedes)
        with open(_journal(p), "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        # the writer has obviously "seen" its own entry
        c = load_cursors(p)
        if c.get(by, 0) == seq - 1:
            c[by] = seq
            _save_cursors(p, c)
        return e


def delta(p: Paths, me: str, advance: bool = True) -> list[dict]:
    """Entries the other side wrote that `me` has not seen yet."""
    if not p.memory.exists():
        return []
    with _lock(p):
        c = load_cursors(p)
        start = max(c.get(me, 0), snapshot_seq(p))
        es = [e for e in entries(p) if e["seq"] > start]
        new = [e for e in es if e.get("by") != me]
        if advance and es:
            c[me] = max(e["seq"] for e in es)
            _save_cursors(p, c)
        return new


def relevant(e: dict, project: str | None) -> bool:
    """A note about this project (its name in the topic, source or text) — H6: these come first."""
    if not project:
        return False
    pj = project.lower()
    return any(pj in str(e.get(k) or "").lower() for k in ("topic", "source", "text"))


def format_delta(new: list[dict], budget: int = DELTA_CHARS, project: str | None = None,
                 shown: list[int] | None = None, kinds: tuple[str, ...] | None = None) -> str:
    """This project's notes first, then newest first, within ~600 tokens; replaced notes say which one they
    replace. The seqs actually shown are appended to `shown` (usage counts, H6). `kinds`: only notes of these
    kinds (L2, behind [memory] by_kind); the rest stay for search and briefs."""
    if not new:
        return ""
    gone = {e.get("supersedes") for e in new if e.get("supersedes")}
    keep = [e for e in new if e["seq"] not in gone and (kinds is None or kind_of(e) in kinds)]
    if not keep:
        return ""
    lines, used, left = ["[ccx shared memory: new since your last session]"], 0, 0
    for e in sorted(keep, key=lambda e: (not relevant(e, project), -e["seq"])):
        extra = f" (replaces #{e['supersedes']})" if e.get("supersedes") else ""
        src = f" [source: {e['source']}]" if e.get("source") else ""
        line = f"- #{e['seq']} ({e['by']}, {e['topic']}){extra}: {e['text']}{src}"
        if used + len(line) > budget:
            left += 1
            continue
        lines.append(line)
        used += len(line)
        if shown is not None:
            shown.append(e["seq"])
    if left:
        lines.append(f"- … {left} more: `ccx mem search <words>` or `ccx mem show`")
    return "\n".join(lines)


BRIEF_NOTES = 4
BRIEF_CHARS = 1200          # ~300 tokens: what a sub-agent's brief may spend on shared notes


_STOP = frozenset("the and for with this that are was were from not but you all can has have had into its our "
                  "out any one two who how what when then than them they their there here will would should could "
                  "also just like more most some such only very use used using".split())
# CJK pairs too common to say what a note is about
_STOP_ZH = frozenset("我们 你们 他们 它们 这个 那个 一个 一些 这些 那些 没有 可以 就是 什么 如果 因为 所以 但是 还是 "
                     "已经 不是 时候 自己 然后 或者 以及 并且 而且 这样 那样 怎么 为了".split())


def _cjk_pairs(t: str) -> list[str]:
    return [run[i:i + 2] for run in re.findall(r"[一-鿿]{2,}", t) for i in range(len(run) - 1)
            if run[i:i + 2] not in _STOP_ZH]


def _words(text: str) -> set[str]:
    """Latin words of 3+ letters (dots and dashes at either end off: `JSON.` is `json`) and CJK pairs, without common
    English and Chinese words: enough to tell which notes a task is about."""
    t = (text or "").lower()
    out = {w.strip(".-") for w in re.findall(r"[a-z0-9_][a-z0-9_.-]{2,}", t)}
    out = {w for w in out if len(w) >= 3 and w not in _STOP}
    out.update(_cjk_pairs(t))
    return out


def _tokens(text: str) -> list[str]:
    """`_words` as a list (BM25 counts repeats), trailing dots and dashes off, `a.b-c` also as its parts, and no
    common English words. Same Latin words of 3+ letters and CJK pairs."""
    t = (text or "").lower()
    out = []
    for w in re.findall(r"[a-z0-9_][a-z0-9_.-]{2,}", t):
        w = w.rstrip(".-")
        if len(w) >= 3 and w not in _STOP:
            out.append(w)
        parts = [x for x in re.split(r"[.-]", w) if len(x) >= 3 and x not in _STOP]
        if len(parts) > 1:
            out.extend(parts)
    out.extend(_cjk_pairs(t))
    return out


def query_terms(text: str) -> list[str]:
    """A query's distinct terms; a word too short to be a token (`ci`, `坑`) is kept whole, matched as a substring."""
    out = list(dict.fromkeys(_tokens(text)))
    for w in (text or "").lower().split():
        if not _tokens(w) and w not in _STOP and w not in out:
            out.append(w)
    return out


BM25_K1, BM25_B = 1.5, 0.75


def bm25(terms: list[str], docs: list[str]) -> list[float]:
    """Okapi BM25 of each doc for these terms (L1). A term that isn't one of a doc's tokens but sits inside its text
    (`snap` in `snapshot`, `坑`) counts half, so a note the old every-word filter found always scores above 0."""
    if not terms or not docs:
        return [0.0] * len(docs)
    toks = [_tokens(d) for d in docs]
    low = [d.lower() for d in docs]
    avg = (sum(len(t) for t in toks) / len(toks)) or 1.0
    tf = []
    for t, d in zip(toks, low):
        row = {}
        for q in terms:
            n = t.count(q) or (d.count(q) * 0.5)
            if n:
                row[q] = n
        tf.append(row)
    df = {q: sum(q in row for row in tf) for q in terms}
    big_n = len(docs)
    out = []
    for t, row in zip(toks, tf):
        norm = BM25_K1 * (1 - BM25_B + BM25_B * max(len(t), 1) / avg)
        out.append(sum(math.log(1 + (big_n - df[q] + 0.5) / (df[q] + 0.5)) * n * (BM25_K1 + 1) / (n + norm)
                       for q, n in row.items()))
    return out


def for_brief(p: Paths, brief: str, project: str | None = None, k: int = BRIEF_NOTES,
              budget: int = BRIEF_CHARS, by_kind: bool | None = None) -> list[dict]:
    """I6: the few notes a task is about (shared words; this project's notes win ties), for a sub-agent's brief
    (sub-agents don't get the start hook's delta). No shared word, no note: an unrelated note costs tokens and helps nothing.
    With [memory] by_kind (L1/L2): ranked by BM25 instead, and events stay out (they are found by search only)."""
    if by_kind is None:
        by_kind = by_kind_on(p)
    scored = []
    if by_kind:
        es = [e for e in live_entries(p) if kind_of(e) not in BRIEF_SKIP]
        for e, s in zip(es, bm25(query_terms(brief), [f"{e.get('topic') or ''} {e['text']}" for e in es])):
            if s:
                scored.append((round(s, 6) + (1e-6 if relevant(e, project) else 0), e["seq"], e))
    else:
        bw = _words(brief)
        for e in live_entries(p):
            n = len(bw & _words(f"{e.get('topic') or ''} {e['text']}"))
            if n:
                scored.append((n + (1 if relevant(e, project) else 0), e["seq"], e))
    out, used = [], 0
    for _n, _s, e in sorted(scored, key=lambda x: (-x[0], -x[1]))[:k]:
        if used + len(e["text"]) > budget:
            continue
        out.append(e)
        used += len(e["text"])
    return out


UNUSED_DAYS = 60


def mark_used(p: Paths, seqs: list[int], by: str | None = None, project: str | None = None,
              via: str | None = None) -> None:
    """A note was shown at a session start, found by a search or put in a sub-agent's brief (H6: how often each one
    is used, and by whom: `by` the tool that saw it, `project` the folder it worked in, `via` start|search|brief)."""
    if not seqs:
        return
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    extra = {k: v for k, v in (("by", by), ("project", project), ("via", via)) if v}
    with _lock(p):
        with open(_meta(p), "a", encoding="utf-8") as f:
            for s in sorted(set(seqs)):
                f.write(json.dumps({"ev": "used", "seq": s, "ts": ts, **extra}) + "\n")


def use_report(p: Paths, days: float = 14) -> dict:
    """H6: in the last `days`, who wrote the notes that were used and who used them (writer x user), per project,
    and how many notes written in that time nobody used. Uses recorded before `by` was kept count as "unknown"."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    arch = p.memory / "journal.archive.jsonl"
    old = []
    if arch.exists():
        for line in arch.read_text(encoding="utf-8").splitlines():
            try:
                old.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    writer = {e["seq"]: e.get("by") or "unknown" for e in [*old, *entries(p)] if "seq" in e}
    matrix: dict[str, dict[str, int]] = {}
    by_project: dict[str, dict[str, dict[str, int]]] = {}
    via: dict[str, int] = {}
    used: set[int] = set()
    try:
        lines = _meta(p).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("ev") != "used" or (ev.get("ts") or "") < cutoff:
            continue
        w, u = writer.get(ev.get("seq"), "unknown"), ev.get("by") or "unknown"
        matrix.setdefault(w, {}).setdefault(u, 0)
        matrix[w][u] += 1
        pj = by_project.setdefault(ev.get("project") or "unknown", {}).setdefault(w, {})
        pj[u] = pj.get(u, 0) + 1
        via[ev.get("via") or "unknown"] = via.get(ev.get("via") or "unknown", 0) + 1
        used.add(ev.get("seq"))
    new = [e for e in entries(p) if (e.get("ts") or "") >= cutoff]
    written: dict[str, int] = {}
    for e in new:
        written[e.get("by") or "unknown"] = written.get(e.get("by") or "unknown", 0) + 1
    return {"days": days, "uses": sum(via.values()), "matrix": matrix, "by_project": by_project, "via": via,
            "written": written, "written_never_used": sum(e["seq"] not in used for e in new)}


def format_use_report(r: dict) -> str:
    """The writer x user matrix as a small text table."""
    users = sorted({u for row in r["matrix"].values() for u in row})
    lines = [f"Shared notes used in the last {r['days']:g} days: {r['uses']} time(s)"
             + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(r["via"].items())) + ")" if r["via"] else "")]
    if users:
        w = max(len("written by \\ used by"), *(len(x) for x in r["matrix"]))
        lines.append("written by \\ used by".ljust(w) + "".join(f"  {u:>8}" for u in users))
        for wr in sorted(r["matrix"]):
            lines.append(wr.ljust(w) + "".join(f"  {r['matrix'][wr].get(u, 0):>8}" for u in users))
    if r["by_project"]:
        lines.append("by project: " + ", ".join(
            f"{pj} {sum(n for row in m.values() for n in row.values())}" for pj, m in sorted(r["by_project"].items())))
    n_new = sum(r["written"].values())
    lines.append(f"written in that time: {n_new}"
                 + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(r["written"].items())) + ")" if n_new else "")
                 + (f", {r['written_never_used']} not used yet" if n_new else ""))
    return "\n".join(lines)


def usage(p: Paths) -> dict[int, dict]:
    """seq -> {"n": times used, "last": when}."""
    out: dict[int, dict] = {}
    try:
        for line in _meta(p).read_text(encoding="utf-8").splitlines():
            ev = json.loads(line)
            if ev.get("ev") == "used":
                u = out.setdefault(ev["seq"], {"n": 0, "last": ""})
                u["n"] += 1
                u["last"] = max(u["last"], ev["ts"])
    except (OSError, ValueError):
        pass
    return out


def unused(p: Paths, days: int = UNUSED_DAYS) -> list[dict]:
    """Notes older than `days` that nobody was shown, found or checked in that time: candidates to clean up."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days * 86400))
    us, va = usage(p), verified_at(p)
    return [{**e, "used": us.get(e["seq"], {}).get("n", 0)} for e in live_entries(p)
            if (e.get("ts") or "") < cutoff and max(us.get(e["seq"], {}).get("last", ""), va.get(e["seq"]) or "") < cutoff]


def _split_notes(text: str) -> tuple[str, dict[str, list[str]], str]:
    """-> (text before the notes section, existing notes by topic, text after it)."""
    m = NOTES_BEGIN.search(text)
    if not m:
        return text, {}, ""
    end = text.find(NOTES_END, m.end())
    if end == -1:
        return text, {}, ""
    body = text[m.end():end]
    blocks: dict[str, list[str]] = {}
    cur = None
    for line in body.splitlines():
        if line.startswith("### "):
            cur = line[4:].strip()
            blocks.setdefault(cur, [])
        elif line.startswith("- ") and cur:
            blocks[cur].append(line[2:].strip())
    return text[:m.start()], blocks, text[end + len(NOTES_END):]


def compact(p: Paths) -> dict:
    """Fold all journal entries into a marked notes section of the snapshot; archive the journal.

    The snapshot may be a file other tools also read (e.g. a shared AGENTS.md that one tool sees through
    a hard link). It is rewritten IN PLACE (same inode), never replaced, so such links keep working."""
    ensure(p)
    if not p.memory_index.exists():
        raise FileNotFoundError(f"snapshot {p.memory_index} does not exist")
    with _lock(p):
        es = entries(p)
        if not es:
            return {"folded": 0, "seq": snapshot_seq(p)}
        text = p.memory_index.read_text(encoding="utf-8")
        head, blocks, tail = _split_notes(text)
        existing = {t for items in blocks.values() for t in items}
        replaced = {x["text"] for x in es if any(y.get("supersedes") == x["seq"] for y in es)}
        for items in blocks.values():                # a replaced note leaves the snapshot too
            items[:] = [t for t in items if t not in replaced]
        for e in es:
            if e["text"] in replaced:
                continue
            if e["text"] not in existing:
                blocks.setdefault(e["topic"], []).append(e["text"])
                existing.add(e["text"])
        seq = max(e["seq"] for e in es)
        body = "\n".join(f"### {topic}\n" + "\n".join(f"- {t}" for t in items) for topic, items in blocks.items())
        section = f"<!-- ccx:notes begin seq={seq} -->\n{NOTES_TITLE}\n\n{body}\n{NOTES_END}"
        new = head.rstrip() + "\n\n" + section + ("\n" + tail.lstrip("\n") if tail.strip() else "\n")
        with open(p.memory_index, "r+", encoding="utf-8", newline="") as f:   # in place: keeps hard links
            f.seek(0)
            f.write(new)
            f.truncate()
        arch = p.memory / "journal.archive.jsonl"
        with open(arch, "a", encoding="utf-8") as f:
            for e in es:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        _journal(p).write_text("", encoding="utf-8")
        return {"folded": len(es), "seq": seq, "snapshot": str(p.memory_index),
                "snapshot_bytes": len(new.encode("utf-8"))}


SCENE_CHARS = 400           # ~100 tokens: one project's scene block
SCENE_LINE = 90
SCENES_TITLE = "# 按项目的场景块 / Scene blocks by project（ccx mem compact --by project 生成，勿手改 / generated, do not edit）"


def _scenes_file(p: Paths) -> Path:
    return p.memory / "scenes.md"


def project_names(p: Paths) -> list[str]:
    """Projects a note can belong to: the catalog's (`ccx projects scan`) and the ones notes were used in."""
    names: list[str] = []
    try:
        from . import projects
        names += [str(x.get("name")) for x in (projects.load(p).get("projects") or []) if x.get("name")]
    except Exception:  # noqa: BLE001 — no catalog: the used-in projects still count
        pass
    try:
        for line in _meta(p).read_text(encoding="utf-8").splitlines():
            ev = json.loads(line)
            if ev.get("ev") == "used" and ev.get("project"):
                names.append(str(ev["project"]))
    except (OSError, ValueError):
        pass
    return [n for n in dict.fromkeys(names) if n and n != "unknown"]


def _snapshot_notes(p: Paths) -> list[str]:
    if not p.memory_index.exists():
        return []
    _h, blocks, _t = _split_notes(p.memory_index.read_text(encoding="utf-8"))
    return [t for items in blocks.values() for t in items]


def scenes(p: Paths, names: list[str] | None = None, budget: int = SCENE_CHARS) -> dict[str, list[str]]:
    """L3: notes grouped by the project they name (topic, source or text), newest first, each cut to one short
    line, within `budget` per project. A note naming no project is left to search; nothing is summarised by a model."""
    names = project_names(p) if names is None else names
    notes = [e for e in reversed(live_entries(p))]
    have = {e["text"] for e in notes}
    notes += [{"seq": None, "text": t} for t in _snapshot_notes(p) if t not in have]
    out: dict[str, list[str]] = {}
    for n in sorted(names, key=len, reverse=True):          # `relayline-site` before `relayline`
        lines, used, left = [], 0, 0
        for e in notes:
            if e.get("_scene") or not relevant(e, n):
                continue
            e["_scene"] = n
            t = e["text"] if len(e["text"]) <= SCENE_LINE else e["text"][:SCENE_LINE - 1] + "…"
            line = (f"#{e['seq']} " if e.get("seq") else "") + t
            if used + len(line) > budget:
                left += 1
                continue
            lines.append(line)
            used += len(line)
        if left:
            lines.append(f"… {left} more: `ccx mem search {n}`")
        if lines:
            out[n] = lines
    for e in notes:
        e.pop("_scene", None)
    return dict(sorted(out.items()))


def compact_by_project(p: Paths) -> dict:
    """`ccx mem compact --by project`: (re)write memory/scenes.md, one short block per project. The journal and the
    snapshot are left as they are; nothing reads the file at a session start unless [memory] start_scene is on."""
    ensure(p)
    sc = scenes(p)
    body = "\n\n".join(f"## {n}\n" + "\n".join(f"- {x}" for x in lines) for n, lines in sc.items())
    text = SCENES_TITLE + "\n\n" + body + "\n"
    with _lock(p):
        _scenes_file(p).write_text(text, encoding="utf-8")
    return {"by": "project", "projects": len(sc), "file": str(_scenes_file(p)),
            "bytes": len(text.encode("utf-8")),
            "largest_block_bytes": max([len("\n".join(v).encode("utf-8")) for v in sc.values()] or [0])}


def scene_block(p: Paths, project: str | None) -> str:
    """This project's block from memory/scenes.md, or '' (no file, no block)."""
    f = _scenes_file(p)
    if not project or not f.exists():
        return ""
    cur, lines = None, []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
        elif cur == project and line.startswith("- "):
            lines.append(line)
    return f"[ccx shared memory: {project}]\n" + "\n".join(lines) if lines else ""


def start_scene_on(p: Paths) -> bool:
    try:
        from .config import load_config
        return bool((load_config(p).get("memory") or {}).get("start_scene", False))
    except Exception:  # noqa: BLE001
        return False
