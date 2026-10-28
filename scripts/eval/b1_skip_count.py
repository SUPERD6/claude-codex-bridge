"""B1 pre-count: how often is `unsure` or `tests_miss_change` the ONLY reason a write run was reviewed? Offline, $0.

The improvement plan's B1 (`[review] skip`, default off) may skip a review whose reason is `unsure` (the sub-agent
listed open questions) or `tests_miss_change` (the check's tests never name a changed file or function), but a
skipped reason must fall through to the remaining triggers. Its gate: the share of first reviews where one of these
two is the only trigger; below about 5% the item is dropped.

ccx records only the first reason that fired (record.review.reason), in the order of ccx/review.py: asked, risk,
>= min_lines changed code lines, unsure, claimed files don't match, no files reported; then (auto mode only, when
none of those fired) the weak-evidence reasons: existing tests edited, weak history, no acceptance command, a
command running no tests, tests_miss_change. So:

  tests_miss_change  is the last trigger; when it is the recorded reason nothing else fired: sole by construction
  unsure             the later triggers still have to be checked: files mismatch / none reported (from the run's
                     claimed files against the files of the diff the reviewer got), edited tests (the record's
                     review.edited_tests), no check, and check_gap on the tree the reviewer saw (rebuilt by
                     c1_namecheck_scan.py --reviewed into --trees); without that tree the row is `unknown`

The weak-review daily cap (`weak_daily`, 20) is not modelled: a later trigger counted here could have been capped.

  python scripts/eval/b1_skip_count.py [--records <dir>] [--trees <c1 --reviewed folder>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import offline_common as oc  # noqa: E402

CODES = (("asked", r"^asked$"), ("risk", r"^risk "), ("lines", r"^\d+ changed code lines"),
         ("unsure", r"sub-agent is unsure"), ("files_mismatch", r"claimed files don't match"),
         ("no_files", r"reported no files"), ("edited_tests", r"^existing tests edited"),
         ("weak_history", r"^weak check"), ("no_check", r"only the sub-agent's own check|no acceptance command"),
         ("check_no_tests", r"runs no tests|found no test files"), ("tests_miss_change", r"tests it runs don't touch"))
SKIPPABLE = ("unsure", "tests_miss_change")


def code(reason: str) -> str:
    """The stable code of a recorded review reason (the text ccx/review.py writes)."""
    for c, rx in CODES:
        if re.search(rx, reason or ""):
            return c
    return "other"


def diff_files(diff: str) -> list[str]:
    return [ln[6:].strip() for ln in diff.splitlines() if ln.startswith("+++ b/")]


def later_trigger(rec: dict, diff: str, tree: Path | None) -> str | None:
    """The first trigger after `unsure` that would still fire for this run: a code, None (none would), or
    'unknown' (check_gap needs the reviewed tree and it is not there)."""
    from ccx import review
    actual = diff_files(diff)
    claimed = (rec.get("result") or {}).get("files_changed") or []
    a, c = {review._norm(f) for f in actual}, {review._norm(f) for f in claimed}
    if c and not any(x.endswith(y) or y.endswith(x) for x in a for y in c):
        return "files_mismatch"
    if not c:
        return "no_files"
    if (rec.get("review") or {}).get("edited_tests"):
        return "edited_tests"
    chk = rec.get("check") or {}
    if not chk.get("cmd"):
        return "no_check"
    if tree is None or not tree.is_dir():
        return "unknown"
    why = review.check_gap(chk["cmd"], tree, actual, diff)
    return None if not why else "check_no_tests" if "no test" in why else "tests_miss_change"


def rows(base: Path, tags, trees: Path | None) -> list[dict]:
    import review_replay as RR
    out = []
    for tag in tags:
        for f in sorted((Path(base) / tag).glob("h-*/ccx/runs/*/run.json")):
            try:
                r = oc.load(f)
            except (OSError, ValueError):
                continue
            rv = r.get("review") or {}
            if r.get("caller") == "ccx-review" or not rv.get("run_id"):
                continue
            unit = f.parents[3].name.removeprefix("h-")
            row = {"tag": tag, "unit": unit, "run_id": r.get("run_id"), "review_id": rv["run_id"],
                   "fix_round": bool(r.get("resumed_from") or r.get("review_of")), "code": code(rv.get("reason")),
                   "verdict": rv.get("verdict"), "usd": rv.get("usd") or 0, "later": None}
            if row["code"] == "unsure":
                d = f.parent.parent / rv["run_id"]
                try:
                    diff = RR.parse_brief((d / "brief.md").read_text(encoding="utf-8"))["diff"]
                except (OSError, ValueError):
                    diff = ""
                tree = trees / f"{tag}-{unit}-{rv['run_id']}" if trees else None
                row["later"] = later_trigger(r, diff, tree)
            out.append(row)
    return out


def summarize(rs: list[dict]) -> dict:
    out = {}
    for name, sel in (("first", [r for r in rs if not r["fix_round"]]), ("all", rs)):
        auto = [r for r in sel if r["code"] != "asked"]
        sole = {"tests_miss_change": sum(r["code"] == "tests_miss_change" for r in sel),
                "unsure": sum(r["code"] == "unsure" and r["later"] is None for r in sel),
                "unsure_unknown": sum(r["code"] == "unsure" and r["later"] == "unknown" for r in sel)}
        n_sole = sole["tests_miss_change"] + sole["unsure"]
        out[name] = {"reviews": len(sel), "auto_reviews": len(auto),
                     "by_code": {c: sum(r["code"] == c for r in sel) for c in sorted({r["code"] for r in sel})},
                     "sole": sole,
                     "unsure_later": {k: sum(r["code"] == "unsure" and str(r["later"]) == k for r in sel)
                                      for k in sorted({str(r["later"]) for r in sel if r["code"] == "unsure"})},
                     "sole_share": round(n_sole / len(sel), 3) if sel else None,
                     "sole_share_auto": round(n_sole / len(auto), 3) if auto else None,
                     "unsure_sole_share": round(sole["unsure"] / len(sel), 3) if sel else None,
                     "sole_usd": round(sum(r["usd"] for r in sel if r["code"] == "tests_miss_change"
                                           or (r["code"] == "unsure" and r["later"] is None)), 4)}
    return out


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="", help="folder holding the round folders (default: temp_root())")
    ap.add_argument("--tags", default=",".join(oc.TAGS), type=lambda x: [t for t in x.split(",") if t])
    ap.add_argument("--trees", default="", help="c1_namecheck_scan.py --reviewed folder (reviewed trees)")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    rs = rows(Path(a.records) if a.records else oc.temp_root(), a.tags, Path(a.trees) if a.trees else None)
    if not rs:
        raise SystemExit("no reviewed write runs found: check --records / CCX_REPLAY_RECORDS and --tags")
    s = summarize(rs)
    print(json.dumps(s, indent=1))
    for r in rs:
        if r["code"] == "unsure":
            print(f"  unsure {r['tag']}/{r['unit']} {r['run_id']} fix_round={r['fix_round']} later={r['later']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": s, "rows": rs}, indent=1), encoding="utf-8")
    return {"summary": s, "rows": rs}


if __name__ == "__main__":
    main()
