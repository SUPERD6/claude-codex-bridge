"""`ccx stop`: the whole process tree goes, the run's own ccx records the stop, `ccx resume` goes on. Fake CLIs only."""
import json
import subprocess
import sys
import time

from test_ccx import FAKES, Env

from ccx import ledger
from ccx.config import Paths
from ccx.runners import Invocation, execute, group_flags, kill_tree, pid_alive
from ccx.stop import stop


def wait_for(pred, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.1)
    return pred()


class StopEnv(Env):
    def run_dir(self, run_id):
        return self.hub / "ccx" / "runs" / run_id

    def record(self, run_id):
        f = self.run_dir(run_id) / "run.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def ledger_rows(self, run_id):
        return [r for r in ledger.rows(Paths(self.hub)) if r.get("run_id") == run_id and not r.get("type")]

    def start_bg(self, **env):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-ab", "--bg", "implement x", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        run_id = json.loads(r.stdout)["run_id"]
        self._bg = [*getattr(self, "_bg", []), run_id]
        return run_id

    def tearDown(self):
        for run_id in getattr(self, "_bg", []):    # before the temp folder goes (cleanups run after it)
            self.reap(run_id)
        for i in range(20):
            try:
                super().tearDown()
                return
            except PermissionError:      # Windows lets go of a dead process's cwd a moment later
                if i == 19:
                    raise
                time.sleep(0.25)

    def reap(self, run_id):
        """Let the background ccx finish before the temp folder goes (Windows can't delete a process's cwd)."""
        rec = self.record(run_id)
        if not wait_for(lambda: not pid_alive(rec.get("ccx_pid")), 15):
            kill_tree(rec.get("ccx_pid"))
        kill_tree(rec.get("pid"))
        wait_for(lambda: not pid_alive(rec.get("ccx_pid")) and not pid_alive(rec.get("pid")), 10)


