"""Independent review (proposal F1): after a write run, a cheap model from another vendor reads the diff against
the task and answers pass / issues, so the lead reads a verdict and the problem spots instead of the whole change.

Only when it is worth it (`auto`, the default): the task was marked visible or critical, the change has 50+ changed
code lines, the sub-agent listed things it is unsure of (open_questions), or its claimed files don't match the
actual diff, or the only evidence is weak (H13: the acceptance command let wrong work through before, or there is
none and only the sub-agent checked itself; at most `weak_daily` of these a day). `on` reviews every write run
with changes, `off` never. The same model reviewing its own work misses its own mistakes, so the reviewer is always
another vendor ([review] by in tiers.toml). Issues go back to the same sub-session for one fix round, which is
reviewed again; still failing -> kind review_failed, for the lead to decide."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Paths
    from .delegate import Request

MARK = "[ccx review"
BRIEF = """{mark} of run {run_id}] Review a change another agent made. Do not edit anything.

## The task it was given
{task}

## What it says it did
{summary}

## The change (git diff against the tree before it started{cut})
```diff
{diff}
```

## Checks
{check}

## Answer
You cannot run commands; judge from the diff and the files. Do not report that tests were not run.
First go through the task above requirement by requirement (each return value, case, rule and error it names) and
check the code meets it; the acceptance tests may cover only some of them. Report a problem as
`[must] file:line — what is wrong` only if it makes the change wrong for the task as stated: a requirement not met,
a bug a test would catch, a broken behaviour that worked before, or a real safety problem (code execution, secrets,
data loss). Missing tests, inputs the task doesn't cover, typing or docs taste and style are `[note] ...`, at most 3. Start summary with exactly `REVIEW: pass` (no [must]) or
`REVIEW: issues` (at least one [must]); put the items in open_questions, [must] first. Status done."""


def _git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def changes(cwd: Path, snap: dict | None) -> tuple[list[str], str]:
    """(changed paths, diff text) since the undo snapshot: tracked edits plus files that are new since then."""
    if not snap:
        return [], ""
    base = snap["base"]
    names = [n for n in _git(cwd, "diff", "--name-only", base).splitlines() if n and not n.startswith(".ccx/")]
    diff = _git(cwd, "diff", base, "--", ".", ":(exclude).ccx")
    before = set(snap.get("untracked") or [])
    for n in _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines():
        if n and n not in before and not n.startswith(".ccx/"):
            names.append(n)
            try:
                body = (Path(snap["repo"]) / n).read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                body = ""
            diff += f"\n--- /dev/null\n+++ b/{n}\n" + "".join(f"+{ln}\n" for ln in body.splitlines())
    return names, diff


def _norm(f: str) -> str:
    return f.replace("\\", "/").lstrip("./").lower()


DOC_SUFFIXES = (".md", ".txt", ".rst", ".adoc")


def code_lines(diff: str) -> int:
    """Changed lines (added + removed) in code files, docs not counted."""
    n, doc = 0, False
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            doc = ln.rstrip().lower().endswith(DOC_SUFFIXES)
        elif ln.startswith(("+", "-")) and not ln.startswith(("---", "+++")) and not doc:
            n += 1
    return n


def reason(mode: str, risk: str | None, result: dict, claimed: list[str], actual: list[str],
           lines: int = 0, min_lines: int = 50) -> str | None:
    """Why to review this run, or None. Called only for write runs that changed something and passed their check."""
    if mode == "off" or not actual:
        return None
    if mode == "on":
        return "asked"
    if risk in ("visible", "critical"):
        return f"risk {risk}"
    if min_lines and lines >= min_lines:
        # big enough that reading the verdict instead of the diff pays for the review (F1 trial: ~50 lines), and
        # the trial's one real bug sat in a change none of the other triggers would have reviewed
        return f"{lines} changed code lines"
    if result.get("open_questions"):
        return "the sub-agent is unsure"
    a = {_norm(f) for f in actual}
    c = {_norm(f) for f in claimed}
    if c and not any(x.endswith(y) or y.endswith(x) for x in a for y in c):
        return "its claimed files don't match the diff"
    if not c:
        return "it reported no files but the tree changed"
    return None


def weak_reason(p: Paths, rc: dict, record: dict, now: float | None = None) -> str | None:
    """H13: in `auto`, also review when the evidence that the work is right is weak, up to `weak_daily` a day
    (`weak = false` in [review] switches this off). Each such review is logged, which is how the cap is counted."""
    import time
    from . import ledger
    if not rc.get("weak", True):
        return None
    check = record.get("check") or {}
    res = record.get("result") or {}
    if check.get("weak"):
        why = "weak check: this acceptance command let wrong work through before"
    elif not check and res.get("verification", "not-run") not in ("", "not-run"):
        why = "only the sub-agent's own check"
    else:
        return None
    now = now or time.time()
    t = time.localtime(now)
    midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    today = sum(1 for r in ledger.rows(p) if r.get("type") == "weak_review" and (r.get("ts") or 0) >= midnight)
    if today >= int(rc.get("weak_daily", 20)):
        return None
    ledger.append_event(p, {"type": "weak_review", "run_id": record.get("run_id"), "why": why, "ts": now})
    return why


REVIEW_B = 3.0           # a review reads one diff against one brief: routed like an easy read-only task


def reviewers(cfg: dict, worker: str, installed, p=None) -> list[tuple[str, str, str]]:
    """(agent, model, effort) candidates for reviewing `worker`'s work, best first: models of another vendor (I3),
    never a cash provider. Order: what the person pinned in [review] by; then, per installed agent of another
    vendor, the rung routing finds cheapest for an easy read (I4: from data, not a fixed table); then
    [review] also. The next one is tried when a review can't finish (haiku ran out of structured-output retries
    twice in the 2026-10-24 trial)."""
    from .agents import NAMES, get, others, same_vendor
    rc = cfg.get("review") or {}
    by = rc.get("by") or {}
    rungs = [by.get(worker)] + [v for k, v in by.items() if k != worker]
    # cheapest rung of each other vendor first: routing picked sonnet medium for reviews in the seven-cores A/B,
    # 20–40x the luna-low work it reviewed, with no gain in pass rate (PR #30); sonnet stays as the fallback (also)
    for agent in filter(installed, others(worker, cfg, only_installed=False)):
        t1 = ((cfg.get("tiers") or {}).get("T1") or {}).get(agent)
        if isinstance(t1, dict) and t1.get("model"):
            rungs.append(f"{agent}:{t1['model']}:{t1.get('effort', 'low')}")
    if p is not None:
        from . import learn
        for agent in filter(installed, others(worker, cfg, only_installed=False)):
            try:
                rungs.append(learn.pick(p, REVIEW_B, [agent], "save", mode="read", kind="read")["rung"])
            except Exception:  # noqa: BLE001 — no routing data for it: the pinned ones still apply
                pass
    out, pinned = [], set(filter(None, by.values()))
    for rung in filter(None, rungs + list(rc.get("also") or [])):
        agent, model, effort = rung.split(":", 2)
        cash = agent in NAMES and get(agent).pay_per_token and rung not in pinned   # real money: only if pinned
        if (agent in NAMES and not cash and not same_vendor(agent, worker, cfg) and installed(agent)
                and (agent, model, effort) not in out):
            out.append((agent, model, effort))
    return out


def brief(run_id: str, task: str, summary: str, diff: str, max_chars: int, check: dict | None = None) -> str:
    cut = f"; cut to {max_chars} characters, open the files for the rest" if len(diff) > max_chars else ""
    ran = (f"ccx ran the acceptance command `{check['cmd']}` after the change: "
           f"{'passed' if check.get('passed') else 'FAILED (exit %s)' % check.get('exit')}." if check
           else "No acceptance command was given; nobody ran the tests for you.")
    return BRIEF.format(mark=MARK, run_id=run_id, task=task.strip()[:2000], summary=(summary or "")[:800],
                        diff=diff[:max_chars] or "(empty)", cut=cut, check=ran)


_PREFIX = re.compile(r"^[\s*_`#>]*review\s*[:：]?\s*[*_`]*\s*(pass|issues)\b", re.I)


def verdict(result: dict | None) -> dict:
    r = result or {}
    s = (r.get("summary") or "").strip()
    m = _PREFIX.match(s)
    v = m.group(1).lower() if m else "unclear"
    items = [str(x)[:300] for x in (r.get("open_questions") or [])]
    must = [x for x in items if x.lstrip().lower().startswith("[must]")]
    notes = [x for x in items if x not in must]
    lenient = False
    if v == "unclear" and items:
        # no `REVIEW: ...` line (e.g. the summary written in another language, round 2 of the seven-cores A/B:
        # haiku named the real bug as [must] and the run was left unfixed): the tagged items still say it
        if must:
            v, lenient = "issues", True
        elif all(x.lstrip().lower().startswith("[note]") for x in notes):
            v, lenient = "pass", True
    if v == "issues" and not must and notes and any(x.lstrip().lower().startswith("[note]") for x in notes):
        v = "pass"                    # only notes: nothing that makes the change wrong, so no fix round
    out = {"verdict": v, "issues": (must or ([] if v == "pass" else notes))[:8], "summary": s[:400]}
    if lenient:
        out["format"] = "lenient"
    if v == "pass" and notes:
        out["notes"] = notes[:3]
    return out


def review_run(req: Request, p: Paths, cfg: dict, record: dict, cwd: Path, run_dir: Path) -> None:
    """F1: maybe have another vendor's cheap model review this write run's diff; sets record["review"]."""
    from .delegate import Request, run
    from .runners import find_bin
    import sys
    rv = sys.modules[__name__]
    rc = cfg.get("review") or {}
    mode = req.review if req.review != "auto" else rc.get("mode", "auto")
    first = req.resume_run if (req.resume_run and not req.continued) else None
    undo = (p.runs / first / "undo.json") if first else (run_dir / "undo.json")
    snap = json.loads(undo.read_text(encoding="utf-8")) if undo.exists() else None
    actual, diff = rv.changes(cwd, snap)
    res = record.get("result") or {}
    why = rv.reason(mode, req.risk, res, res.get("files_changed") or [], actual, rv.code_lines(diff),
                    int(rc.get("min_lines", 50)))
    if not why and mode == "auto" and actual:
        why = rv.weak_reason(p, rc, record)
    if not why:
        return
    cands = rv.reviewers(cfg, req.provider or req.to, find_bin, p)
    if not cands:
        record["review"] = {"verdict": "not-run", "reason": why, "error": "no reviewer from another vendor installed"}
        return
    text = rv.brief(record["run_id"], req.brief, res.get("summary", ""), diff, int(rc.get("max_diff_chars", 12000)),
                    record.get("check"))
    usd, tried = 0.0, []
    for agent, model, effort in cands[:2]:
        rev = run(Request(to=agent, model=model, effort=effort, tier="auto", mode="read", cwd=cwd, brief=text,
                          caller="ccx-review", escalate=False, fallback=False, review="off", allow_subagents=False,
                          ephemeral=True, label=f"review:{record['run_id']}"), p)
        usd += sum(a.get("ae_usd") or 0 for a in rev.get("attempts", []))
        tried.append(f"{agent}:{model}:{effort}")
        v = rv.verdict(rev.get("result")) if rev.get("ok") else {"verdict": "not-run", "issues": [],
                                                                 "summary": (rev.get("error") or "")[:300]}
        if v["verdict"] != "not-run":
            break
    record["review"] = {**v, "reason": why, "by": tried[-1], "run_id": rev["run_id"], "usd": round(usd, 4)}
    if len(tried) > 1:
        record["review"]["tried"] = tried
    if v["verdict"] == "issues":
        record["kind"] = ("review_issues" if req.review_round < int(rc.get("fix_rounds", 1)) else "review_failed")
