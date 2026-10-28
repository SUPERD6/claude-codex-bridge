"""C6: would a review rule "reuse the constants/helpers the code base already has" have caught r5e:2 quota-stop-log?

The unit failed its hidden test because the builder defined its own `QUOTA_HINTS` list in ccx/quota.py instead of
using the one ccx already classifies quota stops with (`ccx/runners.py: QUOTA_HINTS`), so a stop that ccx took for
a quota stop could get evidence `{"by": "unknown"}`. Its first-round review (haiku low) did not name it.

This replays that one review on the tree the reviewer saw (review_replay.py rebuilds it), with today's reviewer
brief (`base`) and the same brief plus one rule (`rule`), --reps times each, through the real review path (claude
haiku low, round-5 clean room). It spends real money: about $0.01-0.03 a review; --budget caps it (default $0.5).

  python scripts/eval/c6_reuse_rule.py --dry-run          # the case and the cost estimate, nothing run
  python scripts/eval/c6_reuse_rule.py --reps 3 --out c6.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_replay as RR  # noqa: E402

CASE = ("r5e", "h-2-quota-stop-log-ccx2", "20261026-074042-e6a7")
ANCHOR = "A [must] without such a basis is treated as a note."
RULE = ("(e) a constant, list or helper the change defines anew although the code base already has one for the "
        "same purpose (search for the name and for its values): name the existing one with file:line, since the "
        "two will disagree. ")
EST_USD = 0.03                  # one haiku low review, with a margin (round 5: $0.009 for this one)


def found(item: str) -> bool:
    """The item names the duplicate: runners' QUOTA_HINTS (or 'the existing hint list') against the new one."""
    t = item.lower()
    return "quota_hints" in t and ("runners" in t or "existing" in t or "duplicat" in t or "already" in t)


def score(results: list[dict]) -> dict:
    out = {}
    for v in ("base", "rule"):
        rs = [r for r in results if r.get("variant") == v and r.get("ok")
              and (v != "rule" or r.get("inserted", True))]          # a rule row without the rule is no rule row
        out[v] = {"n": len(rs), "must": sum(any(found(x) for x in r.get("musts") or []) for r in rs),
                  "any": sum(any(found(x) for x in r.get("items") or []) for r in rs),
                  "usd": round(sum(r.get("usd") or 0 for r in rs), 4)}
    return out


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--budget", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--work", default="")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    d = RR.temp_root() / CASE[0] / CASE[1] / "ccx" / "runs" / CASE[2]
    jobs = [(v, r) for r in range(a.reps) for v in (("base", "rule") if r % 2 else ("rule", "base"))]
    plan = {"case": str(d), "exists": d.is_dir(), "reviews": len(jobs), "est_usd": round(len(jobs) * EST_USD, 2),
            "budget": a.budget}
    print(json.dumps(plan))
    if a.dry_run or not d.is_dir():
        return plan
    if plan["est_usd"] > a.budget:
        raise SystemExit(f"estimate ${plan['est_usd']} is over the budget ${a.budget}")
    work = Path(a.work or tempfile.mkdtemp(prefix="c6-")).resolve()
    c = RR.prepare_case({"id": "quota-stop-log", "dir": str(d), "known": "c6"}, work)
    if c.get("skip"):
        raise SystemExit(c["skip"])
    results, spent = [], 0.0
    for v, r in jobs:
        if spent + EST_USD > a.budget:
            break
        extra = {"variant": "new", **({"insert": [[ANCHOR, RULE]]} if v == "rule" else {})}   # today's brief
        res = RR.run_job(c, v, r, {"base": RR.ROOT, "rule": RR.ROOT}, work, a.timeout, extra)
        res["variant"] = v
        spent += res.get("usd") or 0
        results.append(res)
        print(f"{v} {r}: ok={res.get('ok')} ${res.get('usd') or 0:.4f} musts={len(res.get('musts') or [])} "
              f"found={any(found(x) for x in res.get('items') or [])}", file=sys.stderr)
    out = {**plan, "spent": round(spent, 4), "score": score(results), "results": results}
    print(json.dumps(out["score"]))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
