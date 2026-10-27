"""F10–F14: a sub-agent's own sub-agents — limits on spend and quota, not on head count (fake CLIs only)."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import subagents  # noqa: E402
from ccx.leadcost import LADDER  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestPlan(unittest.TestCase):
    def test_left_to_the_tool_unless_quota_is_tight_or_a_number_is_given(self):
        self.assertEqual(subagents.plan("codex", "gpt-6.1-sol", "auto", {}, LADDER),
                         {"threads": None, "model": None, "why": "left to the tool"})
        snug = subagents.plan("codex", "gpt-6.1-sol", "auto", {"codex": 0.85}, LADDER)
        self.assertEqual((snug["threads"], snug["model"]), (2, None))
        tight = subagents.plan("codex", "gpt-6.1-sol", "auto", {"codex": 2.27}, LADDER)
        self.assertEqual((tight["threads"], tight["model"]), (1, "gpt-6-luna"))    # F13: one rung down
        given = subagents.plan("codex", "gpt-6-luna", "4", {"codex": 2.27}, LADDER)
        self.assertEqual((given["threads"], given["model"]), (4, None))           # already the cheapest rung

    def test_spec_and_cap_and_parts(self):
        self.assertEqual(subagents.parse_spec("OFF"), "off")
        with self.assertRaises(ValueError):
            subagents.parse_spec("many")
        self.assertEqual(subagents.cap_usd(None, {}), 2.0)
        self.assertEqual(subagents.cap_usd(0.3, {"subagents": {"max_usd": 5}}), 0.3)
        self.assertTrue(subagents.has_parts("Do these:\n1. a.py\n2. b.py\n3. c.py"))
        self.assertFalse(subagents.has_parts("Fix the bug in a.py and add a test."))


class TestRuns(Env):
    def last(self):
        return self.calls()[-1]

    def test_parallel_words_and_off(self):
        brief = "Write four modules:\n- a.py\n- b.py\n- c.py\n- d.py"
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", brief)
        self.assertNotIn("explicitly asked to use sub-agents", self.last()["prompt"])  # F14: listing parts is not enough
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--new", "--parallel", brief)
        self.assertIn("You are explicitly asked to use sub-agents", self.last()["prompt"])     # only --parallel asks
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--new", "--parallel",
                 "--subagents", "off", brief)
        c = self.last()
        self.assertNotIn("explicitly asked to use sub-agents", c["prompt"])
        self.assertIn("multi_agent", c["argv"])                                                 # --disable multi_agent
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--new", "--parallel", "one thing")
        self.assertIn("explicitly asked to use sub-agents", self.last()["prompt"])
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--new", "--subagents", "3", "x")
        self.assertIn("agents.max_concurrent_threads_per_session=3", self.last()["argv"])

    def test_claude_gets_the_agent_tool_only_for_write_runs(self):
        self.ccx("run", "--from", "codex", "--to", "claude", "--tier", "T2", "--mode", "read", "x")
        a = self.last()["argv"]
        self.assertNotIn("Agent", a[a.index("--tools") + 1])
        self.ccx("run", "--from", "codex", "--to", "claude", "--tier", "T2", "--mode", "write", "--no-subagents", "--new", "x")
        a = self.last()["argv"]
        self.assertNotIn("Agent", a[a.index("--tools") + 1])

    def test_claude_children_are_read_from_the_session_folder(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        d = self.home_claude / "projects" / slug / "sess1" / "subagents"
        d.mkdir(parents=True)
        msg = {"type": "assistant", "message": {"id": "a1", "model": "claude-haiku-5-5",
                                                "usage": {"input_tokens": 3, "cache_creation_input_tokens": 7000,
                                                          "output_tokens": 20}}}
        (d / "agent-x.jsonl").write_text(json.dumps(msg) + "\n" + json.dumps(msg) + "\n", encoding="utf-8")
        kids = subagents.claude_children("sess1", self.work, self.home_claude)
        self.assertEqual(len(kids), 1)                                  # one reply logged twice counts once
        self.assertEqual(kids[0]["usage"]["cache_write_tokens"], 7000)

    def test_spend_watch_uses_the_piece_budget(self):
        from ccx.config import Paths, load_config
        from ccx.delegate import _spend_watch
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        d = self.home_claude / "projects" / slug / "sess2" / "subagents"
        d.mkdir(parents=True)
        msg = {"type": "assistant", "message": {"id": "b1", "model": "claude-sonnet-5-5",
                                                "usage": {"input_tokens": 200_000, "output_tokens": 20_000}}}
        (d / "agent-y.jsonl").write_text(json.dumps(msg) + "\n", encoding="utf-8")
        p = Paths(self.hub)
        record = {"run_id": "r1", "session_id": "sess2"}
        spec = {"model": "sonnet"}
        why = _spend_watch(p, load_config(p), "claude", spec, record, 0, 0.10, self.work)()
        self.assertIn("cap $0.10, --budget", why)
        self.assertIn("ccx resume r1 --budget", why)
        tiny = _spend_watch(p, load_config(p), "claude", spec, record, 0, 0.0001, self.work)()
        self.assertIn("cap $0.0001", tiny)                               # not "$0.00" below a cent
        self.assertIsNone(_spend_watch(p, load_config(p), "claude", spec, record, 0, None, self.work)())  # $2 default

    def test_claude_result_counts_its_sub_agents(self):
        from ccx.runners import parse_claude
        res = {"type": "result", "session_id": "s", "structured_output": {"status": "done", "summary": "ok"},
               "usage": {"input_tokens": 4, "cache_creation_input_tokens": 11582, "cache_read_input_tokens": 10377,
                         "output_tokens": 914, "cache_creation": {"ephemeral_1h_input_tokens": 11582}},
               "modelUsage": {"claude-haiku-5-5": {"inputTokens": 8, "outputTokens": 1687,
                                                   "cacheReadInputTokens": 17414, "cacheCreationInputTokens": 19933}},
               "total_cost_usd": 0.0044}
        u = parse_claude(json.dumps(res), "", 0).usage
        self.assertEqual((u["cache_write_tokens"], u["cache_write_1h_tokens"], u["cached_input_tokens"],
                          u["output_tokens"]), (19933, 19933, 17414, 1687))


if __name__ == "__main__":
    unittest.main()
