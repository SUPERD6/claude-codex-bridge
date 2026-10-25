"""Where ccx was wrong (core 6, "more accurate with use"): the signals routing learns from, checked against the
verdicts of the person or the lead. Shown as one section of `ccx report`."""
from __future__ import annotations

import html

from . import ledger
from .config import Paths


def summary(p: Paths, rows: list[dict] | None = None) -> dict:
    rows = ledger.rows(p) if rows is None else rows
    groups = ledger.check_trust(rows, p)
    weak = sorted((g for g in groups.values() if g["weak"]), key=lambda g: (-g["wrong"], g["place"]))
    return {"checks": {"judged": sum(g["judged"] for g in groups.values()),
                       "wrong": sum(g["wrong"] for g in groups.values()),
                       "weak": [{k: g[k] for k in ("cmd", "place", "judged", "wrong", "wrong_rate")} for g in weak]}}


def _esc(s) -> str:
    return html.escape(str(s))


def card_html(acc: dict | None) -> str:
    if not acc:
        return ""
    ch = acc["checks"]
    if not ch["judged"]:
        return ""
    rows = "".join(f'<tr><td><code>{_esc(g["cmd"])}</code></td><td>{_esc(g["place"])}</td>'
                   f'<td class="r">{g["wrong"]}/{g["judged"]}</td></tr>' for g in ch["weak"])
    weak = (f'<table class="tbl"><tr><th>acceptance command</th><th>where</th><th class="r">passed but judged wrong'
            f'</th></tr>{rows}</table><p class="note">These commands have let wrong work through: their pass no longer '
            f'counts as a probable verdict, and the run result says so. Look at the change, or make the check '
            f'test what the task asks.</p>') if ch["weak"] else \
        '<p class="note">No acceptance command has let wrong work through more than '\
        f'{ledger.CHECK_MAX_WRONG:.0%} of the time (of {ledger.CHECK_MIN_JUDGED}+ judged).</p>'
    return (f'<div class="card"><h2>Where it was wrong</h2><p class="sub">Acceptance checks: {ch["wrong"]} of '
            f'{ch["judged"]} judged runs passed ccx\'s check and were still wrong.</p>{weak}</div>')
