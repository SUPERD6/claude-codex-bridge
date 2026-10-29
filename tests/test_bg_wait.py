"""`ccx run --bg --wait N` / `ccx resume --bg --wait N`: detach, print the id at once, wait in the same call (one
lead tool call instead of `--bg` then `ccx show --wait`). Fake CLIs only; never a real claude/codex."""
import json
import os
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

    def test_argparse_prefixes_of_wait_are_stripped_too(self):
        self.assertEqual(_without_wait(["run", "--bg", "--wai", "540", "x"]), ["run", "--bg", "x"])
        self.assertEqual(_without_wait(["run", "--wa=5", "--bg", "x"]), ["run", "--bg", "x"])
        self.assertEqual(_without_wait(["run", "--worktree", "--", "--wait", "x"]),
                         ["run", "--worktree", "--", "--wait", "x"])    # after `--` it is part of the brief


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
        self.assertEqual(set(out), {"run_id", "state", "peek", "log", "next"})      # plain --bg's keys, no more
        self.assertEqual(out["state"], "started")
        self.assertEqual(out["next"], f"ccx show {rid} --wait")
        self.assertEqual(out["peek"], f"ccx show {rid}")
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
        # review: the keys a foreground run adds after run() (route, autonomy) are in the waited result too
        self.assertEqual(out["autonomy"]["level"], "L2", out)
        self.assertIn("route", out)
        self.assertEqual(list(out)[-1], "recap")

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
        self.assertIn("no ccx run '20991231-000000-zzzz'", r.stdout + r.stderr)    # ccx's check, not argparse's
        self.assertNotIn("unrecognized arguments", r.stdout + r.stderr)
        self.assertEqual(self.bg_logs(), [])

    def bg_logs(self):
        runs = self.hub / "ccx" / "runs"
        return [d.name for d in runs.iterdir() if (d / "bg.log").exists()] if runs.exists() else []

    def busy_run(self) -> str:
        """A run still working in session s1: its ccx process (this test's own) is alive."""
        from ccx.ledger import write_record
        rid = "20261027-000000-aaaa"
        d = self.hub / "ccx" / "runs" / rid
        d.mkdir(parents=True)
        write_record(d, {"run_id": rid, "state": "running", "ccx_pid": os.getpid(), "session_id": "s1",
                         "to": "codex", "cwd": str(self.work), "mode": "write", "tier": "T2", "attempts": []})
        return rid

    def test_resume_bg_of_a_busy_session_is_refused_before_detaching(self):
        # review: plain `resume --bg` printed `started`, the child refused without a record, `show --wait` waited out
        rid = self.busy_run()
        for extra in ((), ("--wait", "60")):
            r = self.ccx("resume", "--bg", *extra, rid, "go on")
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn(f"run {rid} is still working in that session", r.stdout + r.stderr)
            self.assertNotIn('"started"', r.stdout)
        self.assertEqual(self.bg_logs(), [])                           # nothing detached
        self.assertEqual(self.calls(), [])

    def test_detached_resume_that_finds_its_session_busy_writes_a_refused_record(self):
        # busy only by the time the child looks (after the parent's check): a finished record, not silence
        rid = self.busy_run()
        child = "20261027-000001-bbbb"
        d = self.hub / "ccx" / "runs" / child
        d.mkdir(parents=True)
        (d / "bg.log").write_text("", encoding="utf-8")
        r = self.ccx("resume", rid, "go on", env={"CCX_RUN_ID": child})
        self.assertNotEqual(r.returncode, 0)
        rec = json.loads((d / "run.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["state"], rec["kind"], rec["ok"]), ("finished", "refused", False))
        self.assertIn("still working in that session", rec["result"]["summary"])
        self.assertIn(f"ccx resume {rid}", rec["result"]["next_step"])
        t0 = time.time()
        show = json.loads(self.ccx("show", child, "--wait", "30").stdout)
        self.assertEqual(show["status"], "refused", show)
        self.assertLess(time.time() - t0, 25)                          # the wait ends at once
        self.assertEqual(self.calls(), [])

    def test_run_bg_wait_with_an_abbreviated_wait(self):
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "read", "--bg", "--wai", "90",
                     "explain a.py")
        out = json.loads(r.stdout)
        self.assertEqual(out.get("status"), "done", r.stdout + r.stderr)


class TestRunIds(unittest.TestCase):
    def test_same_second_same_digits_still_gives_two_ids(self):
        import tempfile
        import uuid
        from types import SimpleNamespace
        from unittest import mock
        from ccx import ledger
        p = SimpleNamespace(runs=Path(tempfile.mkdtemp()) / "runs")
        same = [uuid.UUID(int=0)] * 2 + [uuid.UUID(int=1 << 127)]
        with mock.patch("time.strftime", return_value="20261027-000000-"), mock.patch("uuid.uuid4", side_effect=same):
            a, b = ledger.new_run_id(p), ledger.new_run_id(p)
        self.assertNotEqual(a, b)
        self.assertTrue((p.runs / a).is_dir() and (p.runs / b).is_dir())

    def test_a_foreground_run_draws_its_id_from_new_run_id(self):
        import inspect
        from ccx import delegate
        self.assertIn("ledger.new_run_id(p)", inspect.getsource(delegate.run))


if __name__ == "__main__":
    unittest.main()
