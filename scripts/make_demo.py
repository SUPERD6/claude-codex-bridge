"""Regenerate docs/assets/demo.svg: a 15-second animated terminal, "hand-off -> receipt".

    python scripts/make_demo.py

The story: `ccx route` picks a model, `ccx run --to codex` does the task in one attempt, the receipt (what it cost,
The story: `ccx route` picks a model, `ccx run --to codex` does the task in one attempt, the receipt (what it cost,
the check ccx ran again itself, who reviewed the diff), and `ccx ui` showing the same receipt on its page. The
numbers are real ccx output (laid out as a receipt; the card is drawn after the page), run against the stand-in CLIs
in tests/fakes with a throwaway hub and git repository: the check is a real `python -m unittest` on the files the
stand-in wrote, the review is the stand-in Claude's. So it can be re-made at any time without spending tokens; the
numbers are the stand-ins', and the frame says so. Needs git."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"
OUT = ROOT / "docs" / "assets" / "demo.svg"
TASK = "Add slugify() with a test"
CHECK = "python -m unittest -q"
# what the stand-in Codex writes: a helper and its test, so the check ccx runs is a real one
WRITE = ("slug.py=import re\n\n\ndef slugify(s):\n    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')\n"
         ";test_slug.py=import unittest\n\nfrom slug import slugify\n\n\nclass T(unittest.TestCase):\n"
         "    def test_slugify(self):\n        self.assertEqual(slugify('Hello, World!'), 'hello-world')\n")


def session() -> dict:
    """Run route -> run -> verify on the stand-ins; return what the frames show."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        for sub in ("hub", "codex", "claude", "work"):
            (t / sub).mkdir()
        work = t / "work"
        (work / "README.md").write_text("# my-project\n", encoding="utf-8")
        g = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "-c", "commit.gpgsign=false"]
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "start"]):
            subprocess.run([*g, *args], cwd=work, check=True, capture_output=True)
        env = {**os.environ, "CCX_HUB": str(t / "hub"), "CODEX_HOME": str(t / "codex"),
               "CLAUDE_CONFIG_DIR": str(t / "claude"), "CCX_CONFIG": str(t / "cfg.toml"),
               "CCX_CODEX_BIN": str(FAKES / "fake_codex.py"), "CCX_CLAUDE_BIN": str(FAKES / "fake_claude.py"),
               "CCX_AB_RATE": "0", "CCX_NO_BENCH_REFRESH": "1", "CCX_NO_QUOTA_PROBE": "1", "PYTHONUTF8": "1",
               "FAKE_WRITE": WRITE, "FAKE_REVIEW": "pass", "FAKE_SUMMARY": "slugify() in slug.py, with a test",
               "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}
        for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CCX_DEPTH", "CCX_ROLE", "CCX_LEAD_SESSION"):
            env.pop(k, None)

        def ccx(*args: str) -> dict:
            r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), *args], cwd=work, env=env,
                               capture_output=True, text=True, encoding="utf-8")
            if r.returncode not in (0, 2):
                raise SystemExit(f"ccx {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
            return json.loads(r.stdout)

        ccx("init")
        route = ccx("route", "--to", "codex", "--b", "2")
        run = ccx("run", "--from", "claude", "--to", "codex", "--b", "2", "--mode", "write", "--check", CHECK, "--review", "on",
                  TASK)
        rec = json.loads((t / "hub" / "ccx" / "runs" / run["run_id"] / "run.json").read_text(encoding="utf-8"))
        ccx("verify", run["run_id"], "--ok", "1")
        wrote = (work / "test_slug.py").is_file()   # the check ran a real test (0 tests also exit 0 on Python 3.11)
    cost = re.search(r"cost=~?\$([0-9.]+)", run.get("recap") or "")
    if not (wrote and cost and run.get("ok") and (run.get("check") or {}).get("passed")
            and (run.get("review") or {}).get("verdict") == "pass" and ":" in (run["review"].get("by") or "")):
        raise SystemExit(f"the stand-in run did not finish clean: {run.get('recap')}")
    return {"route": route, "run": run, "rec": rec, "cost": float(cost.group(1))}


def lines(s: dict) -> list[tuple[str, str]]:
    """[(kind, text)]: cmd | out | ok | dim | gap | card (the ccx ui card, drawn below the last line)."""
    route, run, rec = s["route"], s["run"], s["rec"]
    a = rec["attempts"][-1]
    rv, ck = run["review"], run["check"]
    who = rv["by"].replace(":", " ")
    n = len(rec["attempts"])
    return [
        ("cmd", "ccx route --to codex --b 2"),
        ("out", f"  {route['rung']}   likely to finish {route['p']:.0%}"),
        ("gap", ""),
        ("cmd", f'ccx run --to codex --b 2 --check "{CHECK}" --review on "{TASK}"'),
        ("out", f"  claude → codex  {a['model']} {a['effort']} · {n} attempt{'s' if n > 1 else ''} · {run['status']}"),
        ("dim", "  receipt"),
        ("ok", f"    check    {ck['cmd']}  rerun by ccx: {'passed' if ck['passed'] else 'FAILED'}"),
        ("ok", f"    review   {who} (another vendor): {rv['verdict']}"),
        ("out", f"    cost     ${s['cost']:.4f} (stand-in price), review included · undo: ccx undo <run>"),
        ("gap", ""),
        ("cmd", "ccx ui"),
        ("card", ""),
    ]


def svg(rows_in: list[tuple[str, str]], s: dict) -> str:
    W, top, step, per, hold = 920, 74, 26, 0.85, 6.5     # px; seconds a line; seconds the full screen stays (~15 s)
    color = {"cmd": "#d9dee5", "out": "#aab3bf", "ok": "#58c27a", "dim": "#7f8996", "gap": "#aab3bf"}
    shown = [k for k, _ in rows_in if k != "gap"]
    card_h = 118
    H = top + step * (len(rows_in) - 1) + card_h + 10
    total = per * len(shown) + hold
    out, n = [], 0

    def keyframes(cls: str) -> str:
        start = per * n / total * 100
        return f'<style>@keyframes {cls}{{0%,{start:.2f}%{{opacity:0}}{start + 0.5:.2f}%,97%{{opacity:1}}100%{{opacity:0}}}}</style>'

    for i, (kind, text) in enumerate(rows_in):
        if kind == "gap":
            continue
        y = top + i * step
        if kind == "card":                             # ccx ui: the run's card, as the page shows it
            run, rec = s["run"], s["rec"]
            a = rec["attempts"][-1]
            x0, y0, cw = 28, y - 16, 560
            rv = run["review"]["by"].split(":")
            out.append(f'<g style="animation-name:c{n}">'
                       f'<rect x="{x0}" y="{y0}" width="{cw}" height="{card_h - 12}" rx="8" fill="#f6f7f9" stroke="#d8dce3"/>'
                       f'<text class="ui" x="{x0 + 16}" y="{y0 + 26}" font-weight="700" fill="#1c2129">{escape(TASK)}</text>'
                       f'<text class="ui" x="{x0 + cw - 16}" y="{y0 + 26}" text-anchor="end" fill="#1f7a3a">✓ done</text>'
                       f'<text class="ui" x="{x0 + 16}" y="{y0 + 50}" fill="#5b6573">Who  Codex · {escape(a["model"])} {escape(a["effort"])}     Cost  ${s["cost"]:.4f}</text>'
                       f'<text class="ui" x="{x0 + 16}" y="{y0 + 72}" fill="#5b6573">Check  {escape(CHECK)} · passed</text>'
                       f'<text class="ui" x="{x0 + 16}" y="{y0 + 94}" fill="#5b6573">Review  pass · {escape(" · ".join(rv))}     Verdict  right (yours)</text>'
                       f'</g>')
            out.append(f'<text class="ui" x="{x0 + cw + 18}" y="{y0 + 50}" fill="#aab3bf" style="animation-name:c{n}">← the same receipt,</text>')
            out.append(f'<text class="ui" x="{x0 + cw + 18}" y="{y0 + 72}" fill="#aab3bf" style="animation-name:c{n}">every hand-off, one page</text>')
            out.append(keyframes(f"c{n}"))
        else:
            prompt = '<tspan fill="#7f8996">$ </tspan>' if kind == "cmd" else ""
            out.append(f'<text x="28" y="{y}" fill="{color[kind]}" style="animation-name:k{n}">{prompt}{escape(text)}</text>')
            out.append(keyframes(f"k{n}"))
        n += 1
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
  <title id="t">ccx demo: a hand-off and its receipt</title>
  <desc id="d">An animated terminal: ccx route picks a model, ccx run hands the task from Claude Code to Codex and it is done in one attempt; the receipt shows the check ccx ran again, another vendor's review and the cost; ccx ui shows the same receipt on its page. Generated by scripts/make_demo.py with stand-in CLIs.</desc>
  <style>
    text,g{{opacity:0;animation-duration:{total:.1f}s;animation-iteration-count:infinite;animation-timing-function:step-end}}
    text{{font-family:ui-monospace,SFMono-Regular,"Cascadia Mono",Menlo,Consolas,monospace;font-size:15px;white-space:pre}}
    g text,text.ui{{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;font-size:14px;opacity:1;animation:none}}
    text.ui[style]{{opacity:0;animation-duration:{total:.1f}s;animation-iteration-count:infinite;animation-timing-function:step-end}}
    .static{{opacity:1;animation:none}}
    @media (prefers-reduced-motion: reduce){{text,g,text.ui[style]{{opacity:1;animation:none}}}}
  </style>
  <rect width="{W}" height="{H}" rx="12" fill="#11161c"/>
  <circle cx="26" cy="24" r="6" fill="#3b434d"/><circle cx="46" cy="24" r="6" fill="#3b434d"/><circle cx="66" cy="24" r="6" fill="#3b434d"/>
  <text class="static" x="{W - 24}" y="29" text-anchor="end" fill="#7f8996" font-size="13">demo · stand-in CLIs, made-up costs · scripts/make_demo.py</text>
  <line x1="0" y1="44" x2="{W}" y2="44" stroke="#222a33"/>
  {chr(10).join('  ' + r for r in out).strip()}
</svg>
"""


def main() -> int:
    s = session()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg(lines(s), s), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT), f"({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
