"""Smoke test for an INSTALLED ccx (wheel / pipx), run by CI outside the source tree:

    python tests/smoke_installed.py <path-to-installed-ccx-executable>

Uses the fake CLIs in tests/fakes and temporary homes; never calls real CLIs."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

FAKES = Path(__file__).resolve().parent / "fakes"


def main(ccx: str) -> int:
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        for sub in ("hub", "codex", "claude", "work"):
            (t / sub).mkdir()
        env = {**os.environ, "CCX_HUB": str(t / "hub"), "CODEX_HOME": str(t / "codex"),
               "CLAUDE_CONFIG_DIR": str(t / "claude"), "CCX_CODEX_BIN": str(FAKES / "fake_codex.py"),
               "CCX_CLAUDE_BIN": str(FAKES / "fake_claude.py"), "CCX_AB_RATE": "0", "PYTHONUTF8": "1"}
        for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CCX_DEPTH"):
            env.pop(k, None)

        def run(*args: str) -> str:
            r = subprocess.run([ccx, *args], cwd=t / "work", env=env, capture_output=True, text=True,
                               encoding="utf-8")
            if r.returncode != 0:
                raise SystemExit(f"ccx {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
            return r.stdout

        print(run("--version").strip())
        run("init")
        out = json.loads(run("run", "--from", "claude", "--to", "codex", "--tier", "T2", "implement thing"))
        assert out["status"] == "done", out
        route = json.loads(run("route", "--to", "codex", "--b", "3"))
        assert route["source"] == "task-routing", route           # the skill script shipped as package data
        skills = json.loads(run("skills", "install"))["skills"]
        assert {s["skill"] for s in skills} >= {"agent-delegate", "task-routing"}, skills
        print("installed ccx: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
