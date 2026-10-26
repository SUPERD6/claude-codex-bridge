"""Killed and abandoned runs are counted: the usage spent before the kill becomes an attempt, and a run whose ccx
process died is closed as interrupted (then resumable). Fake CLIs only."""
import json
import os
import subprocess
import sys
import time

from test_ccx import ROOT, Env
from test_stop import StopEnv, wait_for

from ccx import ledger, recover
from ccx.config import Paths
from ccx.runners import group_flags, kill_tree, pid_alive


class RecoverEnv(StopEnv):
    def record(self, run_id):
        f = self.hub / "ccx" / "runs" / run_id / "run.json"
        return ledger.read_record(f) if f.exists() else {}

    def rows(self, run_id):
        return [r for r in ledger.rows(Paths(self.hub)) if r.get("run_id") == run_id and not r.get("type")]

    def tiers(self, text):
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        (self.hub / "ccx" / "tiers.toml").write_text(text, encoding="utf-8")


class TestKilledUsage(RecoverEnv):
    def test_codex_timeout_counts_what_its_session_file_says(self):
        self.tiers("[defaults]\ntimeout_sec = 5\n")
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-fallback", "x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60"})
        out = json.loads(r.stdout)
        self.assertEqual(out["kind"], "timeout")
        a = self.record(out["run_id"])["attempts"][-1]
        self.assertEqual(a["kind"], "timeout")
        self.assertGreater(a["usage"]["output_tokens"], 0)          # 120 per 2 s tick in the fake's rollout
        self.assertGreater(a["ae_usd"], 0)
        row = self.rows(out["run_id"])[0]
        self.assertEqual(row["usage4"]["output_tokens"], a["usage"]["output_tokens"])
        self.assertGreater(row["ae_usd"], 0)

    def test_codex_0164_stopped_in_its_first_request_counts_the_request_records(self):
        # real run 2026-10-25 (codex-cli 0.164): stopped during the first request, the session file had a
        # token_usage_record for it and no token_count; the attempt was counted as 0 tokens
        self.tiers("[defaults]\ntimeout_sec = 3\n")
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-fallback", "x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60", "FAKE_RECORDS": "1"})
        out = json.loads(r.stdout)
        rec = self.record(out["run_id"])
        a = rec["attempts"][-1]
        self.assertEqual((a["kind"], a["recovered"]), ("timeout", True))
        n = a["usage"]["input_tokens"] // 19245
        self.assertGreaterEqual(n, 1)
        self.assertEqual(a["usage"], {"input_tokens": 19245 * n, "cache_write_tokens": 0, "cache_write_1h_tokens": 0,
                                      "cached_input_tokens": 0, "output_tokens": 207 * n})
        self.assertNotIn("codex_total", a)
        # resumed: the new turn's own total counts in full (the killed request is not taken as a running total)
        r = self.ccx("resume", out["run_id"], "go on", env={"FAKE_STATUS": "done"})
        res = json.loads(r.stdout)
        self.assertEqual(res["tokens"], {"input": 400, "cache_write": 0, "cached": 800, "output": 150})

    def test_claude_stopped_counts_its_streamed_messages_once(self):
        r = self.ccx("run", "--from", "codex", "--to", "claude", "--model", "sonnet", "--effort", "low", "--bg",
                     "--no-ab", "x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60"})
        run_id = json.loads(r.stdout)["run_id"]
        self._bg = [run_id]
        self.assertTrue(wait_for(lambda: self.record(run_id).get("session_id")))
        time.sleep(0.5)
        r = self.ccx("stop", run_id)
        self.assertEqual(json.loads(r.stdout)["kind"], "user_stopped", r.stdout + r.stderr)
        a = self.record(run_id)["attempts"][-1]
        self.assertEqual(a["kind"], "user_stopped")
        # one message, printed twice in the stream: counted once
        self.assertEqual(a["usage"], {"input_tokens": 10, "cache_write_tokens": 2000, "cache_write_1h_tokens": 0,
                                      "cached_input_tokens": 5000, "output_tokens": 300})
        self.assertEqual(self.rows(run_id)[0]["usage4"]["output_tokens"], 300)


