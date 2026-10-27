"""`ccx run --bg --wait N` / `ccx resume --bg --wait N`: detach, print the id at once, wait in the same call (one
lead tool call instead of `--bg` then `ccx show --wait`). Fake CLIs only; never a real claude/codex."""
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import Env  # noqa: E402

from ccx.commands.delegation import _without_wait  # noqa: E402


class TestWithoutWait(unittest.TestCase):
    def test_wait_is_stripped_from_the_childs_argv(self):
        self.assertEqual(_without_wait(["run", "--bg", "--wait", "540", "--tier", "T1", "x"]),
                         ["run", "--bg", "--tier", "T1", "x"])
        self.assertEqual(_without_wait(["resume", "r1", "--wait=60", "go on"]), ["resume", "r1", "go on"])
        self.assertEqual(_without_wait(["run", "--bg", "x"]), ["run", "--bg", "x"])


class TestBgWait(Env):
    def wait_done(self, rid):
        """Let a detached child finish before the temp folder goes."""
        self.ccx("show", rid, "--wait", "90")

    def test_finished_run_prints_the_final_result_in_the_same_call(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "read", "--bg", "--wait", "90",
                     "explain a.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)                                     # one JSON document on stdout
        self.assertEqual((out["status"], out["ok"]), ("done", True), out)
        self.assertEqual(list(out)[-1], "recap")
        self.assertIn(f"started {out['run_id']}", r.stderr)            # the id came first, on stderr
        log = (self.hub / "ccx" / "runs" / out["run_id"] / "bg.log").read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("--wait N goes with --bg", log)               # the child did not get --wait

    def test_timeout_prints_exactly_what_bg_prints(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-ab", "--bg", "--wait", "1", "implement x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        rid = out["run_id"]
        self.assertEqual(set(out), {"run_id", "state", "check", "log", "next"})      # plain --bg's keys, no more
        self.assertEqual(out["state"], "started")
        self.assertEqual(out["next"], f"ccx show {rid} --wait")
        self.assertEqual(out["check"], f"ccx show {rid}")
        self.ccx("stop", rid)
        self.wait_done(rid)

    def test_refused_by_routing_ends_the_wait_at_once(self):
        t0 = time.time()
        r = self.ccx("run", "--bg", "--wait", "90", "--from", "claude", "fix typo")
        out = json.loads(r.stdout)
        self.assertEqual(out["kind"], "not_delegated", r.stdout + r.stderr)
        self.assertFalse(out["ok"])
        self.assertEqual(r.returncode, 2)
        self.assertLess(time.time() - t0, 60)
        self.assertEqual(self.calls(), [])                             # nobody was paid

    def test_child_that_dies_before_the_run_ends_the_wait(self):
        # --fork with no Claude Code session: the detached child refuses before any run record exists
        t0 = time.time()
        r = self.ccx("run", "--from", "claude", "--to", "claude", "--model", "sonnet", "--effort", "low", "--fork",
                     "--bg", "--wait", "90", "implement x")
        out = json.loads(r.stdout)
        self.assertEqual((out["state"], out["ok"]), ("failed", False), out)
        self.assertIn("--fork", out["log_tail"])
        self.assertEqual(r.returncode, 2)
        self.assertLess(time.time() - t0, 60)

    def test_autonomy_branch_waits_after_its_gate(self):
        stop = json.loads(self.ccx("run", "--from", "claude", "--tier", "T1", "--autonomy", "L0", "--mode", "read",
                                   "--bg", "--wait", "90", "explain a.py").stdout)
        self.assertNotIn("run_id", stop)                               # L0 proposes only: nothing detached
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--autonomy", "L2", "--mode", "read", "--bg",
                     "--wait", "90", "explain a.py")
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "done", r.stdout + r.stderr)
        self.assertIn(f"started {out['run_id']}", r.stderr)

    def test_wait_without_bg_is_an_error(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--wait", "5", "explain a.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--wait N goes with --bg", r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])

    def test_plain_bg_is_unchanged(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "read", "--bg", "explain a.py")
        out = json.loads(r.stdout)
        self.assertEqual(out["state"], "started")
        self.assertEqual(out["next"], f"ccx show {out['run_id']} --wait")
        self.wait_done(out["run_id"])

    def test_resume_bg_wait(self):
        first = json.loads(self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--review", "off",
                                    "implement thing").stdout)
        r = self.ccx("resume", "--review", "off", "--bg", "--wait", "90", first["run_id"], "go on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "done", out)
        rec = json.loads((self.hub / "ccx" / "runs" / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["resumed_from"], first["run_id"])

    def test_resume_bg_of_an_unknown_run_fails_before_detaching(self):
        r = self.ccx("resume", "--bg", "20991231-000000-zzzz", "go on")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.hub / "ccx" / "runs").exists() and any(
            (d / "bg.log").exists() for d in (self.hub / "ccx" / "runs").iterdir()))


if __name__ == "__main__":
    unittest.main()
