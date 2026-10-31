"""Verdict audit (P1-10): ccx's final receipt against the hidden tests, for every unit of a ccx arm in the evaluations.

Read-only. It reads the results files under EVAL (.ccx/eval: r4/, r5/), each unit's hub where the evaluation kept it
(WORK: the temp folder holding the r4c/r4l/r5*/r6a/m1r5 work dirs) and, where the hub was removed after scoring
(hold-out runs hc1 and m1h2), the lead's stream kept under EVAL/r5/streams/<tag>/: the last ccx receipt the lead saw.

    python scripts/research/verdict_audit.py --eval .ccx/eval --work "%TEMP%" [--out units.json] [--repo .]

ccx says "right" when the final run of every chain in the unit has the receipt's top line ok: ok, no bad kind
(review_issues, review_failed, check_broken, no_changes, check_failed, env), no failed check, review not issues or
failed, status done or partial. --strict asks status done (a sub-agent's "partial" counts as wrong). A run the lead
continued (`ccx resume <run>`, or ccx's fix round) is not final: the run that continued it is.
Hidden test = the unit's `ok` (pytest on the commit's own test files). Pilot and aborted runs are left out.
Prints the 2x2 tables before / after #158 and every "said right, actually wrong" unit with its cause.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter
from fnmatch import fnmatch
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COUNTED = ["r4/calib.jsonl", "r4/long.jsonl", "r5/results.jsonl", "r5/holdout-results.jsonl",
           "r5/m1h2-results.jsonl", "r5/m1r5-results.jsonl"]
LEFT_OUT = ["r5/pilot-dropped.jsonl", "r5/m1r5-aborted-results.jsonl", "r5/m1h-results.jsonl",
            "r5/m1r5-part1-results.jsonl", "r5/pg0-results.jsonl", "r4/long-pilot-dropped.jsonl"]
BAD_KINDS = ("review_issues", "review_failed", "check_broken", "no_changes", "env", "check_failed")
PR158 = "12599c0"                      # review fix round gets every [must]; no_changes; reviewer permission text
PR158_TS = 1793217746.0                # its merge time (2026-10-28 16:02:26 -04:00), for rows without a fingerprint
NO_LEAD = {"direct", "luna", "haiku", "flash", "luna_rev"}   # ccx run straight from the brief, no lead
RESUME = re.compile(r"\bresume\s+(\d{8}-\d{6}-[0-9a-f]{4})")
sys.path.insert(0, str(ROOT / "scripts" / "eval"))           # the task lists (hidden test files), read only


def load(f: Path) -> list[dict]:
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def after_158(commit: str | None, ts: float | None, repo: Path) -> bool:
    if commit:
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", PR158, commit], cwd=repo,
                            capture_output=True).returncode
        if rc not in (0, 1):                             # 128: a commit this clone does not have
            raise SystemExit(f"commit {commit} not in {repo}: fetch the full history")
        return rc == 0
    return float(ts or 0) > PR158_TS


def why_not(o: dict, status: str | None) -> list[str]:
    """Why a run record or receipt does not say right ([] = it does). 'status partial' alone is the soft case."""
    out = [] if o.get("ok") else ["not ok"]
    if status != "done":
        out.append(f"status {status}")
    if o.get("kind") in BAD_KINDS:
        out.append(f"kind {o['kind']}")
    if (o.get("check") or {}).get("passed") is False:
        out.append("check failed")
    if (o.get("review") or {}).get("verdict") in ("issues", "failed"):
        out.append(f"review {o['review']['verdict']}")
    return out


def hub_index(work: Path) -> dict[str, set]:
    idx: dict[str, set] = {}
    for h in glob.glob(str(work / "*" / "h-*" / "ccx" / "runs")):
        for rid in os.listdir(h):
            idx.setdefault(rid, set()).add(Path(h).parent.parent)
    return idx


def find_hub(r: dict, idx: dict, work: Path) -> Path | None:
    ids = r.get("ccx_run_ids") or []
    if ids:                                          # the hub holding exactly this unit's runs
        hubs = set.intersection(*[idx.get(i, set()) for i in ids])
        return hubs.pop() if len(hubs) == 1 else None
    parts = str(r.get("label") or "").split(":")     # r4 long rows carry no run ids: by the unit's key
    if len(parts) >= 5:
        h = work / "r4l" / f"h-{parts[2].lower()}-{parts[3]}-{parts[4]}"
        if (h / "ccx" / "runs").exists():
            return h
    return None


def receipts(stream: Path) -> tuple[list[dict], set]:
    """Every ccx receipt (JSON with run_id, status, ok) in the lead's tool results, in order, and the runs the lead
    continued with `ccx resume <run>` (a receipt does not say which run it resumed)."""
    out, resumed = [], set()
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    resumed |= set(RESUME.findall(json.dumps(c.get("input") or {})))
            continue
        if e.get("type") != "user":
            continue
        for c in (e.get("message") or {}).get("content") or []:
            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                continue
            t = c["content"] if isinstance(c["content"], str) else " ".join(
                x.get("text", "") for x in c["content"] if isinstance(x, dict))
            i = t.find("{")
            while i != -1:
                try:
                    obj, end = json.JSONDecoder().raw_decode(t, i)
                except ValueError:
                    i = t.find("{", i + 1)
                    continue
                if isinstance(obj, dict) and {"run_id", "status", "ok"} <= set(obj):
                    out.append(obj)
                i = t.find("{", end)
    return out, resumed


def review_denials(hub: Path) -> int:
    """Tool calls refused to the Claude reviewer (permission_denials in its event log), over the unit's reviews."""
    n = 0
    for d in (hub / "ccx" / "runs").iterdir():
        try:
            rec = json.loads((d / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(rec.get("label") or "").startswith("review:"):
            continue
        for ev in d.glob("events.*.log"):
            for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    n += len(json.loads(line).get("permission_denials") or [])
                except (ValueError, AttributeError):
                    pass
    return n


def final_of(x: dict, status: str | None, review: dict | None, first: dict | None) -> dict:
    return {"why": why_not(x, status), "status": status, "kind": x.get("kind"),
            "check": (x.get("check") or {}).get("cmd"), "check_passed": (x.get("check") or {}).get("passed"),
            "review": (review or {}).get("verdict"), "first_review": (first or {}).get("verdict"),
            "files": None if "files_changed" not in x and "result" not in x
            else len(x.get("files_changed") or (x.get("result") or {}).get("files_changed") or [])}


def audit(r: dict, idx: dict, work: Path, ev: Path) -> dict | None:
    u = {k: r.get(k) for k in ("tag", "round", "task", "arm", "env_clean", "files_changed", "lead_edits", "pytest")}
    u.update(hidden_ok=bool(r.get("ok")), commit=(r.get("fingerprint") or {}).get("commit"), ts=r.get("ts"))
    hub = find_hub(r, idx, work)
    name = f"{r['round']}-{r['task']}-{r['arm']}.stream.jsonl"
    stream = ev / "r5" / "streams" / str(r.get("tag")) / name
    if hub and not stream.exists():
        stream = hub.parent / name                   # dev-set work dirs keep the stream next to the hub
    if hub:
        recs = []
        for d in (hub / "ccx" / "runs").iterdir():
            try:
                recs.append(json.loads((d / "run.json").read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        work_runs = [x for x in recs if not str(x.get("label") or "").startswith("review:")]
        if not work_runs:
            return None                                  # the lead never delegated: no receipt
        parents = {x.get("resumed_from") for x in work_runs} | {x.get("review_of") for x in work_runs}
        u["source"] = "hub"
        u["finals"] = [final_of(x, (x.get("result") or {}).get("status"), x.get("review"), x.get("first_review"))
                       for x in work_runs if x["run_id"] not in parents]
        u["review_denials"] = review_denials(hub)
        rc = receipts(stream)[0] if stream.exists() else []
        if rc:                                           # cross-check: what the lead saw last
            u["stream_says_right"] = not [w for w in why_not(rc[-1], rc[-1].get("status")) if w != "status partial"]
    elif stream.exists() and receipts(stream)[0]:
        rc, resumed = receipts(stream)
        last = {o["run_id"]: o for o in rc}
        done_with = {o.get("fixed_after_review_of") for o in rc} | resumed
        u["source"] = "stream"
        u["finals"] = [final_of(o, o.get("status"), o.get("review"), (o.get("review") or {}).get("first_round"))
                       for k, o in last.items() if k not in done_with]
    elif r.get("ccx_ok") is not None:                    # r4 calibration: ccx run from the brief, row fields only
        chk, rv = r.get("check") or {}, r.get("review") or {}
        x = {"ok": r["ccx_ok"], "check": chk, "review": rv}
        u["source"] = "row"
        u["finals"] = [final_of(x, r.get("status"), rv, None)]
    else:
        return None
    return u


def says(u: dict, strict: bool) -> bool:
    soft = set() if strict else {"status partial"}
    return all(set(f["why"]) <= soft for f in u["finals"])


def hidden_files(task: str) -> list[str] | None:
    import tasks_holdout
    import tasks_r5
    for mod in (tasks_r5, tasks_holdout):
        try:
            return list(mod.by_id(task)["tests"])
        except StopIteration:
            continue
    return None                                          # r4's synthetic tasks: the hidden test is its own file


def cause(u: dict) -> str:
    f = u["finals"][-1]
    if u.get("files_changed") == 0 or f["files"] == 0:
        return "A patch not landed"
    if not f["check"]:
        return "B no check, review only"
    hid = hidden_files(u["task"])
    if hid is None:
        return "C1 check did not run the hidden test's file (synthetic task: visible tests only)"
    globs = [Path(t).name for t in f["check"].split() if "test" in t and t.endswith(".py")]
    ran = [h for h in hid if any(fnmatch(Path(h).name, g) for g in globs)]
    if not ran:
        return "C1 check did not run the hidden test's file"
    if len(ran) < len(hid):
        return "C2 check ran some of the hidden test files (the sub-agent's version)"
    return "C2 check ran the same test file (the sub-agent's version)"


def wrong_class(u: dict) -> str:
    """Why a receipt said wrong, one class per unit: broken check command, failed check, failed review, a rule, other."""
    kinds = [f["kind"] for f in u["finals"]]
    if "check_broken" in kinds:
        return "check command broken"
    if "check_failed" in kinds or any(f["check_passed"] is False for f in u["finals"]):
        return "check failed"
    if any(k in ("review_failed", "review_issues") or f["review"] in ("issues", "failed")
           for k, f in zip(kinds, u["finals"])):
        return "review [must]"
    if "no_changes" in kinds:
        return "rule: no_changes"
    return "other"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p, d = k / n, 1 + z * z / n
    c, h = p + z * z / (2 * n), z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def table(name: str, us: list[dict], strict: bool) -> dict:
    c = Counter((says(u, strict), u["hidden_ok"]) for u in us)
    tt, tf, ft, ff = c[(True, True)], c[(True, False)], c[(False, True)], c[(False, False)]
    lo, hi = wilson(tf, tt + tf)
    print(f"{name:34s} n={len(us):3d}  right/right {tt:3d}  SAID RIGHT, WRONG {tf:2d}  said wrong, right {ft:3d}  "
          f"wrong/wrong {ff:2d}  false 'right' {tf}/{tt + tf} = {tf / max(1, tt + tf):.1%} (95% {lo:.1%}-{hi:.1%})")
    return {"n": len(us), "right_right": tt, "said_right_wrong": tf, "said_wrong_right": ft, "wrong_wrong": ff}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--eval", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--repo", default=ROOT, type=Path)
    ap.add_argument("--out", type=Path, help="write the scrubbed per-unit rows here (no paths)")
    ap.add_argument("--strict", action="store_true", help="a sub-agent's status partial counts as said wrong")
    a = ap.parse_args()
    idx = hub_index(a.work)
    units = []
    for f in COUNTED:
        for r in load(a.eval / f):
            u = audit(r, idx, a.work, a.eval)
            if u:
                u["file"] = f
                u["after_158"] = after_158(u["commit"], u["ts"], a.repo)
                u["lead"] = "no lead" if u["arm"] in NO_LEAD else "lead"
                units.append(u)
    left = sum(len(load(a.eval / f)) for f in LEFT_OUT if (a.eval / f).exists())
    print(f"{len(units)} units with a ccx receipt; {left} pilot/aborted rows left out\n")
    out = {}
    for name, sel in [("all", lambda u: True), ("before #158", lambda u: not u["after_158"]),
                      ("after #158", lambda u: u["after_158"]),
                      ("before #158, no lead", lambda u: not u["after_158"] and u["lead"] == "no lead"),
                      ("before #158, with a lead", lambda u: not u["after_158"] and u["lead"] == "lead")]:
        out[name] = table(name, [u for u in units if sel(u)], a.strict)
    for f in COUNTED:
        for af in (False, True):
            us = [u for u in units if u["file"] == f and u["after_158"] == af]
            if us:
                table(f"  {f} {'after' if af else 'before'}", us, a.strict)
    print("\nsaid right, actually wrong:")
    for u in units:
        if says(u, a.strict) and not u["hidden_ok"]:
            u["cause"] = cause(u)
            f = u["finals"][-1]
            print(f"  {'after ' if u['after_158'] else 'before'} {u['tag']}:{u['round']}:{u['task']}:{u['arm']}  "
                  f"{u['cause']}  | check: {f['check']}  | review {f['review']} (first {f['first_review']})  "
                  f"| status {f['status']} | reviewer denials {u.get('review_denials')} | hidden {u['pytest']}")
    for af in (False, True):
        fn = [u for u in units if u["after_158"] == af and not says(u, a.strict) and u["hidden_ok"]]
        for u in fn:
            u["wrong_class"] = wrong_class(u)
        print(f"\nsaid wrong, actually right, {'after' if af else 'before'} #158: {len(fn)}",
              dict(Counter(u["wrong_class"] for u in fn).most_common()),
              "| lead edited:", sum((u.get("lead_edits") or 0) > 0 for u in fn))
    cross = [u for u in units if "stream_says_right" in u]
    print(f"\nhub vs the lead's last receipt: {sum(says(u, False) != u['stream_says_right'] for u in cross)} "
          f"of {len(cross)} units differ")
    if a.out:
        keep = ("file", "tag", "round", "task", "arm", "lead", "after_158", "commit", "env_clean", "source",
                "hidden_ok", "pytest", "files_changed", "lead_edits", "review_denials", "finals", "cause", "wrong_class")
        a.out.write_text(json.dumps({"summary": out, "units": [{k: u.get(k) for k in keep} for u in units]},
                                    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
