"""v0.2 delegation: calibrated routing, explicit model/effort, early session ids, quota fallback,
timeouts, checkpoint integration and the learning loop (ccx verify). Fake CLIs only."""
import json
import subprocess
import sys
import unittest

from test_ccx import ROOT, Env

from ccx.runners import classify, parse_claude

CHECKPOINT = ROOT / "skills" / "task-checkpoint" / "scripts" / "checkpoint.py"


class V02(Env):
    def run_json(self, *args, env=None, code=None):
        r = self.ccx(*args, env=env)
        if code is not None:
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def record(self, run_id):
        return json.loads((self.hub / "ccx" / "runs" / run_id / "run.json").read_text(encoding="utf-8"))

    def routing_state(self):
        f = self.hub / "ccx" / "routing-state.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"counts": {}}


class TestRouting(V02):
    def test_rubric_uses_task_routing(self):
        out = self.run_json("run", "--from", "claude", "--files", "3", "--coupling", "cross",
                            "--clarity", "goal", "implement the parser", code=0)
        self.assertEqual(out["route"]["source"], "task-routing")
        agent, model, effort = out["route"]["rung"].split(":")
        self.assertEqual(out["agent"], agent)
        argv = self.calls()[-1]["argv"]
        self.assertIn(model, argv)

    def test_tiny_task_is_not_delegated(self):
        out = self.run_json("run", "--from", "claude", "--b", "0", "fix typo", code=0)
        self.assertFalse(out["delegated"])
        self.assertIn("do-it-yourself", out["advice"])
        self.assertEqual(self.calls(), [])

    def test_explicit_model_and_effort(self):
        out = self.run_json("run", "--from", "codex", "--model", "sonnet", "--effort", "high", "review", code=0)
        self.assertEqual(out["agent"], "claude")
        argv = self.calls()[-1]["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")

    def test_route_command_with_rubric(self):
        out = self.run_json("route", "--files", "9", "--coupling", "system", "--clarity", "unknown",
                            "--risk", "critical", "--novelty", "new", code=0)
        self.assertEqual(out["b"], 10)
        self.assertIn("rung", out)

    def test_explicit_rung_escalates_up_the_routing_ladder(self):
        out = self.run_json("run", "--from", "claude", "--model", "gpt-6.1-sol", "--effort", "medium",
                            "implement", env={"FAKE_STATUS": "blocked_then_done"}, code=0)
        self.assertEqual(out["status"], "done")
        rec = self.record(out["run_id"])
        self.assertEqual([a["rung"] for a in rec["attempts"]],
                         ["codex:gpt-6.1-sol:medium", "codex:gpt-6.1-sol:high"])
        self.assertEqual(rec["attempts"][1]["session_id"], rec["attempts"][0]["session_id"])


class TestFailures(V02):
    def test_quota_falls_back_to_other_agent(self):
        out = self.run_json("run", "--from", "user", "--to", "codex", "--tier", "T2", "implement",
                            env={"FAKE_STATUS_CODEX": "quota"}, code=0)
        self.assertEqual(out["agent"], "claude")
        rec = self.record(out["run_id"])
        self.assertEqual([a["kind"] for a in rec["attempts"]], ["quota", "ok"])
        self.assertEqual([a["agent"] for a in rec["attempts"]], ["codex", "claude"])

    def test_quota_without_fallback_says_how_to_resume(self):
        out = self.run_json("run", "--from", "user", "--to", "claude", "--tier", "T2", "--no-fallback",
                            "implement", env={"FAKE_STATUS": "quota"}, code=2)
        self.assertEqual(out["kind"], "quota")
        self.assertIn("ccx resume", out["hint"])
        self.assertEqual(len(self.record(out["run_id"])["attempts"]), 1)

    def test_timeout_keeps_session_for_resume(self):
        (self.hub / "ccx").mkdir(exist_ok=True)
        # 5 s: the fake must start and print its session id before the kill, even on a busy machine
        (self.hub / "ccx" / "tiers.toml").write_text("[defaults]\ntimeout_sec = 5\n", encoding="utf-8")
        out = self.run_json("run", "--from", "claude", "--tier", "T2", "--no-fallback", "long job",
                            env={"FAKE_STATUS": "hang"}, code=2)
        self.assertEqual(out["kind"], "timeout")
        rec = self.record(out["run_id"])
        self.assertTrue(rec["session_id"])          # captured from the first event, before the kill

    def test_classify(self):
        self.assertEqual(classify("HTTP 429 rate limit"), "quota")
        self.assertEqual(classify("401 Unauthorized"), "auth")
        self.assertEqual(classify("segfault"), "error")

    def test_parse_claude_stream(self):
        lines = [{"type": "system", "subtype": "init", "session_id": "s1"},
                 {"type": "assistant", "message": {}},
                 {"type": "result", "is_error": False, "session_id": "s1", "structured_output": {"status": "done"},
                  "usage": {"input_tokens": 1, "cache_read_input_tokens": 5, "output_tokens": 2},
                  "total_cost_usd": 0.01}]
        oc = parse_claude("\n".join(json.dumps(x) for x in lines), "", 0)
        self.assertTrue(oc.ok)
        self.assertEqual(oc.session_id, "s1")
        self.assertEqual(oc.usage["cached_input_tokens"], 5)


