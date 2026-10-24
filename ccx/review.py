"""Independent review (proposal F1): after a write run, a cheap model from another vendor reads the diff against
the task and answers pass / issues, so the lead reads a verdict and the problem spots instead of the whole change.

Only when it is worth it (`auto`, the default): the task was marked visible or critical, the change has 50+ changed
code lines, the sub-agent listed things it is unsure of (open_questions), or its claimed files don't match the
actual diff. `on` reviews every write run
with changes, `off` never. The same model reviewing its own work misses its own mistakes, so the reviewer is always
another vendor ([review] by in tiers.toml). Issues go back to the same sub-session for one fix round, which is
reviewed again; still failing -> kind review_failed, for the lead to decide."""
from __future__ import annotations

import subprocess
from pathlib import Path

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
Report a problem as `[must] file:line — what is wrong` only if it makes the change wrong for the task as stated: a
bug a test would catch, a broken behaviour that worked before, the new behaviour left untested, or a real safety
problem (code execution, secrets, data loss). Anything else worth saying (inputs the task doesn't cover, typing or
docs taste, style) is `[note] ...`, at most 3. Start summary with exactly `REVIEW: pass` (no [must]) or
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


REVIEW_B = 3.0           # a review reads one diff against one brief: routed like an easy read-only task


def reviewers(cfg: dict, worker: str, installed, p=None) -> list[tuple[str, str, str]]:
    """(agent, model, effort) candidates for reviewing `worker`'s work, best first: models of another vendor (I3),
    never a cash provider. Order: what the person pinned in [review] by; then, per installed agent of another
    vendor, the rung routing finds cheapest for an easy read (I4: from data, not a fixed table); then
    [review] also. The next one is tried when a review can't finish (haiku ran out of structured-output retries
    twice in the 2026-10-24 trial)."""
    from .agents import NAMES, others, same_vendor
    rc = cfg.get("review") or {}
    by = rc.get("by") or {}
    rungs = [by.get(worker)] + [v for k, v in by.items() if k != worker]
    if p is not None:
        from . import learn
        for agent in others(worker, cfg):
            try:
                rungs.append(learn.pick(p, REVIEW_B, [agent], "save", mode="read", kind="read")["rung"])
            except Exception:  # noqa: BLE001 — no routing data for it: the pinned ones still apply
                pass
    out = []
    for rung in filter(None, rungs + list(rc.get("also") or [])):
        agent, model, effort = rung.split(":", 2)
        if (agent in NAMES and not same_vendor(agent, worker, cfg) and installed(agent)
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


def verdict(result: dict | None) -> dict:
    r = result or {}
    s = (r.get("summary") or "").strip()
    v = "issues" if s.upper().startswith("REVIEW: ISSUES") else "pass" if s.upper().startswith("REVIEW: PASS") \
        else "unclear"
    items = [str(x)[:300] for x in (r.get("open_questions") or [])]
    must = [x for x in items if x.lstrip().lower().startswith("[must]")]
    notes = [x for x in items if x not in must]
    if v == "issues" and not must and notes and any(x.lstrip().lower().startswith("[note]") for x in notes):
        v = "pass"                    # only notes: nothing that makes the change wrong, so no fix round
    out = {"verdict": v, "issues": (must or ([] if v == "pass" else notes))[:8], "summary": s[:400]}
    if v == "pass" and notes:
        out["notes"] = notes[:3]
    return out
