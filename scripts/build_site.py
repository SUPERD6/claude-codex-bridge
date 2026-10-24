"""Build the static website into _site/ (what the Pages workflow publishes).

    python scripts/build_site.py [--out _site]

Copies site/ and the images in docs/assets/, and makes the sample dashboard (_site/demo/) with the real
`ccx report`, run on a throwaway hub filled by a few tasks against the stand-in CLIs in tests/fakes — no tokens,
no personal data."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "tests" / "fakes"

# (from, to, extra args, fake status, verdict) — a small, varied week of work
SAMPLE = [
    ("claude", "codex", ["--tier", "T1"], "done", 1),
    ("claude", "codex", ["--tier", "T2"], "done", 1),
    ("codex", "claude", ["--tier", "T2"], "done", 1),
    ("claude", "codex", ["--tier", "T2"], "blocked_then_done", 1),
    ("codex", "claude", ["--tier", "T1"], "done", 0),
    ("claude", "codex", ["--tier", "T3"], "done", 1),
    ("claude", "codex", ["--tier", "T2", "--no-fallback"], "quota", None),
    ("codex", "claude", ["--tier", "T2"], "done", 1),
]


def sample_dashboard(out: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        for sub in ("hub", "codex", "claude", "work"):
            (t / sub).mkdir()
        env = {**os.environ, "CCX_HUB": str(t / "hub"), "CODEX_HOME": str(t / "codex"),
               "CLAUDE_CONFIG_DIR": str(t / "claude"), "CCX_CONFIG": str(t / "cfg.toml"),
               "CCX_CODEX_BIN": str(FAKES / "fake_codex.py"), "CCX_CLAUDE_BIN": str(FAKES / "fake_claude.py"),
               "CCX_AB_RATE": "0", "PYTHONUTF8": "1"}
        for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CCX_DEPTH"):
            env.pop(k, None)

        def ccx(*args: str, status: str = "done") -> dict:
            r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), *args], cwd=t / "work",
                               env={**env, "FAKE_STATUS": status}, capture_output=True, text=True, encoding="utf-8")
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                raise SystemExit(f"ccx {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")

        ccx("init")
        for i, (frm, to, extra, status, verdict) in enumerate(SAMPLE):
            out_run = ccx("run", "--from", frm, "--to", to, "--new", *extra, f"sample task {i + 1}", status=status)
            if verdict is not None and out_run.get("run_id"):
                ccx("verify", out_run["run_id"], "--ok", str(verdict))
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), "report", "--no-lead", "--out", str(out)],
                           cwd=t / "work", env=env, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0 or not out.exists():
            raise SystemExit(f"ccx report failed:\n{r.stdout}\n{r.stderr}")
    # the numbers come from stand-in CLIs: say so on the page, so nobody reads them as results
    html = out.read_text(encoding="utf-8")
    note = ('<div style="margin:0;padding:10px 16px;background:#fff4d6;color:#4a3b00;font:14px/1.5 system-ui,sans-serif;'
            'border-bottom:1px solid #e6d28a">Sample dashboard built from <b>stand-in CLIs</b> (tests/fakes) by '
            'scripts/build_site.py. It shows the layout; the numbers, including “saving”, are not results. '
            '<a href="../" style="color:#0b5c60">Back to ccx</a></div>')
    out.write_text(html.replace("<body>", "<body>" + note, 1) if "<body>" in html else note + html, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    out = Path(ap.parse_args().out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    shutil.copytree(ROOT / "docs" / "assets", out / "assets")
    sample_dashboard(out / "demo" / "index.html")
    (out / ".nojekyll").write_text("", encoding="utf-8")       # serve files as they are
    print("built", out, "->", sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
