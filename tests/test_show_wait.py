"""`ccx show <id> --wait` (a lead waiting out a long run within one tool call) and the diffstat in the compact
result (the lead needs no `git diff` of its own). Fake CLIs only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import Env  # noqa: E402


def _rec(run_id: str, **kw) -> dict:
    r = {"run_id": run_id, "label": "", "to": "codex", "caller": "claude", "tier": "T2", "mode": "write",
         "cwd": "", "session_id": "s1", "resumed_from": None, "ok": True, "state": "finished", "error": None,
         "kind": "ok", "ts": time.time(), "result": {"status": "done", "summary": f"did {run_id}"},
         "attempts": [{"rung": "codex:gpt-6-luna:low", "model": "gpt-6-luna", "effort": "low", "usage4": {},
                       "ae_usd": 0.01}]}
    r.update(kw)
    return r


class TestShowWait(Env):
    def put(self, rec: dict) -> None:
        d = self.hub / "ccx" / "runs" / rec["run_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.json").write_text(json.dumps(rec), encoding="utf-8")

    def test_wait_on_a_finished_run_prints_the_run_result(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "write", "--review", "off",
                     "rename foo to bar in a.py")
        rid = json.loads(r.stdout)["run_id"]
        w = self.ccx("show", rid, "--wait", "5")
        self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
        out = json.loads(w.stdout)
        self.assertEqual((out["run_id"], out["status"], out["ok"]), (rid, "done", True))
        self.assertEqual(list(out)[-1], "recap")
        self.assertIn(f"ccx run {rid}: status=done", out["recap"])

    def test_wait_follows_a_review_fix_round_to_its_last_run(self):
        first = "20991231-100000-aaaa"
        fix = "20991231-100500-bbbb"
        self.put(_rec(first, kind="review_issues", ok=False,
                      review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        self.put(_rec(fix, resumed_from=first, review_of=first, review={"verdict": "pass"},
                      first_review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        self.put(_rec("20991231-110000-cccc", resumed_from="20991231-000000-zzzz"))   # unrelated later run
        w = self.ccx("show", first, "--wait", "5")
        out = json.loads(w.stdout)
        self.assertEqual(out["run_id"], fix, w.stdout + w.stderr)
        self.assertEqual(out["chain"], f"{first} -> {fix}")
        self.assertEqual(out["fixed_after_review_of"], first)
        self.assertEqual(out["review"]["verdict"], "pass")
        self.assertTrue(out["recap"].startswith(f"ccx run {fix}:"))

    def test_plain_show_follows_a_finished_fix_round(self):
        # plan #3: `ccx show <first id>` without --wait printed the first run's stale result (ok true, kind
        # review_issues) after its fix round had ended review_failed; it reports the chain's final state, like --wait
        first, fix = "20991231-100000-aaaa", "20991231-100500-bbbb"
        self.put(_rec(first, kind="review_issues", review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        self.put(_rec(fix, resumed_from=first, review_of=first, kind="review_failed",
                      review={"verdict": "issues", "issues": ["a.py:1 bug"]},
                      first_review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        out = json.loads(self.ccx("show", first).stdout)
        self.assertEqual((out["run_id"], out["kind"], out["ok"]), (fix, "review_failed", False), out)
        self.assertEqual(out["chain"], f"{first} -> {fix}")
        self.assertIn("[must]", out["hint"])
        full = self.ccx("show", first, "--full").stdout
        self.assertIn(f"chain: {first} -> {fix}", full)
        self.assertIn(f'"run_id": "{fix}"', full)
        self.assertEqual(json.loads(self.ccx("show", fix).stdout)["run_id"], fix)       # the last link: itself

    def test_plain_show_of_a_fix_round_still_running(self):
        first, fix = "20991231-100000-aaaa", "20991231-100500-bbbb"
        self.put(_rec(first, kind="review_issues", review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        self.put(_rec(fix, resumed_from=first, review_of=first, state="running", result=None, kind=None, ok=False,
                      pid=None))
        (self.hub / "ccx" / "runs" / fix / "beat").write_text(str(time.time()), encoding="utf-8")
        out = json.loads(self.ccx("show", first).stdout)
        self.assertEqual((out["run_id"], out["status"], out["ok"]), (fix, "running", False), out)

    def test_plain_show_before_the_fix_round_starts(self):
        first = "20991231-100000-aaaa"
        self.put(_rec(first, kind="review_issues", review={"verdict": "issues", "issues": ["a.py:1 bug"]}))
        out = json.loads(self.ccx("show", first).stdout)
        self.assertEqual((out["run_id"], out["ok"], out["fix_round"]), (first, False, "starting"), out)
        self.assertEqual(out["next"], f"ccx show {first} --wait")
        f = self.hub / "ccx" / "runs" / first / "run.json"
        old = time.time() - 3600                       # long ended and no fix round came: review_issues is final
        os.utime(f, (old, old))
        out = json.loads(self.ccx("show", first).stdout)
        self.assertEqual((out["kind"], out["ok"]), ("review_issues", False), out)
        self.assertNotIn("fix_round", out)

    def test_wait_times_out_with_status_running(self):
        rid = "20991231-120000-dddd"
        rec = _rec(rid, state="running", result=None, kind=None, ok=False, pid=None)
        self.put(rec)
        (self.hub / "ccx" / "runs" / rid / "beat").write_text(str(time.time()), encoding="utf-8")
        t0 = time.time()
        w = self.ccx("show", rid, "--wait", "1")
        self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
        out = json.loads(w.stdout)
        self.assertEqual(out["status"], "running")
        self.assertEqual(out["next"], f"ccx show {rid} --wait")
        self.assertLess(time.time() - t0, 30)

    def test_wait_on_an_unknown_run_fails(self):
        w = self.ccx("show", "20991231-130000-eeee", "--wait", "1")
        self.assertNotEqual(w.returncode, 0)

    def test_bg_says_how_to_wait(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "read", "--bg", "explain a.py")
        out = json.loads(r.stdout)
        self.assertEqual(out["next"], f"ccx show {out['run_id']} --wait")
        w = self.ccx("show", out["run_id"], "--wait", "60")
        self.assertEqual(json.loads(w.stdout)["status"], "done", w.stdout + w.stderr)

    def test_diffstat_for_a_write_run_in_a_git_repo(self):
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("foo = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-q", "-m", "init"], cwd=self.work, check=True)
        write = f"{self.work / 'a.py'}=bar = 1\nbaz = 2\n;{self.work / 'new.py'}=x = 1\n"
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "write", "--review", "off",
                     "rename foo to bar in a.py", env={"FAKE_WRITE": write})
        out = json.loads(r.stdout)
        self.assertIn("1 file changed", out.get("diffstat", ""), r.stdout + r.stderr)
        self.assertIn("1 new untracked file", out["diffstat"])
        w = json.loads(self.ccx("show", out["run_id"]).stdout)
        self.assertEqual(w["diffstat"], out["diffstat"])

    def test_no_diffstat_outside_git(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "write", "--review", "off",
                     "rename foo to bar in a.py")
        self.assertNotIn("diffstat", json.loads(r.stdout))
