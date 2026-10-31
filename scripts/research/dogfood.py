"""Dogfood (P1-11): what the real hub's ledger says about 2026-10-24 00:00 to 2026-10-31 00:00 local time. Read-only.

    python scripts/research/dogfood.py <hub>/ccx/ledger.jsonl > summary.json

Prints counts and costs only: no paths, labels or project names (a project is counted by its folder, never named).
Every run is put in one group by its label and folder: eval/trial (eval-*, f1-trial*, calib-*, or run in an f1-trial or
ccx-7c-* folder), probe/acceptance (selftest, quota-probe, probe-*, startup-probe, E8 accept, live-ds*, two-way*,
untried*, discuss:*, desktop-*, *-real checks of a fix),
temp dir (no such label, run in a temp folder: ad-hoc tests), real work (the rest). A review run joins its run's group.
"""
import json, sys, collections, datetime

L = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
TZ = datetime.timezone(datetime.timedelta(hours=-4))       # the machine's local time that week (EDT): fixed, so a rerun agrees
t0 = datetime.datetime(2026, 10, 24, tzinfo=TZ).timestamp()
t1 = datetime.datetime(2026, 10, 31, tzinfo=TZ).timestamp()
inwin = [r for r in L if t0 <= float(r.get("ts") or 0) < t1]
runs = [r for r in inwin if not r.get("type")]
events = [r for r in inwin if r.get("type")]
by_id = {r["run_id"]: r for r in runs}

EVAL = ("eval-", "f1-trial", "calib-")
PROBE = ("selftest", "quota-probe", "probe-", "startup-probe", "e8 accept", "live-ds", "two-way", "untried",
         "discuss:", "desktop-")


def group(r):
    lab = str(r.get("label") or "").lower()
    if lab.startswith("review:"):
        parent = by_id.get(lab[len("review:"):])
        return group(parent) if parent else "eval/trial"
    cwd = (r.get("cwd") or "").replace("\\", "/").lower()
    if lab.startswith(EVAL) or "/f1-trial/" in cwd or "/ccx-7c-" in cwd:     # the 7c evaluation's unlabeled resume runs
        return "eval/trial"
    if lab.startswith(PROBE) or lab.endswith("-real") or "-real:" in lab or "-real#" in lab:
        return "probe/acceptance"
    if "/temp/" in cwd:
        return "temp dir (ad-hoc test)"
    return "real work"


def is_review(r):
    return str(r.get("label") or "").startswith("review:")


def usd(r):
    return float(r.get("ae_usd") or r.get("cost_usd") or 0)


def model(r):
    rg = r.get("rungs") or []
    return rg[-1] if rg else "?"


reviewed = {str(r["label"])[len("review:"):] for r in runs if is_review(r)}
verdict = {}
for e in events:
    if e.get("type") in ("verify", "dismiss"):
        verdict[e.get("run_id")] = e             # a run judged more than once: its last verdict counts


def summary(rs_all):
    work = [r for r in rs_all if not is_review(r)]
    revs = [r for r in rs_all if is_review(r)]
    wr = [r for r in work if r.get("mode") == "write"]
    cost = collections.defaultdict(lambda: [0, 0.0])
    for r in rs_all:
        k = ("review " if is_review(r) else "work ") + model(r)
        cost[k][0] += 1
        cost[k][1] += usd(r)
    vend = collections.defaultdict(float)
    for r in rs_all:
        for a, v in (r.get("ae_by_agent") or {r.get("to") or "?": usd(r)}).items():
            vend[a] += float(v or 0)
    v = [verdict[r["run_id"]] for r in work if r["run_id"] in verdict]
    return {
        "work_runs": len(work), "review_runs": len(revs),
        "by_day": dict(sorted(collections.Counter(
            datetime.datetime.fromtimestamp(r["ts"], TZ).strftime("%m-%d") for r in work).items())),
        "caller_to": dict(collections.Counter(f"{r.get('caller')}->{r.get('to')}" for r in work).most_common()),
        "usd": {"work": round(sum(map(usd, work)), 3), "review": round(sum(map(usd, revs)), 3)},
        "usd_by_vendor": {k: round(x, 3) for k, x in sorted(vend.items(), key=lambda y: -y[1])},
        "by_model": {k: [n, round(x, 3)] for k, (n, x) in sorted(cost.items(), key=lambda y: -y[1][1])},
        "write_runs": len(wr),
        "write_with_check": sum(bool(r.get("check")) for r in wr),
        "write_check_failed": sum((r.get("check") or {}).get("passed") is False for r in wr),
        "write_reviewed": sum(r["run_id"] in reviewed for r in wr),
        "write_check_or_review": sum(bool(r.get("check")) or r["run_id"] in reviewed for r in wr),
        "status": dict(collections.Counter(r.get("status") for r in work)),
        "kind": dict(collections.Counter(r.get("kind") for r in work)),
        "not_ok": sum(not r.get("ok") for r in work),
        "escalated": sum(int(r.get("attempts") or 1) > 1 for r in work),
        "resumed_or_fix_round": sum(int(r.get("resume_chain") or 1) > 1 or int(r.get("continue_depth") or 0) > 0
                                    for r in work),
        "permission_denial_runs": sum(bool(r.get("permission_denials")) for r in rs_all),
        "verdicts": {"judged": len(v),
                     "lead_ok": sum(e.get("type") == "verify" and bool(e.get("ok")) and not e.get("soft") for e in v),
                     "lead_wrong": sum(e.get("type") == "verify" and not e.get("ok") and not e.get("soft") for e in v),
                     "soft_ok": sum(e.get("type") == "verify" and bool(e.get("ok")) and bool(e.get("soft")) for e in v),
                     "dismissed": sum(e.get("type") == "dismiss" for e in v)},
        "lead_session_linked": sum(bool(r.get("lead_session")) for r in work),
        "median_seconds": sorted(float(r.get("seconds") or 0) for r in work)[len(work) // 2] if work else None,
        "projects": len({(r.get("cwd") or "").lower() for r in work}),
    }


groups = collections.defaultdict(list)
for r in runs:
    groups[group(r)].append(r)
selfruns = [e for e in events if e.get("type") == "selfrun"]   # ccx trial: the lead doing a task itself, for comparison
out = {"window_rows": len(inwin), "runs": len(runs),
       "selfrun": {"n": len(selfruns), "usd": round(sum(float(e.get("ae_usd") or 0) for e in selfruns), 3)},
       "verdicts_on_runs_before_window": sum(e.get("type") in ("verify", "dismiss") and e.get("run_id") not in by_id
                                              for e in events), "events": dict(collections.Counter(e.get("type") for e in events)),
       "all": summary(runs), "groups": {g: summary(rs) for g, rs in sorted(groups.items())}}
print(json.dumps(out, ensure_ascii=False, indent=1))
