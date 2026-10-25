"""Where ccx was wrong (core 6, "more accurate with use"; H14): the signals routing learns from, checked against
the verdicts of the person or the lead, this week next to last week. Shown as one section of `ccx report`.

- per tier x kind of work: how often a judged piece was wrong, and how often it needed rework (ways.pieces);
- the routing prediction: Brier score of `p` (the chance routing gave the picked rung to do it) against what
  happened (judged right and done by that rung, no escalation), and a binned calibration;
- probable verdicts (soft) later judged the other way;
- acceptance commands that let wrong work through (J7, all time).

Evaluation runs (ledger.is_eval) are left out: they measure ccx, not the person's work."""
from __future__ import annotations

import html
import time

from . import ledger
from .config import Paths

WEEK = 7 * 86400
BINS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.0001))


def _week(ts: float | None, now: float) -> str | None:
    age = now - float(ts or 0)
    return "this" if 0 <= age < WEEK else "last" if WEEK <= age < 2 * WEEK else None


def _rate(a: int, n: int) -> float | None:
    return round(a / n, 3) if n else None


def tiers(pieces: list[dict], now: float) -> list[dict]:
    """(agent, tier, kind) -> judged, wrong and rework rates per week."""
    agg: dict[tuple, dict] = {}
    for x in pieces:
        w = _week(x.get("ts"), now)
        if not w or not x.get("judged"):
            continue
        g = agg.setdefault((x["agent"], x["tier"], x["kind"]), {"this": [0, 0, 0], "last": [0, 0, 0]})[w]
        g[0] += 1
        g[1] += not x.get("ok")
        g[2] += bool(x.get("rework"))
    out = []
    for (agent, tier, kind), g in sorted(agg.items()):
        out.append({"agent": agent, "tier": tier, "kind": kind,
                    **{w: {"judged": g[w][0], "wrong": _rate(g[w][1], g[w][0]), "rework": _rate(g[w][2], g[w][0])}
                       for w in ("this", "last")}})
    return out


def calibration(pieces: list[dict], now: float) -> dict:
    """Brier score and bins of routing's `p` per week. Outcome: judged right and done by the picked rung."""
    out = {}
    for w in ("this", "last"):
        xs = [(float(x["p"]), 1.0 if x.get("ok") and x.get("attempts", 1) <= 1 else 0.0) for x in pieces
              if x.get("judged") and x.get("p") is not None and _week(x.get("ts"), now) == w]
        bins = []
        for lo, hi in BINS:
            b = [(p, y) for p, y in xs if lo <= p < hi]
            if b:
                bins.append({"bin": f"{lo:.2f}-{min(hi, 1):.2f}", "n": len(b),
                             "predicted": round(sum(p for p, _ in b) / len(b), 3),
                             "actual": round(sum(y for _, y in b) / len(b), 3)})
        out[w] = {"n": len(xs), "brier": round(sum((p - y) ** 2 for p, y in xs) / len(xs), 4) if xs else None,
                  "bins": bins}
    return out


def overturned(rows: list[dict], now: float, include_evals: bool = False) -> dict:
    """Probable verdicts judged the other way later, by the week of the later verdict (evaluations left out)."""
    runs = ledger.runs_by_id(rows)
    soft: dict[str, bool] = {}
    out = {"this": [0, 0], "last": [0, 0]}
    for r in rows:
        if r.get("type") != "verify" or not r.get("run_id") or (not include_evals and ledger.is_eval(r, runs)):
            continue
        if r.get("soft"):
            soft.setdefault(r["run_id"], bool(r.get("ok")))
        elif r["run_id"] in soft:
            was = soft.pop(r["run_id"])
            w = _week(r.get("ts"), now)
            if w:
                out[w][0] += 1
                out[w][1] += bool(r.get("ok")) != was
    return {w: {"rechecked": n, "overturned": k, "rate": _rate(k, n)} for w, (n, k) in out.items()}


def summary(p: Paths, rows: list[dict] | None = None, now: float | None = None, include_evals: bool = False) -> dict:
    from . import ways
    now = now or time.time()
    rows = ledger.rows(p) if rows is None else rows
    pcs = ways.pieces(p, days=14, include_evals=include_evals)
    groups = ledger.check_trust(rows, p)
    weak = sorted((g for g in groups.values() if g["weak"]), key=lambda g: (-g["wrong"], g["place"]))
    return {"tiers": tiers(pcs, now), "calibration": calibration(pcs, now), "soft": overturned(rows, now, include_evals),
            "evals": include_evals,
            "checks": {"judged": sum(g["judged"] for g in groups.values()),
                       "wrong": sum(g["wrong"] for g in groups.values()),
                       "weak": [{k: g[k] for k in ("cmd", "place", "judged", "wrong", "wrong_rate")} for g in weak]}}