class TestStop(StopEnv):
    def test_stop_kills_the_tree_and_the_run_records_it_then_resume(self):
        gc = self.work.parent / "grandchild.pid"
        run_id = self.start_bg(FAKE_STATUS="hang", FAKE_HANG_S="90", FAKE_GRANDCHILD=str(gc))
        rec = wait_for(lambda: (r := self.record(run_id)).get("pid") and r.get("session_id") and gc.exists() and r)
        self.assertTrue(rec, "the run never started")
        self.assertTrue(pid_alive(rec["ccx_pid"]))
        gpid = int(gc.read_text())
        self.assertTrue(pid_alive(gpid))
        r = self.ccx("stop", run_id)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["state"], out["kind"], out["closed_by"]), ("stopped", "user_stopped", "its own ccx process"))
        self.assertEqual(out["resume"], f"ccx resume {run_id}")
        self.assertTrue(wait_for(lambda: not pid_alive(gpid), 10), "the grandchild survived")
        self.assertTrue(wait_for(lambda: not pid_alive(rec["pid"]), 10))
        rec = self.record(run_id)
        self.assertEqual((rec["state"], rec["kind"], rec["ok"]), ("stopped", "user_stopped", False))
        self.assertEqual([a["kind"] for a in rec["attempts"]], ["user_stopped"])
        rows = self.ledger_rows(run_id)
        self.assertEqual([x["kind"] for x in rows], ["user_stopped"])          # one row, written by the run itself
        # nothing to learn from a stop
        self.assertFalse((self.hub / "ccx" / "routing-state.json").exists() and
                         "gpt-6-luna" in (self.hub / "ccx" / "routing-state.json").read_text(encoding="utf-8"))
        r = self.ccx("resume", run_id, "go on", env={"FAKE_STATUS": "done"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = self.calls()[-1]["argv"]
        self.assertEqual(argv[:3], ["exec", "resume", rec["session_id"]])

    def test_stop_twice_and_on_a_finished_run_does_nothing(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "x")
        run_id = json.loads(r.stdout)["run_id"]
        r = self.ccx("stop", run_id)
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertEqual((out["stopped"], out["state"]), (False, "finished"))
        self.assertFalse((self.run_dir(run_id) / "stop.request").exists())

    def test_parent_gone_stop_closes_the_record_itself(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], **group_flags())
        try:
            run_id = "20261025-000000-dead"
            d = self.run_dir(run_id)
            d.mkdir(parents=True)
            ledger.write_record(d, {"run_id": run_id, "to": "codex", "state": "running", "attempts": [],
                                    "session_id": "thread-x", "pid": child.pid, "ccx_pid": dead.pid,
                                    "child": "python.exe" if sys.platform == "win32" else "python", "ts": time.time()})
            out = stop(Paths(self.hub), run_id, wait=1)
            self.assertEqual((out["stopped"], out["kind"], out["killed"]), (True, "user_stopped", True))
            self.assertIn("gone", out["closed_by"])
            self.assertTrue(wait_for(lambda: child.poll() is not None, 10))
            rec = self.record(run_id)
            self.assertEqual((rec["state"], rec["kind"]), ("stopped", "user_stopped"))
            self.assertEqual(len(self.ledger_rows(run_id)), 1)
            out = stop(Paths(self.hub), run_id, wait=1)                 # again: nothing more happens
            self.assertFalse(out["stopped"])
            self.assertEqual(len(self.ledger_rows(run_id)), 1)
        finally:
            if child.poll() is None:
                child.kill()

    def test_stop_as_it_finishes_keeps_the_result(self):
        # the stop request lands just as the sub-agent finished: its finished work is kept, nothing is lost
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "x",
                     env={"FAKE_STOP_AT_END": "1"})
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "done", out)
        rec = self.record(out["run_id"])
        self.assertEqual((rec["state"], rec["kind"], rec["stop_requested"]), ("finished", "ok", True))
        self.assertEqual(len(self.ledger_rows(out["run_id"])), 1)

    def test_stop_and_the_run_closing_at_once_write_one_ledger_row(self):
        # `ccx stop` took the final lock first (it thought the run's ccx was gone): the run writes no second row
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "x",
                     env={"FAKE_STOP_AT_END": "lock"})
        run_id = json.loads(r.stdout)["run_id"]
        self.assertEqual(self.ledger_rows(run_id), [])
        d = self.run_dir(run_id)
        self.assertFalse(ledger.claim_final(d, "again"))
        d2 = self.run_dir("other")
        d2.mkdir(parents=True)
        self.assertTrue(ledger.claim_final(d2, "first"))
        self.assertFalse(ledger.claim_final(d2, "second"))


class TestTreeKill(StopEnv):
    def test_timeout_kills_the_grandchild_too_and_does_not_hang(self):
        gc = self.work.parent / "gc.pid"
        inv = Invocation(argv=[sys.executable, str(FAKES / "fake_codex.py"), "exec"], stdin="x", cwd=self.work)
        env = {**self.env, "FAKE_STATUS": "hang", "FAKE_HANG_S": "60", "FAKE_GRANDCHILD": str(gc)}
        t0 = time.time()
        oc, _, _ = execute("codex", inv, 3, env)
        self.assertLess(time.time() - t0, 30)             # the grandchild holds stdout open: without the tree kill
        self.assertEqual(oc.kind, "timeout")              # this waited its whole 120 s
        self.assertTrue(wait_for(lambda: not pid_alive(int(gc.read_text())), 10))

    def test_stop_file_stops_a_run_without_ccx_stop(self):
        # e.g. `ccx stop` ran on another machine sharing the hub: the run's own ccx sees the request
        sf = self.work.parent / "stop.request"
        inv = Invocation(argv=[sys.executable, str(FAKES / "fake_codex.py"), "exec"], stdin="x", cwd=self.work)
        env = {**self.env, "FAKE_STATUS": "hang", "FAKE_HANG_S": "60"}
        pids = []
        import threading
        threading.Timer(1.5, lambda: sf.write_text("{}")).start()
        t0 = time.time()
        oc, so, _ = execute("codex", inv, 120, env, on_start=pids.append, stop_file=sf)
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(oc.kind, "user_stopped")
        self.assertIn("thread.started", so)
        self.assertEqual(len(pids), 1)