class TestSweep(RecoverEnv):
    def start_and_kill_ccx(self, **env):
        """Start a background run, then kill its ccx process (not the sub-agent): a closed window, a crash."""
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--bg", "--no-ab", "x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60", **env})
        run_id = json.loads(r.stdout)["run_id"]
        self._bg = [run_id]
        rec = wait_for(lambda: (x := self.record(run_id)).get("pid") and x.get("session_id") and x)
        self.assertTrue(rec)
        time.sleep(2.5)                                   # the fake's session file grows every 2 s
        self.addCleanup(kill_tree, rec["pid"])           # the sub-agent was left running on purpose
        if os.name == "nt":
            k = subprocess.run(["taskkill", "/PID", str(rec["ccx_pid"]), "/F"], capture_output=True, timeout=10)
            # a sandbox (Codex's on Windows) may not let us kill the detached ccx: say so instead of timing out
            if k.returncode != 0 and pid_alive(rec["ccx_pid"]):
                self.addCleanup(kill_tree, rec["ccx_pid"])
                self.skipTest(f"cannot kill the --bg ccx process here (taskkill exit {k.returncode}; sandboxed?)")
        else:
            os.kill(rec["ccx_pid"], 9)
        if not wait_for(lambda: not pid_alive(rec["ccx_pid"]), 5):
            self.addCleanup(kill_tree, rec["ccx_pid"])
            self.skipTest("the --bg ccx process survived the kill (sandboxed?); this test needs it gone")
        return run_id, rec

    def test_dead_ccx_is_closed_as_interrupted_by_stats_then_resumes(self):
        run_id, rec = self.start_and_kill_ccx()
        self.assertEqual(self.record(run_id)["state"], "running")
        r = self.ccx("stats")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec2 = self.record(run_id)
        self.assertEqual((rec2["state"], rec2["kind"]), ("interrupted", "interrupted"))
        a = rec2["attempts"][-1]
        self.assertEqual((a["kind"], a["rung"], a["recovered"]), ("killed", "codex:gpt-6-luna:low", True))
        self.assertGreater(a["usage"]["output_tokens"], 0)
        self.assertEqual(len(self.rows(run_id)), 1)
        self.ccx("stats")                                  # again: nothing more
        self.assertEqual(len(self.rows(run_id)), 1)
        kill_tree(rec["pid"])
        r = self.ccx("resume", run_id, "go on", env={"FAKE_STATUS": "done"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls()[-1]["argv"][:3], ["exec", "resume", rec["session_id"]])

    def test_stop_after_ccx_died_records_the_usage_too(self):
        run_id, rec = self.start_and_kill_ccx()
        out = json.loads(self.ccx("stop", run_id).stdout)
        self.assertEqual((out["kind"], out["killed"]), ("user_stopped", True))
        a = self.record(run_id)["attempts"][-1]
        self.assertEqual(a["kind"], "user_stopped")
        self.assertGreater(a["usage"]["output_tokens"], 0)
        self.assertEqual(len(self.rows(run_id)), 1)

    def test_no_heartbeat_when_pid_cant_be_checked(self):
        p = Paths(self.hub)
        run_id = time.strftime("%Y%m%d-%H%M%S-") + "beat"
        d = p.runs / run_id
        d.mkdir(parents=True)
        ledger.write_record(d, {"run_id": run_id, "to": "codex", "state": "running", "attempts": [], "ts": time.time(),
                                "host": "another-machine", "ccx_pid": 1})
        now = time.time()
        self.assertEqual(recover.sweep(p, now=now), [])                         # fresh: left alone
        self.assertEqual(recover.sweep(p, now=now + recover.STALE_SEC + 5), [run_id])
        self.assertEqual(self.record(run_id)["state"], "interrupted")

    def test_ctrl_c_in_ccx_records_a_killed_attempt(self):
        if os.name == "nt":
            self.skipTest("CTRL_C to a console process group: covered on POSIX (SIGINT)")
        import signal
        r = subprocess.Popen([sys.executable, str(ROOT / "ccx.py"), "run",
                              "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                              "--no-ab", "x"], cwd=self.work, env={**self.env, "FAKE_STATUS": "hang",
                                                                    "FAKE_HANG_S": "60"},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        runs = self.hub / "ccx" / "runs"
        rec = wait_for(lambda: runs.exists() and any((d / "run.json").exists() for d in runs.iterdir()) and
                       (x := json.loads(next(d for d in runs.iterdir() if (d / "run.json").exists())
                                        .joinpath("run.json").read_text(encoding="utf-8"))).get("session_id") and x)
        time.sleep(2.5)
        r.send_signal(signal.SIGINT)
        r.wait(30)
        rec = self.record(rec["run_id"])
        self.assertEqual((rec["state"], rec["kind"]), ("interrupted", "killed"))
        self.assertEqual(rec["attempts"][-1]["kind"], "killed")
        self.assertGreater(rec["attempts"][-1]["usage"]["output_tokens"], 0)
        self.assertFalse(pid_alive(rec["pid"]))
        self.assertEqual(len(self.rows(rec["run_id"])), 1)


class TestKilledQueue(RecoverEnv):
    def kill_q_run(self):
        """`ccx q run` with one piece, its whole process tree killed mid-run (r2 group 9, 4-I)."""
        it = json.loads(self.ccx("q", "add", "x", "--brief", "implement x", "--to", "codex", "--minutes", "5").stdout)
        proc = subprocess.Popen([sys.executable, str(ROOT / "ccx.py"), "q", "run", "--from", "claude"], cwd=self.work,
                                env={**self.env, "FAKE_STATUS": "hang", "FAKE_HANG_S": "60"},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **group_flags())
        runs = self.hub / "ccx" / "runs"

        def started():
            for d in runs.iterdir() if runs.exists() else []:
                rec = self.record(d.name)
                if rec.get("label") == f"q:{it['id']}" and rec.get("session_id") and rec.get("pid"):
                    return rec
        rec = wait_for(started)
        self.assertTrue(rec)
        time.sleep(2.5)                                   # the fake's session file grows every 2 s
        kill_tree(proc.pid)                               # Windows: the whole tree (taskkill /T)
        kill_tree(rec["pid"])                             # POSIX: the sub-agent has a process group of its own
        proc.wait(30)
        self.assertTrue(wait_for(lambda: not pid_alive(rec["ccx_pid"]) and not pid_alive(rec["pid"]), 10))
        return it, rec

    def test_resume_closes_the_killed_run_and_counts_its_spend(self):
        it, rec = self.kill_q_run()
        self.assertEqual(self.record(rec["run_id"])["state"], "running")
        r = self.ccx("q", "resume", "--from", "claude", env={"FAKE_STATUS": "done"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        old = self.record(rec["run_id"])
        self.assertEqual((old["state"], old["attempts"][-1]["kind"]), ("interrupted", "killed"))
        self.assertEqual(len(self.rows(rec["run_id"])), 1)             # its spend reached the ledger
        killed = old["attempts"][-1]["ae_usd"]
        self.assertGreater(killed, 0)
        item = json.loads(self.ccx("q", "ls").stdout)["items"][0]
        self.assertEqual(item["status"], "done")
        self.assertGreaterEqual(item["cost_usd"], killed)               # the queue counts it too

    def test_resume_continues_the_killed_session(self):
        it, rec = self.kill_q_run()
        r = self.ccx("q", "resume", "--from", "claude", env={"FAKE_STATUS": "done"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["restored"][it["id"]], "resumed")
        last = self.calls()[-1]
        self.assertEqual(last["argv"][:3], ["exec", "resume", rec["session_id"]])   # not started over
        self.assertIn("ccx was stopped while you were working", last["prompt"])
