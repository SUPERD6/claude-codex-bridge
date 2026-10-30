"""scripts/eval/j0_baseline.py `real`: only conversations a person drove count as the lead — sessions any ccx ledger
knows and headless sessions (Claude -p, codex exec) are left out; an earlier window is re-read the same way; two
readings compare side by side (fake session files, no model calls)."""
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from test_report import ReportEnv, iso

EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(EVAL))

import j0_baseline as j0  # noqa: E402


def _claude(home: Path, sid: str, ts: float, entry: str, cached: int, write: int = 0, folder: str = "-work"):
    d = home / "projects" / folder
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{sid}.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "entrypoint": entry, "sessionId": sid, "timestamp": iso(ts)}) + "\n")
        for i in range(3):
            f.write(json.dumps({"type": "assistant", "sessionId": sid, "entrypoint": entry,
                                "timestamp": iso(ts + i * 60),
                                "message": {"id": f"{sid}-{i}", "model": "claude-opus-5-5",
                                            # a re-write (write > 0) on the last turn: the cache lost that much
                                            "usage": {"input_tokens": 10,
                                                      "cache_read_input_tokens": cached - (write if i == 2 else 0),
                                                      "cache_creation_input_tokens": write if i == 2 else 0,
                                                      "output_tokens": 100}}}) + "\n")


class TestJ0Real(ReportEnv):
    def setUp(self):
        super().setUp()
        self.out = Path(self.tmp.name) / "j0"
        self._old_out, j0.OUT = j0.OUT, self.out
        self.tmpdir = Path(self.tmp.name) / "temp"

    def tearDown(self):
        j0.OUT = self._old_out
        super().tearDown()

    def real(self, **kw):
        a = SimpleNamespace(**{"days": 7, "until": None, "tag": "t", "ledger": None, "keep_headless": False,
                               "project": None, "all_projects": True, **kw})
        orig = j0.other_ledgers
        j0.other_ledgers = lambda tmp=None: orig(self.tmpdir)
        try:
            j0.cmd_real(a)
        finally:
            j0.other_ledgers = orig
        return j0.read_jsonl(self.out / "real.jsonl")[-1]

    def test_leaves_out_sub_sessions(self):
        now = time.time() - 3600
        _claude(self.home_claude, "person", now, "claude-desktop", 300_000)
        _claude(self.home_claude, "headless-lead", now, "sdk-cli", 20_000)            # an eval lead / ccx sub-run
        _claude(self.home_claude, "temp-hub-sub", now, "claude-desktop", 50_000)       # known to a temporary hub
        hub = self.tmpdir / "ccx-7c-abc" / "hub" / "ccx"
        hub.mkdir(parents=True)
        (hub / "ledger.jsonl").write_text(json.dumps({"run_id": "r1", "sessions": ["temp-hub-sub"]}) + "\nnot json\n",
                                          encoding="utf-8")
        x = self.home_codex / "sessions" / "2026" / "10" / "25"
        x.mkdir(parents=True)
        (x / "rollout-exec-1.jsonl").write_text(json.dumps({"timestamp": iso(now), "type": "session_meta",
                                                            "payload": {"id": "exec-1", "originator": "codex_exec"}})
                                                + "\n", encoding="utf-8")
        r = self.real()
        lead = r["lead"]["claude"]
        self.assertEqual((lead["sessions"], lead["requests"]), (1, 3))
        self.assertEqual(lead["median_request_tokens"], 300_010)
        self.assertEqual(r["left_out"]["headless_sessions"], 2)                      # sdk-cli + codex exec
        self.assertEqual(r["left_out"]["other_ledger_sessions"], 1)
        self.assertIn("lead_cache", lead)
        old = self.real(keep_headless=True)["lead"]["claude"]                          # PR #6's reading
        self.assertEqual(old["sessions"], 2)
        self.assertEqual(self.real(ledger=[str(hub / "ledger.jsonl")])["lead"]["claude"]["sessions"], 1)

    def test_sub_runs_do_not_inherit_the_entrypoint(self):
        import os
        from ccx.delegate import _child_env
        os.environ["CLAUDE_CODE_ENTRYPOINT"] = "claude-desktop"
        try:
            self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", _child_env("claude", "r1"))   # -p then writes sdk-cli
        finally:
            os.environ.pop("CLAUDE_CODE_ENTRYPOINT")
        import common
        self.assertIn("CLAUDE_CODE_ENTRYPOINT", common.PARENT_VARS)                    # eval leads too

    def test_only_this_project(self):
        now = time.time() - 3600
        proj = Path(self.tmp.name) / "repo"
        (proj / ".claude" / "worktrees" / "wt1").mkdir(parents=True)
        slug = lambda p: re.sub(r"[^A-Za-z0-9]", "-", str(p.resolve()))  # noqa: E731
        _claude(self.home_claude, "main-co", now, "claude-desktop", 100_000, folder=slug(proj))
        _claude(self.home_claude, "in-wt", now, "claude-desktop", 100_000, folder=slug(proj / ".claude" / "worktrees" / "wt1"))
        _claude(self.home_claude, "elsewhere", now, "claude-desktop", 100_000, folder="-other-project")
        x = self.home_codex / "sessions" / "2026" / "10" / "25"
        x.mkdir(parents=True)
        (x / "rollout-c1.jsonl").write_text(json.dumps({"timestamp": iso(now), "type": "session_meta",
                                                        "payload": {"id": "c1", "cwd": str(proj)}}) + "\n",
                                            encoding="utf-8")
        self.assertEqual(j0.project_sessions(proj, self.home_claude, self.home_codex), {"main-co", "in-wt", "c1"})
        r = self.real(all_projects=False, project=str(proj))
        self.assertEqual((r["project"], r["lead"]["claude"]["sessions"]), (str(proj), 2))
        self.assertEqual(self.real()["lead"]["claude"]["sessions"], 3)

    def test_earlier_window_and_compare(self):
        week = 7 * 86400
        before_t = time.time() - week - 2 * 86400
        _claude(self.home_claude, "old", before_t, "claude-desktop", 350_000, write=200_000)
        _claude(self.home_claude, "new", time.time() - 3600, "claude-desktop", 200_000)
        until = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - week))
        before = self.real(until=until)
        self.assertEqual(before["lead"]["claude"]["sessions"], 1)
        self.assertEqual(before["lead"]["claude"]["median_request_tokens"], 350_010)
        self.assertEqual(before["lead"]["claude"]["lead_cache"]["breaks"], 1)          # the 200k re-write
        after = self.real()
        self.assertEqual(after["lead"]["claude"]["median_request_tokens"], 200_010)
        c = j0.compare_real(before, after)["lead"]["claude"]
        self.assertAlmostEqual(c["median_request_tokens"]["ratio"], round(200_010 / 350_010, 3))
        self.assertEqual(c["lead_cache_breaks"], {"before": 1, "after": 0})
