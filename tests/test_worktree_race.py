"""make_worktree beside other writers: git's own `worktree add` race (CI windows-latest, 2026-10-30: the second writer
of a `ccx q run` failed with "failed to read .git/worktrees/<other>/commondir")."""
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import workspace  # noqa: E402

REAL_RUN = subprocess.run


def git(cwd, *args):
    return REAL_RUN(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                    capture_output=True, text=True)


class TestWorktreeRace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")

    def tearDown(self):
        for line in git(self.repo, "worktree", "list", "--porcelain").stdout.splitlines():
            if line.startswith("worktree ") and Path(line[9:]).resolve() != self.repo.resolve():
                REAL_RUN(["git", "worktree", "remove", "--force", line[9:]], cwd=self.repo, capture_output=True)
        self.tmp.cleanup()

    def test_threads_of_one_process_add_their_worktrees_one_at_a_time(self):
        inside, most = [0], [0]
        guard = threading.Lock()

        def run(args, *a, **kw):
            add = args[:3] == ["git", "worktree", "add"]
            if add:
                with guard:
                    inside[0] += 1
                    most[0] = max(most[0], inside[0])
                time.sleep(0.3)               # wide open: without the lock both threads are in here together
            try:
                return REAL_RUN(args, *a, **kw)
            finally:
                if add:
                    with guard:
                        inside[0] -= 1

        out, errs = [], []

        def one(i):
            try:
                out.append(workspace.make_worktree(self.repo, f"run-{i}"))
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        with mock.patch.object(workspace.subprocess, "run", run):
            ts = [threading.Thread(target=one, args=(i,)) for i in range(3)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(errs, [])
        self.assertEqual(most[0], 1)
        self.assertEqual(sorted(p.name for p in out), ["run-0", "run-1", "run-2"])
        self.assertTrue(all((p / "a.txt").exists() for p in out))

    def test_the_race_with_another_process_is_tried_again(self):
        calls = []

        def run(args, *a, **kw):
            if args[:3] == ["git", "worktree", "add"]:
                calls.append(args)
                if len(calls) == 1:           # as git leaves it: the branch made, then the fatal
                    git(self.repo, "branch", args[4])
                    return subprocess.CompletedProcess(args, 128, "", (
                        "Preparing worktree (new branch 'x')\nfatal: failed to read "
                        ".git/worktrees/20261031-020710-648a/commondir: No error\n"))
            return REAL_RUN(args, *a, **kw)
        with mock.patch.object(workspace.subprocess, "run", run), mock.patch.object(workspace.time, "sleep"):
            wt = workspace.make_worktree(self.repo, "run-x")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("-b", calls[1])             # the branch git made the first time is used, not deleted
        self.assertTrue((wt / "a.txt").exists())
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "ccx/run-x")

    def test_the_race_is_known_by_its_path_in_any_language(self):
        for err in ("fatal: failed to read .git/worktrees/20261031-020710-648a/commondir: No error",
                    "致命错误：无法读取 C:/Users/Jo Doe/repo/.git/worktrees/20261031-1/gitdir",
                    "fatal: failed to read C:\\Users\\Jo Doe\\repo\\.git\\worktrees\\r-2\\commondir"):
            self.assertTrue(workspace._WT_RACE.search(err), err)
        self.assertFalse(workspace._WT_RACE.search("fatal: a branch named 'ccx/x' already exists"))

    def test_any_other_failure_is_not_tried_again(self):
        workspace.make_worktree(self.repo, "dup")
        calls = []

        def run(args, *a, **kw):
            if args[:3] == ["git", "worktree", "add"]:
                calls.append(args)
            return REAL_RUN(args, *a, **kw)
        with mock.patch.object(workspace.subprocess, "run", run):
            with self.assertRaises(RuntimeError) as e:
                workspace.make_worktree(self.repo, "dup")      # the branch exists already
        self.assertEqual(len(calls), 1)
        self.assertIn("git worktree add failed", str(e.exception))
        self.assertTrue(git(self.repo, "rev-parse", "--verify", "ccx/dup").stdout.strip())   # not deleted


if __name__ == "__main__":
    unittest.main()
