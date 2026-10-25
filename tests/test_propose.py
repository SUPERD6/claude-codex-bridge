"""H12 offers to delegate (ccx propose) and J5/H10 the lead's own context read by itself in `ccx route` (fake CLIs)."""
import json
import unittest

from test_report import ReportEnv


class TestLeadContext(ReportEnv):
    def test_route_reads_the_lead_conversation(self):
        env = {"CLAUDE_CODE_SESSION_ID": "lead-ctx"}
        self.claude_transcript("lead-ctx", n=3)                 # each request read 10 + 1000 + 20000 tokens
        out = self.j("route", "--b", "4", "--to", "codex", "--lead", "claude:opus:high", env=env)
        sv, c = out["self_vs_delegate"], out["choice"]
        self.assertEqual((sv["ctx_source"], sv["lead_ctx_tokens"]), ("lead_session", 21010))
        self.assertEqual((c["ctx_source"], c["lead_ctx_tokens"]), ("lead_session", 21010))
        zero = self.j("route", "--b", "4", "--to", "codex", "--lead", "claude:opus:high", "--lead-ctx", "0", env=env)
        self.assertEqual(zero["self_vs_delegate"]["ctx_source"], "given")
        # more of your own turns when you do it yourself: a big conversation makes doing it here dearer
        gap = lambda r: r["self_vs_delegate"]["self_usd"] - r["self_vs_delegate"]["delegate_usd"]  # noqa: E731
        self.assertGreater(gap(out), gap(zero))
        none = self.j("route", "--b", "4", "--to", "codex", "--lead", "claude:opus:high",
                      env={"CLAUDE_CODE_SESSION_ID": "no-such-conversation"})
        self.assertEqual((none["self_vs_delegate"]["ctx_source"], none["self_vs_delegate"]["lead_ctx_tokens"]),
                         ("none", 0))

    def test_codex_lead(self):
        self.codex_rollout("thr-1")
        from ccx import context
        self.assertEqual(context.lead_now("codex", "thr-1", self.home_codex), 5000)
        self.assertIsNone(context.lead_now("codex", "other", self.home_codex))
        self.assertIsNone(context.lead_now("claude", None))


class TestPropose(ReportEnv):
    def test_offer_yes_delegate_judge_and_stats(self):
        env = {"CLAUDE_CODE_SESSION_ID": "lead-p"}
        self.claude_transcript("lead-p", n=2)
        big = self.j("propose", "--b", "4", "--kind", "code", "--to", "codex", "--lead", "claude:opus:high",
                     "--lead-ctx", "300000", "add a parser", env=env)
        self.assertTrue(big["proposal"].startswith("p"))
        self.assertEqual(big["worth_offering"], big["recommend"] == "delegate")
        if big["worth_offering"]:
            self.assertIn("Delegate it?", big["say"])
            self.assertIn(f"--proposal {big['proposal']}", big["next"])
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "--kind", "code",
                     "--proposal", big["proposal"], "add a parser", env=env)
        self.assertEqual(out["status"], "done", out)
        self.j("verify", out["run_id"], "--ok", "1")
        small = self.j("propose", "--b", "1", "--to", "codex", "--lead", "claude:haiku:low", "rename a var", env=env)
        self.j("propose", "--no", small["proposal"])
        self.assertNotEqual(self.ccx("propose", "--no", "p-none").returncode, 0)
        self.assertNotEqual(self.ccx("propose", "--b", "4", "x").returncode, 0)        # needs --lead
        self.j("run", "--from", "claude", "--to", "codex", "--b", "2", "--no-ab", "an evaluation run", env=env)
        s = self.j("propose", "--stats")
        pr = s["proposals"]
        self.assertEqual((pr["proposed"], pr["agreed"], pr["declined"], pr["delegated"], pr["judged"],
                          pr["held_up"]), (2, 1, 1, 1, 1, 1))
        self.assertEqual(pr["chain_complete_share"], 0.5)
        v = s["verdicts"]
        self.assertEqual((v["real_runs"], v["judged_by_lead_or_person"], v["coverage"]), (1, 1, 1.0))  # --no-ab left out
        row = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r.get("proposal") for r in row if r.get("run_id") == out["run_id"] and not r.get("type")],
                         [big["proposal"]])


if __name__ == "__main__":
    unittest.main()
