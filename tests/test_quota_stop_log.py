"""H2: every quota stop leaves its evidence (what matched, the words around it) in <hub>/ccx/quota-stops.jsonl,
and `ccx quota` shows the latest. Fake CLIs only: no quota is spent to test it."""
import json

from test_ccx import Env

from ccx import quota


class TestQuotaStopLog(Env):
    def stops(self):
        f = self.hub / "ccx" / "quota-stops.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def test_codex_quota_stop_keeps_the_matching_words(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-fallback", "x", env={"FAKE_STATUS": "quota"})
        run_id = json.loads(r.stdout)["run_id"]
        [s] = self.stops()
        self.assertEqual((s["run_id"], s["agent"], s["model"], s["by"]), (run_id, "codex", "gpt-6-luna", "hint"))
        self.assertEqual(s["hint"], "429")
        self.assertIn("usage limit reached", s["text"])
        out = json.loads(self.ccx("quota").stdout)
        self.assertEqual(out["recent_quota_stops"][-1]["run_id"], run_id)

    def test_claude_quota_stop_keeps_the_rejected_event(self):
        self.ccx("run", "--from", "codex", "--to", "claude", "--model", "sonnet", "--effort", "low",
                 "--no-fallback", "x", env={"FAKE_STATUS": "quota"})
        [s] = self.stops()
        self.assertEqual((s["agent"], s["by"]), ("claude", "rate_limit_event"))
        self.assertEqual(s["event"], {"status": "rejected", "resetsAt": 1798000000})

    def test_other_failures_leave_nothing(self):
        self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "x",
                 env={"FAKE_STATUS": "auth"})
        self.assertEqual(self.stops(), [])
        self.assertNotIn("recent_quota_stops", json.loads(self.ccx("quota").stdout))

    def test_evidence_without_a_known_hint_says_so(self):
        self.assertEqual(quota.stop_evidence("codex", "", "", "something else"), {"by": "unknown"})
