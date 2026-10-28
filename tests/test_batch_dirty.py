"""`ccx batch` with uncommitted changes: parallel writers share the project folder (as `ccx q run` does) instead of
each getting a worktree made from the last commit, which would not have those changes (fakes only)."""
import json
import subprocess

from test_adapters import AdapterEnv

# passes only where the uncommitted file is: in the project folder, not in a worktree made from HEAD
NEED_WIP = 'python -c "import os, sys; sys.exit(0 if os.path.exists(\'wip.txt\') else 1)"'


class TestBatchDirty(AdapterEnv):
    def git_init(self):
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                     "-m", "init"]):
            subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True)

    def batch(self, tasks, *flags):
        f = self.work / "plan.json"          # the plan file itself sits in the project and does not count
        f.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        r = self.ccx("batch", str(f), "--from", "claude", *flags)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def writers(self, check=None):
        return [{"id": f"w{i}", "to": "codex", "tier": "T1", "mode": "write", "review": "off",
                 "brief": f"write piece {i}", "cwd": str(self.work), **({"check": check} if check else {})}
                for i in range(2)]

    def test_uncommitted_work_keeps_writers_in_the_project_folder(self):
        self.git_init()
        (self.work / "wip.txt").write_text("not committed yet", encoding="utf-8")
        out = self.batch(self.writers(NEED_WIP))
        self.assertTrue(all(r["ok"] for r in out["results"]), out)          # both saw wip.txt
        self.assertTrue(all("worktree" not in r for r in out["results"]))
        self.assertEqual(out["shared_folder"]["ids"], ["w0", "w1"])
        self.assertIn("commit first", out["shared_folder"]["why"])

    def test_lanes_path_too(self):
        self.git_init()
        (self.work / "wip.txt").write_text("not committed yet", encoding="utf-8")
        out = self.batch(self.writers(NEED_WIP), "--lanes", "1")
        self.assertTrue(all(r["ok"] for r in out["results"]), out)
        self.assertTrue(all("worktree" not in r for r in out["results"]))
        self.assertEqual(out["shared_folder"]["ids"], ["w0", "w1"])

    def test_clean_repo_still_gives_each_writer_a_worktree(self):
        self.git_init()
        out = self.batch(self.writers())
        trees = [r.get("worktree") for r in out["results"]]
        self.assertTrue(all(trees), out)
        self.assertEqual(len(set(trees)), 2)
        self.assertNotIn("shared_folder", out)

    def test_readers_and_a_lone_writer_say_nothing(self):
        self.git_init()
        (self.work / "wip.txt").write_text("x", encoding="utf-8")
        out = self.batch(self.writers()[:1] + [{"id": "r", "to": "codex", "tier": "T1", "mode": "read",
                                                 "brief": "read r", "cwd": str(self.work)}])
        self.assertNotIn("shared_folder", out)
        self.assertTrue(all("worktree" not in r for r in out["results"]))
