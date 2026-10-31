"""External benchmark pg1 (2026-10-31): every number of docs/research/2026-10-31-polyglot-pg1.md from the result rows.

    python scripts/research/polyglot_pg1.py .ccx/eval/r5/pg1-results.jsonl --out docs/research/data/2026-10-31-polyglot-pg1.json

Read-only, standard library only, and separate from scripts/eval/r5.py (it does not import it), so the report's numbers
are a second computation next to `r5.py summary`. The output has no paths: per unit only the task, arm and the fields
the report uses. The bootstrap resamples tasks with a fixed seed (--seed, default 31), so a re-run prints the same CIs.

Two counts are reported everywhere: all 30 tasks, and the clean rows only (`env_clean`, as `r5.py summary` counts).
A pair is two arms on the same task (one round). Sign tests are exact two-sided binomial tests on the discordant pairs
(McNemar's exact test).

One input is not in the rows: FAILURE_CODES, a hand coding of each ccx2 failure from the error lines of that unit's
hidden-test output (kept beside the rows on the machine that ran it). The coding is ours; the counts built on it say so.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from math import comb
from pathlib import Path

ARMS = ("self", "ccx2", "direct")
SELECTION = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "polyglot_selection.json"

# Hand coding of the 18 ccx2 failures, from the first error lines of each unit's hidden-pytest.txt.
# interface: the code does the job but not with the shape the hidden tests expect (return type, input format, missing
# attribute or constant, error text); logic: the behaviour itself is wrong.
FAILURE_CODES = {
    "pg-book-store": ("interface", "rejects the basket format the tests pass (expects counts for five books)"),
    "pg-zipper": ("interface", "tuple trees instead of the tests' dict trees; its own test_own.py fixed that shape"),
    "pg-simple-linked-list": ("interface", "head()/pop return int where the tests expect a node with .value"),
    "pg-rest-api": ("interface", "payload taken as dict, the tests pass a JSON string"),
    "pg-dot-dsl": ("interface", "attrs default [] instead of {}; error messages differ"),
    "pg-food-chain": ("interface", "returns one string, the tests expect a list of lines; its own test_own.py fixed that"),
    "pg-grep": ("interface", "returns a list of lines, the tests expect one string"),
    "pg-grade-school": ("interface", "raises on a duplicate name, the tests expect add_student to return False"),
    "pg-go-counting": ("interface", "the module lacks the WHITE/BLACK/NONE constants the tests import"),
    "pg-phone-number": ("interface", "no .pretty() method / attributes the tests use"),
    "pg-forth": ("interface", "takes one string, the tests pass a list of lines"),
    "pg-react": ("interface", "callbacks get values spread out, the tests pass one list"),
    "pg-tree-building": ("interface", "error message text differs from the tests'"),
    "pg-pov": ("interface", "error message text differs from the tests'"),
    "pg-bowling": ("logic", "two bonus-roll validation cases not raised"),
    "pg-hangman": ("logic", "wrong guess count and status after the last miss"),
    "pg-connect": ("logic", "wrong winner on several boards"),
    "pg-paasio": ("logic", "context-manager behaviour of the wrapped object"),
}


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sign_p(a: int, b: int) -> float:
    """Exact two-sided binomial p for a vs b discordant pairs (p = 0.5)."""
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(c - h, 3), round(c + h, 3)]


def holm(ps: dict[str, float]) -> dict[str, float]:
    out, run = {}, 0.0
    for i, (k, p) in enumerate(sorted(ps.items(), key=lambda kv: kv[1])):
        run = max(run, min(1.0, p * (len(ps) - i)))
        out[k] = float(f"{run:.3g}")
    return out


def arm_stats(rows: list[dict]) -> dict:
    ok = sum(1 for r in rows if r["ok"])
    usd = sum(r["usd"] for r in rows)
    return {"ok": ok, "n": len(rows), "wilson95": wilson(ok, len(rows)), "usd": round(usd, 4),
            "cost_per_success": round(usd / ok, 4) if ok else None,
            "lead_usd": round(sum(r.get("lead_usd") or 0 for r in rows), 4),
            "ccx_usd": round(sum(r.get("ccx_usd") or 0 for r in rows), 4),
            "wall_median_s": round(statistics.median(r["wall_s"] for r in rows), 1)}


def paired(by: dict, a: str, b: str, tasks: list[str]) -> dict:
    only_a = [t for t in tasks if by[t][a]["ok"] and not by[t][b]["ok"]]
    only_b = [t for t in tasks if by[t][b]["ok"] and not by[t][a]["ok"]]
    return {"pairs": len(tasks), f"only_{a}": len(only_a), f"only_{b}": len(only_b),
            "p_exact": float(f"{sign_p(len(only_a), len(only_b)):.3g}"), f"only_{a}_tasks": only_a,
            f"only_{b}_tasks": only_b}


def boot_ci(vals: list[float], q=(0.025, 0.975)) -> list[float]:
    s = sorted(vals)
    return [round(s[int(q[0] * (len(s) - 1))], 3), round(s[int(q[1] * (len(s) - 1))], 3)]


def cost_ratios(by: dict, tasks: list[str], a: str, b: str) -> tuple[float, float | None]:
    ua = sum(by[t][a]["usd"] for t in tasks)
    ub = sum(by[t][b]["usd"] for t in tasks)
    oa = sum(by[t][a]["ok"] for t in tasks)
    ob = sum(by[t][b]["ok"] for t in tasks)
    total = ub / ua
    cps = (ub / ob) / (ua / oa) if oa and ob else None
    return total, cps


def bootstrap(by: dict, tasks: list[str], a: str, b: str, n: int, seed: int) -> dict:
    rng = random.Random(seed)
    tot, cps, skipped = [], [], 0
    for _ in range(n):
        s = [rng.choice(tasks) for _ in tasks]
        t, c = cost_ratios(by, s, a, b)
        tot.append(t)
        if c is None:
            skipped += 1
        else:
            cps.append(c)
    t0, c0 = cost_ratios(by, tasks, a, b)
    wall = [by[t][b]["wall_s"] - by[t][a]["wall_s"] for t in tasks]
    return {"pairs": len(tasks), "resamples": n, "seed": seed, "unit": "task",
            "total_ratio": round(t0, 3), "total_ratio_ci": boot_ci(tot),
            "cost_per_success_ratio": round(c0, 3), "cost_per_success_ratio_ci": boot_ci(cps),
            "resamples_without_a_success": skipped,
            f"tasks_{b}_dearer": sum(1 for t in tasks if by[t][b]["usd"] > by[t][a]["usd"]),
            f"tasks_{b}_slower": sum(1 for t in wall if t > 0),
            "wall_diff_median_s": round(statistics.median(wall), 1),
            "wall_median_diff_s": round(statistics.median(by[t][b]["wall_s"] for t in tasks)
                                        - statistics.median(by[t][a]["wall_s"] for t in tasks), 1)}


def auc(scores_pos: list[float], scores_neg: list[float]) -> float | None:
    """P(score of a positive > score of a negative), ties counted half (Mann-Whitney)."""
    if not scores_pos or not scores_neg:
        return None
    w = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in scores_pos for q in scores_neg)
    return round(w / (len(scores_pos) * len(scores_neg)), 2)


def scrub(r: dict) -> dict:
    p = r.get("phases") or {}
    return {"task": r["task"], "arm": r["arm"], "ok": r["ok"], "env_clean": r.get("env_clean"),
            "status": r.get("status") or r.get("subtype"), "usd": r["usd"], "lead_usd": r.get("lead_usd"),
            "ccx_usd": r.get("ccx_usd"), "wall_s": r["wall_s"], "hidden_failed": len(r.get("hidden_failed") or []),
            "ccx_check_passed": r.get("ccx_check_passed"), "verdicts": r.get("verdicts"),
            "rungs": [x.get("rung") for x in r.get("ccx_routes") or []],
            "attempts": p.get("n_attempts"), "reviews": p.get("n_reviews"), "fix_rounds": p.get("n_fix_rounds"),
            "lead_tools": r.get("lead_tools")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--selection", type=Path, default=SELECTION)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--resamples", type=int, default=2000)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    rows = load(a.results)
    by: dict[str, dict[str, dict]] = {}
    for r in rows:
        by.setdefault(r["task"], {})[r["arm"]] = r
    tasks = sorted(by)
    assert all(set(by[t]) == set(ARMS) for t in tasks), "every task needs one row per arm"
    sel = {t["id"]: t for t in json.loads(a.selection.read_text(encoding="utf-8"))["tasks"]}

    def clean(t, *arms):
        return all(by[t][x].get("env_clean") for x in arms)

    out: dict = {"source": a.results.name, "tasks": len(tasks), "rows": len(rows)}
    out["unclean_rows"] = [{"task": r["task"], "arm": r["arm"], "ok": r["ok"],
                            "other_processes_seen": len(r.get("between_units") or [])}
                           for r in rows if not r.get("env_clean")]
    out["arms"] = {"all": {x: arm_stats([by[t][x] for t in tasks]) for x in ARMS},
                   "clean": {x: arm_stats([by[t][x] for t in tasks if clean(t, x)]) for x in ARMS}}

    pairs = {}
    for x, y in (("self", "ccx2"), ("self", "direct"), ("direct", "ccx2")):
        pairs[f"{x} vs {y}"] = {"all": paired(by, x, y, tasks),
                                "clean": paired(by, x, y, [t for t in tasks if clean(t, x, y)])}
    for k in ("all", "clean"):
        h = holm({name: v[k]["p_exact"] for name, v in pairs.items()})
        for name in pairs:
            pairs[name][k]["p_holm3"] = h[name]
    blocked = [t for t in tasks if by[t]["direct"].get("status") == "blocked"]
    nb = [t for t in tasks if t not in blocked]
    pairs["direct vs ccx2"]["without_blocked"] = paired(by, "direct", "ccx2", nb)
    pairs["direct vs ccx2"]["without_blocked_clean"] = paired(by, "direct", "ccx2",
                                                             [t for t in nb if clean(t, "direct", "ccx2")])
    out["direct_blocked"] = [{"task": t, "wall_s": by[t]["direct"]["wall_s"]} for t in blocked]
    out["paired"] = pairs

    ct = [t for t in tasks if clean(t, "self", "ccx2")]
    out["bootstrap_ccx2_over_self"] = {"clean": bootstrap(by, ct, "self", "ccx2", a.resamples, a.seed),
                                       "all": bootstrap(by, tasks, "self", "ccx2", a.resamples, a.seed)}

    # Where ccx2's money goes: the lead's side (brief, wait, acceptance) vs ccx's runs (work + reviews).
    def lead_side(ts):
        c = [by[t]["ccx2"] for t in ts]
        lead = sum(r["lead_usd"] for r in c)
        tot = sum(r["usd"] for r in c)
        s = [by[t]["self"] for t in ts]
        return {"ccx2_lead_usd": round(lead, 4), "ccx2_usd": round(tot, 4), "lead_share": round(lead / tot, 3),
                "ccx2_lead_usd_median": round(statistics.median(r["lead_usd"] for r in c), 4),
                "self_usd_median": round(statistics.median(r["usd"] for r in s), 4),
                "tasks_ccx2_lead_alone_dearer_than_self": sum(1 for t in ts
                                                              if by[t]["ccx2"]["lead_usd"] > by[t]["self"]["usd"]),
                "of": len(ts),
                "ccx2_cost_per_success_if_all_right": round(tot / len(ts), 4),
                "self_cost_per_success": round(sum(r["usd"] for r in s) / sum(r["ok"] for r in s), 4)}
    out["lead_side"] = {"all": lead_side(tasks), "clean": lead_side(ct),
                        "fields": "lead_usd (the lead's model spend) / usd (lead_usd + ccx_usd) of the ccx2 rows; "
                                  "self's usd is its lead_usd"}

    c2 = [by[t]["ccx2"] for t in tasks]
    out["check"] = {"ccx2_check_passed": sum(1 for r in c2 if r.get("ccx_check_passed")), "of": len(c2),
                    "passed_but_hidden_failed": sum(1 for r in c2 if r.get("ccx_check_passed") and not r["ok"]),
                    "hidden_failed": sum(1 for r in c2 if not r["ok"])}
    out["routes"] = {"rungs": sorted({x for r in rows for x in scrub(r)["rungs"]}),
                     "ccx2_units_with_a_fix_round": sum(1 for r in c2 if (r.get("phases") or {}).get("n_fix_rounds")),
                     "ccx2_units_with_2_attempts": sum(1 for r in c2
                                                       if ((r.get("phases") or {}).get("n_attempts") or 0) > 1),
                     "ccx2_units_reviewed": sum(1 for r in c2 if (r.get("phases") or {}).get("n_reviews"))}
    dfail = [by[t]["direct"] for t in tasks if not by[t]["direct"]["ok"] and by[t]["direct"].get("status") != "blocked"]
    out["direct_review"] = {"failed_not_blocked": len(dfail),
                            "last_verdict_pass": sum(1 for r in dfail if (r.get("verdicts") or [None])[-1] == "pass")}

    allwrong = [t for t in tasks if not any(by[t][x]["ok"] for x in ARMS)]
    ccx2_only_fail = [t for t in tasks if by[t]["direct"]["ok"] and not by[t]["ccx2"]["ok"]]
    wins = []
    for t in pairs["direct vs ccx2"]["all"]["only_ccx2_tasks"]:
        d, c = by[t]["direct"], by[t]["ccx2"]
        p = c.get("phases") or {}
        why = ("direct blocked" if d.get("status") == "blocked" else
               "direct row unclean" if not d.get("env_clean") else
               "ccx2 retried" if (p.get("n_attempts") or 0) > 1 or p.get("n_fix_rounds") else "ccx2 first try")
        wins.append({"task": t, "why": why, "ccx2_attempts": p.get("n_attempts"),
                     "ccx2_fix_rounds": p.get("n_fix_rounds"), "direct_wall_s": d["wall_s"]})
    codes = {t: FAILURE_CODES.get(t, ("uncoded", ""))[0] for t in tasks if not by[t]["ccx2"]["ok"]}
    out["failures"] = {
        "all_three_wrong": allwrong,
        "ccx2_failed_direct_right": ccx2_only_fail,
        "ccx2_won_direct_lost": wins,
        "ccx2_failure_codes": {k: sum(1 for v in codes.values() if v == k) for k in ("interface", "logic", "uncoded")},
        "ccx2_failure_coding": {t: {"code": FAILURE_CODES[t][0], "what": FAILURE_CODES[t][1]} for t in codes
                                if t in FAILURE_CODES},
        "coding_is": "hand coding of the hidden-test error lines (FAILURE_CODES), not a field of the rows",
        "direct_ccx2_clean_pairs_opposite": (lambda c: {"opposite": sum(1 for t in c if by[t]["direct"]["ok"]
                                                                         != by[t]["ccx2"]["ok"]), "of": len(c)})(
            [t for t in tasks if clean(t, "direct", "ccx2")]),
    }
    s_rows = [by[t]["self"] for t in tasks]
    out["self_right_without_bash"] = {
        "count": sum(1 for r in s_rows if r["ok"] and not (r.get("lead_tools") or {}).get("Bash")),
        "tasks": [r["task"] for r in s_rows if r["ok"] and not (r.get("lead_tools") or {}).get("Bash")],
        "fields": "lead_tools has no Bash: the lead never ran a command (a Bash call that only wrote a file still counts "
                  "as Bash here)"}

    # Pre-delegation features vs ccx2 failing (AUC > 0.5: a higher value goes with failing).
    feats = {}
    for f in ("exercism_difficulty", "tests", "instruction_chars"):
        feats[f] = {"ccx2_fails": auc([sel[t][f] for t in tasks if not by[t]["ccx2"]["ok"]],
                                      [sel[t][f] for t in tasks if by[t]["ccx2"]["ok"]]),
                    "direct_fails": auc([sel[t][f] for t in tasks if not by[t]["direct"]["ok"]],
                                        [sel[t][f] for t in tasks if by[t]["direct"]["ok"]])}
    out["feature_auc"] = {"by_feature": feats, "in_sample": True,
                          "from": "scripts/eval/polyglot_selection.json (difficulty, tests, instruction_chars)"}
    out["units"] = [scrub(by[t][x]) for t in tasks for x in ARMS]

    text = json.dumps(out, indent=1, ensure_ascii=False)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
