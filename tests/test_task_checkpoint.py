"""Tests for the standalone task-checkpoint skill: interrupt, detect, resume."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "task-checkpoint" / "scripts" / "checkpoint.py"


class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=self.repo, capture_output=True, check=True)  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        g("config", "commit.gpgsign", "false")
        (self.repo / "a.py").write_text("x = 1\n")
        g("add", "-A")
        g("commit", "-q", "-m", "init")
        self.env = {**os.environ, "CHECKPOINT_ROOT": str(self.repo), "CHECKPOINT_STALE_SECONDS": "60"}

    def tearDown(self):
        self.tmp.cleanup()

    def cp(self, *args):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def plan(self, tid):
        return json.loads((self.repo / ".ccx" / "tasks" / tid / "plan.json").read_text(encoding="utf-8"))

    def test_full_interrupt_and_resume_cycle(self):
        tid = self.cp("init", "--title", "Refactor loader", "--step", "parse", "--step", "cache", "--step", "docs")
        self.assertIn(".ccx/tasks/", (self.repo / ".gitignore").read_text())
        # step 1 done with a code change -> snapshot taken, branch untouched
        self.cp("start", tid, "1", "--agent", "codex", "--session", "th-111")
        (self.repo / "a.py").write_text("x = 2\n")
        self.cp("done", tid, "1", "--note", "tests pass")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout
        log = subprocess.run(["git", "log", "--oneline"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertEqual(len(log.strip().splitlines()), 1, "checkpoint must not commit to the branch")
        snap = self.plan(tid)["steps"][0]["snapshot"]
        self.assertTrue(snap and snap != head.strip())
        refs = subprocess.run(["git", "for-each-ref", "refs/checkpoints"], cwd=self.repo,
                              capture_output=True, text=True).stdout
        self.assertIn(f"refs/checkpoints/{tid}/step-1", refs)
        # step 2 starts, then the process "dies" (no done, heartbeat goes stale)
        self.cp("start", tid, "2", "--agent", "codex", "--session", "th-222")
        self.assertIn("running", self.cp("status", tid))
        self.assertEqual(self.cp("status", "--quiet"), "")       # running task: hook stays silent
        # the heartbeat goes stale: age it instead of sleeping (a busy machine made a 2 s threshold flaky)
        lock = self.repo / ".ccx" / "tasks" / tid / "lock.json"
        data = json.loads(lock.read_text(encoding="utf-8"))
        data["heartbeat"] -= 120
        lock.write_text(json.dumps(data), encoding="utf-8")
        out = self.cp("status", "--quiet")
        self.assertIn("interrupted", out)
        self.assertIn("1/3 steps done", out)
        brief = self.cp("brief", tid)
        self.assertIn("[x] 1. parse", brief)
        self.assertIn("[~] 2. cache", brief)
        self.assertIn("session th-222", brief)
        self.assertIn("Next: step 2", brief)
        self.assertIn(f"git diff {snap[:12]}", brief)

    def test_quota_stop_records_reason_and_retry(self):
        tid = self.cp("init", "--title", "Long job", "--step", "a", "--step", "b")
        self.cp("start", tid, "1", "--agent", "claude", "--session", "s-1")
        self.cp("fail", tid, "1", "--reason", "quota", "--retry-after", "2026-10-23T05:00Z", "--note", "429")
        s = self.cp("status", "--quiet")
        self.assertIn("step 1 quota", s)
        b = self.cp("brief", tid)
        self.assertIn("stopped: quota", b)
        self.assertIn("retry after 2026-10-23T05:00Z", b)
        # restart the step: reason cleared
        self.cp("start", tid, "1", "--agent", "codex")
        self.assertNotIn("reason", self.plan(tid)["steps"][0])

    def test_finish_silences_status_and_torn_log_line_tolerated(self):
        tid = self.cp("init", "--title", "Small", "--step", "only")
        with open(self.repo / ".ccx" / "tasks" / tid / "progress.jsonl", "a") as f:
            f.write('{"ts": "x", "event": "no')   # crash mid-write
        self.cp("note", tid, "still works")
        self.assertIn("still works", self.cp("brief", tid))   # the entry after the torn line survives
        self.cp("start", tid, "1")
        self.cp("done", tid, "1")
        self.cp("finish", tid)
        self.assertEqual(self.cp("status", "--quiet"), "")

    def test_works_outside_git(self):
        d = Path(self.tmp.name) / "plain"
        d.mkdir()
        env = {**self.env, "CHECKPOINT_ROOT": str(d)}
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], cwd=d, env=env,  # noqa: E731
                                        capture_output=True, text=True)
        tid = run("init", "--title", "no git", "--step", "x").stdout.strip()
        self.assertEqual(run("done", tid, "1").returncode, 0)
        self.assertIn("[x] 1. x", run("brief", tid).stdout)



class TestWorktrees(TestCheckpoint):  # reuses setUp; only its own test is new
    def test_worktree_shares_main_task_folder(self):
        wt = Path(self.tmp.name) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "side", str(wt)], cwd=self.repo, check=True,
                       capture_output=True)
        env = {k: v for k, v in self.env.items() if k != "CHECKPOINT_ROOT"}
        r = subprocess.run([sys.executable, str(SCRIPT), "init", "--title", "from worktree", "--step", "x"],
                           cwd=wt, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / ".ccx" / "tasks" / r.stdout.strip()).exists())


if __name__ == "__main__":
    unittest.main()
