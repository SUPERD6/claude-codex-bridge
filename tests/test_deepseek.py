"""DeepSeek as the fourth vendor (DeepSeek Harness `dsh`, DeepSeek through Codex) and the smaller API providers
(Kimi, GLM, Qwen, OpenRouter): argv, keys, vendor, daily caps and accounting, all against fake CLIs."""
import json
import os
import time
from unittest import mock

from test_adapters import AdapterEnv
from test_ccx import FAKES

from ccx.agents.dsh import parse_dsh

# a real key on the machine running the tests must not leak in
KEYS = {"DEEPSEEK_API_KEY": "", "MOONSHOT_API_KEY": "", "ZAI_API_KEY": "", "DASHSCOPE_API_KEY": "",
        "DASHSCOPE_ANTHROPIC_BASE_URL": "", "OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}


class DeepSeekEnv(AdapterEnv):
    def setUp(self):
        super().setUp()
        self.env.update(KEYS)
        self.env["CCX_DSH_BIN"] = str(FAKES / "fake_dsh.py")

    def spent(self, agent: str, usd: float):
        led = self.hub / "ccx" / "ledger.jsonl"
        led.parent.mkdir(parents=True, exist_ok=True)
        led.write_text(json.dumps({"run_id": "old", "ts": time.time(), "to": agent,
                                   "ae_by_agent": {agent: usd}}) + "\n", encoding="utf-8")


class TestDsh(DeepSeekEnv):
    def test_run_read_only_and_resume(self):
        out = self.j("run", "--from", "claude", "--to", "dsh", "--tier", "T2", "--mode", "read", "review x",
                     env={"DEEPSEEK_API_KEY": "sk-test"})
        self.assertEqual((out["agent"], out["status"]), ("dsh", "done"))
        c = self.calls()[-1]
        self.assertEqual(c["argv"][:2], ["--profile", "headless"])
        self.assertEqual(c["argv"][-2:], ["--json", "-"])                  # task on stdin, after the app flags
        self.assertEqual(c["patch"][0], {"id": "agent-default-model", "config": {
            "provider": "deepseek-official", "model": "deepseek-flash", "reasoningEffort": "high"}})
        self.assertIn({"id": "session-log-deepseek", "disabled": True}, c["patch"])   # no session-log upload
        self.assertEqual((c["permission"], c["telemetry"]), ("read-only", "DISABLED"))
        self.assertEqual(c["deepseek_key"], "sk-test")                     # its own key, from the environment
        self.assertIn("JSON schema", c["prompt"])
        rec = self.rec(out["run_id"])
        a = rec["attempts"][0]
        self.assertEqual((a["usage"]["input_tokens"], a["usage"]["cached_input_tokens"],
                          a["usage"]["cache_write_tokens"], a["usage"]["output_tokens"]), (1500, 7200, 50, 300))
        self.assertGreater(a["ae_usd"], 0)                                 # priced as deepseek-flash
        sid = rec["session_id"]
        self.assertTrue(sid.startswith("session-"))
        self.j("resume", out["run_id"], "one more thing")
        c2 = self.calls()[-1]
        self.assertEqual(c2["argv"][c2["argv"].index("--session-id") + 1], sid)

    def test_write_mode_and_escalation(self):
        out = self.j("run", "--from", "claude", "--to", "dsh", "--tier", "T2", "x",
                     env={"FAKE_STATUS": "blocked_then_done"})
        self.assertEqual(out["escalated"], "T2 -> T3")
        c = self.calls()[-1]
        self.assertEqual(c["permission"], "workspace-write")
        self.assertEqual(c["patch"][0]["config"]["reasoningEffort"], "max")

    def test_quota_falls_back_to_a_subscription_agent(self):
        out = self.j("run", "--from", "user", "--to", "dsh", "--tier", "T2", "x", env={"FAKE_STATUS_DSH": "quota"})
        self.assertNotEqual(out["agent"], "dsh")
        self.assertEqual([a["kind"] for a in self.rec(out["run_id"])["attempts"]][0], "quota")

    def test_daily_cap(self):
        self.spent("dsh", 5.0)
        r = self.ccx("run", "--from", "codex", "--to", "dsh", "--tier", "T2", "x")
        self.assertEqual(r.returncode, 3)
        self.assertIn("budget", r.stdout)

    def test_parse(self):
        lines = [{"type": "session", "sessionId": "s1"},
                 {"type": "status", "phase": "step_end", "usage": {"inputTokens": 10, "outputTokens": 2}},
                 {"type": "status", "phase": "turn_end", "reason": "error"}, {"type": "final", "text": ""}]
        oc = parse_dsh("\n".join(json.dumps(x) for x in lines), "dsh: LLM_ERROR: 401 invalid api key\n", 1)
        self.assertFalse(oc.ok)
        self.assertEqual((oc.session_id, oc.kind, oc.auth_problem), ("s1", "auth", True))
        self.assertIn("401", oc.error)
        self.assertEqual(oc.usage["input_tokens"], 10)

    def test_agents_lists_it_as_deepseek(self):
        rows = {r["agent"]: r for r in self.j("agents")["agents"]}
        self.assertEqual((rows["dsh"]["vendor"], rows["dsh"]["pay_per_token"]), ("deepseek", True))
        self.assertEqual(rows["dsh"]["daily_usd"], 1.0)
        for name in ("deepseek", "deepseek-codex"):
            self.assertEqual(rows[name]["vendor"], "deepseek")
        self.assertFalse(rows["kimi"]["ready"])                            # no key: takes no part
        self.assertEqual(rows["kimi"]["needs_env"], ["MOONSHOT_API_KEY"])

    def test_never_a_quota_fallback_or_reviewer(self):
        from ccx import agents, review
        self.assertNotIn("dsh", agents.others("claude", {}, only_installed=False))
        cfg = {"review": {"by": {}, "also": ["dsh:deepseek-flash:low", "codex:gpt-6-luna:low"]}}
        self.assertEqual([a for a, _, _ in review.reviewers(cfg, "claude", lambda a: True)], ["codex"])
        self.assertTrue(agents.same_vendor("dsh", "deepseek", {"providers": {"deepseek": {"agent": "claude"}}}))
        from ccx import discuss                                       # nor a default discussion participant
        self.assertEqual(discuss.participants({}, None, lambda: ["codex", "claude", "dsh"]), ["codex", "claude"])
        self.assertEqual(discuss.participants({}, ["dsh", "codex"]), ["dsh", "codex"])   # named: allowed


class TestDeepSeekThroughCodex(DeepSeekEnv):
    def test_codex_with_deepseek_model_provider(self):
        out = self.j("run", "--from", "claude", "--provider", "deepseek-codex", "x",
                     env={"DEEPSEEK_API_KEY": "sk-test", "OPENAI_API_KEY": "caller-openai"})
        self.assertEqual(out["agent"], "deepseek-codex")
        c = self.calls()[-1]
        argv = " ".join(c["argv"])
        self.assertIn('model_provider="deepseek"', argv)
        self.assertIn('model_providers.deepseek.base_url="https://api.deepseek.com/"', argv)
        self.assertIn('model_providers.deepseek.env_key="DEEPSEEK_API_KEY"', argv)   # the key itself never in argv
        self.assertIn('model_providers.deepseek.wire_api="responses"', argv)
        self.assertNotIn("sk-test", argv)
        self.assertEqual(c["argv"][c["argv"].index("-m") + 1], "deepseek-flash")
        self.assertIn("multi_agent", c["argv"])                     # its own sub-agents would ask for OpenAI models
        for f in ("apps", "plugins"):                                # every connector's tools: ~210k tokens a request
            self.assertEqual(c["argv"][c["argv"].index(f) - 1], "--disable")
        self.assertEqual((c["deepseek_key"], c["openai_key"]), ("sk-test", False))   # caller's OpenAI key dropped
        rec = self.rec(out["run_id"])
        self.assertGreater(rec["attempts"][0]["ae_usd"], 0)
        self.assertNotIn("sk-test", json.dumps(rec))

    def test_report_counts_it_as_deepseek(self):
        from ccx import report
        cfg = {"providers": {"deepseek-codex": {"agent": "codex", "vendor": "deepseek"}, "glm": {"agent": "claude"}}}
        self.assertEqual(report._stream({"agent": "deepseek-codex", "role": "sub"}, cfg), ("deepseek", "sub"))
        self.assertEqual(report._stream({"agent": "dsh", "role": "sub"}, cfg), ("deepseek", "sub"))
        self.assertEqual(report._stream({"agent": "glm", "role": "sub"}, cfg), ("other", "sub"))
        self.assertEqual(report._stream({"agent": "codex", "role": "sub"}, cfg), ("codex", "sub"))


class TestSmallProviders(DeepSeekEnv):
    def test_glm_through_claude_priced_from_its_own_table(self):
        out = self.j("run", "--from", "codex", "--provider", "glm", "x", env={"ZAI_API_KEY": "zk"})
        c = self.calls()[-1]
        self.assertEqual((c["base_url"], c["api_key"]), ("https://api.z.ai/api/anthropic", "zk"))
        self.assertIn("--bare", c["argv"])
        self.assertEqual(c["argv"][c["argv"].index("--model") + 1], "glm-5.3-flash")
        self.assertGreater(self.rec(out["run_id"])["attempts"][0]["ae_usd"], 0)     # [providers.glm] prices

    def test_glm_daily_cap(self):
        self.spent("glm", 1.0)
        r = self.ccx("run", "--from", "codex", "--provider", "glm", "x", env={"ZAI_API_KEY": "zk"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("budget", r.stdout)

    def test_qwen_base_url_from_the_environment(self):
        url = "https://ws1.ap-southeast-1.maas.aliyuncs.com/apps/anthropic"
        self.j("run", "--from", "codex", "--provider", "qwen", "x",
               env={"DASHSCOPE_API_KEY": "qk", "DASHSCOPE_ANTHROPIC_BASE_URL": url})
        self.assertEqual(self.calls()[-1]["base_url"], url)
        r = self.ccx("run", "--from", "codex", "--provider", "qwen", "x", env={"DASHSCOPE_API_KEY": "qk"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("DASHSCOPE_ANTHROPIC_BASE_URL", r.stdout)

    def test_unpriced_model_is_refused(self):
        n = len(self.calls())
        r = self.ccx("run", "--from", "codex", "--provider", "kimi", "x", env={"MOONSHOT_API_KEY": "mk"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("no price", r.stdout)                          # the daily cap could not hold
        self.assertEqual(len(self.calls()), n)                        # nothing ran, nothing spent

    def test_openrouter_needs_a_model(self):
        r = self.ccx("run", "--from", "codex", "--provider", "openrouter", "x", env={"OPENROUTER_API_KEY": "ok"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("--model", r.stdout)

    def test_only_providers_with_a_key_take_part(self):
        from ccx.commands.common import provider_agents
        from ccx.config import Paths, load_config
        env = {**{k: "" for k in KEYS}, "ZAI_API_KEY": "zk", "CCX_CLAUDE_BIN": str(FAKES / "fake_claude.py"),
               "CCX_CODEX_BIN": str(FAKES / "fake_codex.py")}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(provider_agents(load_config(Paths(self.hub))), ["glm"])