class TestLearning(V02):
    def test_definite_failure_is_learned_automatically(self):
        out = self.run_json("run", "--from", "claude", "--to", "codex", "--b", "4", "--no-escalate", "x",
                            env={"FAKE_STATUS": "blocked"}, code=0)
        self.assertEqual(out["status"], "blocked")
        st = self.routing_state()
        self.assertEqual(sum(st["counts"].values()), 1)
        self.assertEqual(self.record(out["run_id"])["learned"], "auto")

    def test_self_checked_success_then_lead_verdict(self):
        out = self.run_json("run", "--from", "claude", "--to", "codex", "--b", "4", "x", code=0)
        self.assertEqual(sum(self.routing_state()["counts"].values()), 1)   # codex fake ran pytest
        v = self.run_json("verify", out["run_id"], "--ok", "1", code=0)
        self.assertEqual(v["learned"], [])                                   # agreed: no double count
        v = self.run_json("verify", out["run_id"], "--ok", "0", "--note", "tests were wrong", code=0)
        self.assertTrue(v["learned"])                                        # lead overrides
        self.assertEqual(sum(self.routing_state()["counts"].values()), 2)
        rows = [json.loads(l) for l in (self.hub / "ccx" / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(sum(1 for r in rows if r.get("type") == "verify"), 2)
        self.assertEqual(self.ccx("stats").returncode, 0)                    # verify rows don't break stats

    def test_unchecked_success_waits_for_verify(self):
        out = self.run_json("run", "--from", "codex", "--to", "claude", "--b", "4", "x", code=0)
        self.assertIsNone(self.record(out["run_id"])["learned"])
        self.assertEqual(self.routing_state()["counts"], {})
        self.run_json("verify", out["run_id"], "--ok", "1", code=0)
        self.assertEqual(self.record(out["run_id"])["learned"], "lead")

    def test_minutes_calibrate_split_horizon(self):
        out = self.run_json("run", "--from", "claude", "--to", "codex", "--b", "4", "--minutes", "60",
                            "--model", "gpt-6.1-sol", "--effort", "medium", "x", code=0)
        self.assertEqual(self.record(out["run_id"])["learned"], "auto")
        st = json.loads((self.hub / "ccx" / "split-state.json").read_text())
        self.assertIn("codex:gpt-6.1-sol:medium", st["ln_h50"])

    def test_plan_wrapper(self):
        r = self.ccx("plan", "size", "--minutes", "240", "--rung", "codex:gpt-6.1-sol:medium")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pieces", r.stdout)


class TestCheckpoint(V02):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        r = subprocess.run([sys.executable, str(CHECKPOINT), "init", "--title", "big job", "--step", "part a"],
                           cwd=self.work, capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.task = r.stdout.strip()

    def step(self):
        plan = json.loads((self.work / ".ccx" / "tasks" / self.task / "plan.json").read_text(encoding="utf-8"))
        return plan["steps"][0]

    def test_session_saved_and_verify_marks_done(self):
        out = self.run_json("run", "--from", "claude", "--to", "claude", "--tier", "T2",
                            "--task", self.task, "--step", "1", "do part a", code=0)
        s = self.step()
        self.assertEqual(s["status"], "doing")
        self.assertEqual(s["session"], self.record(out["run_id"])["session_id"])
        self.run_json("verify", out["run_id"], "--ok", "1", code=0)
        self.assertEqual(self.step()["status"], "done")

    def test_quota_marks_step_failed_with_reason(self):
        self.run_json("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--no-fallback",
                      "--task", self.task, "--step", "1", "do part a", env={"FAKE_STATUS": "quota"}, code=2)
        s = self.step()
        self.assertEqual(s["status"], "failed")
        self.assertEqual(s["reason"], "quota")
        self.assertIn("ccx resume", s["note"])


if __name__ == "__main__":
    unittest.main()