def _esc(s) -> str:
    return html.escape(str(s))


def _pct(v) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def _weeks_html(acc: dict) -> str:
    rows = "".join(
        f'<tr><td>{_esc(t["agent"])}</td><td>{_esc(t["tier"])}</td><td>{_esc(t["kind"])}</td>'
        + "".join(f'<td class="r">{t[w]["judged"] or "–"}</td><td class="r">{_pct(t[w]["wrong"])}</td>'
                  f'<td class="r">{_pct(t[w]["rework"])}</td>' for w in ("this", "last")) + "</tr>"
        for t in acc["tiers"])
    tiers_html = (f'<table class="tbl"><tr><th>agent</th><th>tier</th><th>kind</th><th class="r">judged</th>'
                  f'<th class="r">wrong</th><th class="r">rework</th><th class="r">last wk judged</th>'
                  f'<th class="r">wrong</th><th class="r">rework</th></tr>{rows}</table>') if rows else \
        '<p class="note">No judged pieces in the last two weeks (evaluation runs left out).</p>'
    cal = acc["calibration"]
    brier = " · ".join(f'{w} week: {cal[w]["brier"] if cal[w]["brier"] is not None else "–"} (n={cal[w]["n"]})'
                       for w in ("this", "last"))
    bins = "".join(f'<tr><td>{w}</td><td>{_esc(b["bin"])}</td><td class="r">{b["n"]}</td>'
                   f'<td class="r">{_pct(b["predicted"])}</td><td class="r">{_pct(b["actual"])}</td></tr>'
                   for w in ("this", "last") for b in cal[w]["bins"])
    bins_html = (f'<table class="tbl"><tr><th>week</th><th>predicted p</th><th class="r">n</th>'
                 f'<th class="r">mean predicted</th><th class="r">actually right</th></tr>{bins}</table>') if bins else ""
    so = acc["soft"]
    soft = " · ".join(f'{w} week: {so[w]["overturned"]}/{so[w]["rechecked"]} ({_pct(so[w]["rate"])})'
                      for w in ("this", "last"))
    return (f'<h3>By tier and kind of work</h3>{tiers_html}'
            f'<h3>Routing prediction</h3><p class="sub">Brier score (0 is perfect, 0.25 is a coin flip): {brier}. '
            f'Right = judged right and done by the rung routing picked.</p>{bins_html}'
            f'<h3>Probable verdicts overturned later</h3><p class="sub">{soft}</p>')


def card_html(acc: dict | None) -> str:
    if not acc:
        return ""
    ch = acc["checks"]
    rows = "".join(f'<tr><td><code>{_esc(g["cmd"])}</code></td><td>{_esc(g["place"])}</td>'
                   f'<td class="r">{g["wrong"]}/{g["judged"]}</td></tr>' for g in ch["weak"])
    weak = (f'<table class="tbl"><tr><th>acceptance command</th><th>where</th><th class="r">passed but judged wrong'
            f'</th></tr>{rows}</table><p class="note">These commands have let wrong work through: their pass no longer '
            f'counts as a probable verdict, and the run result says so. Look at the change, or make the check '
            f'test what the task asks.</p>') if ch["weak"] else \
        '<p class="note">No acceptance command has let wrong work through more than '\
        f'{ledger.CHECK_MAX_WRONG:.0%} of the time (of {ledger.CHECK_MIN_JUDGED}+ judged).</p>'
    checks = (f'<h3>Acceptance checks</h3><p class="sub">{ch["wrong"]} of {ch["judged"]} judged runs passed ccx\'s '
              f'check and were still wrong (all time, evaluations included).</p>{weak}') if ch["judged"] else ""
    weeks = _weeks_html(acc) if "tiers" in acc else ""
    ev = ("evaluation runs included" if acc.get("evals") else
          "evaluation runs left out (`ccx report --include-evals` to count them)")
    return (f'<div class="card"><h2>Where it was wrong — this week vs last week</h2><p class="note">{ev}</p>'
            f'{weeks}{checks}</div>'
            if weeks or checks else "")
