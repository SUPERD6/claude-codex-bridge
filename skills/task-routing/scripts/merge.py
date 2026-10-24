"""Turn public benchmark scores into rung abilities (theta), one estimate per benchmark, merged.

For each benchmark: match its rows to routing rungs (same model family, version and reasoning effort), fit a line
score -> theta on the rungs whose hand-set prior is known (the anchors), and read every rung's theta off that
line. The per-benchmark estimates are combined with weights = relevance for the kind of task / squared fit error,
halved when the version or the effort does not match, with no benchmark above half the total. The result is then
blended with the hand-set prior (which keeps a say where benchmarks are thin), and learned offsets apply on top.

Standard library only; works on the cache written by benchmarks.py. Everything is a starting point to be checked
against recorded outcomes, not a measurement of our own tasks."""
from __future__ import annotations

import math
import re

EFFORTS = ("max", "xhigh", "high", "medium", "low", "minimal", "none")
_EFFORT_RE = re.compile(r"(?:^|[\s_(\-,]+)(max|x-?high|high|medium|low|minimal|none|unknown)\b", re.I)
DEFAULTS = {
    # theta change relative to max effort. Hand-set round numbers (larger drops at lower effort); refit when local
    # outcomes per effort accumulate.
    "effort_shift": {"max": 0.0, "xhigh": -0.3, "high": -0.8, "medium": -1.5, "low": -2.8, "minimal": -3.5,
                     "none": -3.5},
    "min_anchors": 4,
    "cap": 0.5,                 # no benchmark carries more than half the weight
    "mismatch": 0.5,            # weight factor when version or effort differs from the rung
    "prior_sd": 1.5,            # how much the hand-set prior still counts
    "kinds": {
        "code": {"frontiercode": 3, "swe_bench_verified": 2, "terminal_bench": 2,
                 "lmarena_agent_task_outcome_explicit": 1.5, "lmarena_agent_bash_reliability": 1, "eci": 2,
                 "webdev_arena": 0.5, "gpqa_diamond": 0.5},
        "read": {"eci": 3, "gpqa_diamond": 2, "hle": 1, "frontiercode": 1, "lmarena_text": 1.5},
        "research": {"simpleqa_verified": 3, "lmarena_text_factuality": 2, "lmarena_search_factuality": 1,
                     "eci": 2, "gpqa_diamond": 1},
        "write": {"lmarena_text": 3, "eci": 2, "simpleqa_verified": 1},
    },
}


def split_name(name: str) -> tuple[str, str]:
    """'claude-haiku-5-5_max' / 'Claude Haiku 5.5 (High)' / 'DeepSeek-V4-Pro (High, 20260813)'
    -> (compact family with any version digits, effort or '')."""
    s = name or ""
    effort = ""
    m = _EFFORT_RE.search(s)
    if m:
        effort = m.group(1).lower().replace("-", "")
        effort = "" if effort == "unknown" else effort
        s = s[:m.start()] + " " + s[m.end():]
    return re.sub(r"[^a-z0-9]", "", s.lower()), effort


def _family_weight(family: str, patterns: list) -> float | None:
    for pat, w in patterns:
        if re.fullmatch(pat, family):
            return float(w)
    return None


def _fit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    sd = math.sqrt(sum(r * r for r in res) / max(1, n - 2)) if n > 2 else 1.0
    return a, b, max(sd, 0.25)


def rung_rows(scores: list[dict], rungs: list[dict], aliases: dict) -> dict:
    """(benchmark, rung key) -> (row, match weight, row effort, version weight) for the best matching row."""
    out = {}
    for row in scores:
        fam, eff = split_name(row.get("model") or row.get("display") or "")
        row_eff = (row.get("effort") or "").lower().replace("-", "") or eff or "max"   # no effort given: best setting
        for r in rungs:
            pats = aliases.get(r["model"])
            if not pats:
                continue
            vw = _family_weight(fam, pats)
            if vw is None:
                continue
            w = vw * (1.0 if row_eff == r["effort"] else DEFAULTS["mismatch"])
            key = (row["benchmark"], f"{r['agent']}:{r['model']}:{r['effort']}")
            if key not in out or w > out[key][1]:
                out[key] = (row, w, row_eff, vw)
    return out


def merged_thetas(scores: list[dict], rungs: list[dict], aliases: dict, kind: str = "code",
                  cfg: dict | None = None, anchor_agents: tuple = ("claude", "codex")) -> dict:
    """rung key -> {"theta", "sd", "prior", "bench_theta", "used": [(benchmark, weight)]}; rungs no benchmark covers
    keep their prior."""
    c = {**DEFAULTS, **(cfg or {})}
    shift = {**DEFAULTS["effort_shift"], **(c.get("effort_shift") or {})}
    rel = (c.get("kinds") or DEFAULTS["kinds"]).get(kind) or DEFAULTS["kinds"]["code"]
    rows = rung_rows([s for s in scores if s["benchmark"] in rel], rungs, aliases)
    keyed = {f"{r['agent']}:{r['model']}:{r['effort']}": r for r in rungs}
    per_bench: dict[str, dict] = {}
    for bench in rel:
        pts = [(k, row, w, re_, vw) for (b, k), (row, w, re_, vw) in rows.items() if b == bench]
        # anchors: the exact model version; a different effort is moved onto the row's effort with the shift table
        anchors = [(row["score"], keyed[k]["theta"] + shift.get(re_, 0) - shift.get(keyed[k]["effort"], 0))
                   for k, row, w, re_, vw in pts if vw >= 1.0 and keyed[k]["agent"] in anchor_agents]
        if len(anchors) < c["min_anchors"]:
            continue
        fit = _fit([x for x, _ in anchors], [y for _, y in anchors])
        if not fit or fit[1] <= 0:
            continue                        # a benchmark that doesn't rise with ability tells us nothing here
        a, b, sd = fit
        for k, row, w, re_, vw in pts:
            th = a + b * row["score"] + shift.get(keyed[k]["effort"], 0) - shift.get(re_, 0)
            per_bench.setdefault(k, {})[bench] = (th, w * rel[bench] / sd ** 2, sd)
    out = {}
    for k, r in keyed.items():
        est = per_bench.get(k) or {}
        prior = r["theta"]
        if not est:
            out[k] = {"theta": prior, "sd": c["prior_sd"], "prior": prior, "bench_theta": None, "used": []}
            continue
        total = sum(w for _, w, _ in est.values())
        cap = c["cap"] * total if len(est) > 1 else total
        ws = {b: min(w, cap) for b, (_, w, _) in est.items()}
        wsum = sum(ws.values())
        bt = sum(est[b][0] * ws[b] for b in est) / wsum
        bsd = math.sqrt(sum((ws[b] / wsum) ** 2 * est[b][2] ** 2 for b in est))
        pw, bw = 1 / c["prior_sd"] ** 2, 1 / bsd ** 2
        theta = (prior * pw + bt * bw) / (pw + bw)
        out[k] = {"theta": round(theta, 2), "sd": round(math.sqrt(1 / (pw + bw)), 2), "prior": prior,
                  "bench_theta": round(bt, 2), "used": sorted(((b, round(ws[b] / wsum, 2)) for b in est),
                                                              key=lambda x: -x[1])}
    return out
