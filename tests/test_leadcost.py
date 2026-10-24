"""J1/J2: what the lead re-reads every turn, part by part, and the turns where its cache broke (fake logs only)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import leadcost  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402


def asst(i, ts, write, read, model="claude-opus-5-5"):
    return {"type": "assistant", "timestamp": ts, "sessionId": "s",
            "message": {"id": f"m{i}", "model": model,
                        "usage": {"input_tokens": 5, "cache_creation_input_tokens": write,
                                  "cache_read_input_tokens": read, "output_tokens": 50}}}


def write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


class TestClaude(Env):
    def test_breakdown_from_shape_and_attachments(self):
        tools = [{"name": "Bash", "description": "x" * 4000},
                 {"name": "mcp__browser__click", "description": "y" * 8000},
                 {"name": "mcp__browser__type", "description": "y" * 8000}]
        rows = [{"type": "api-request-shape", "shape": {"system": [{"text": "s" * 4000}], "tools": tools}},
                {"type": "attachment", "attachment": {"type": "instructions",
                                                      "files": [{"path": "/p/CLAUDE.md", "content": "规" * 3000}]}},
                {"type": "attachment", "attachment": {"type": "skill_listing", "content": "- a: b\n" * 200}},
                {"type": "attachment", "attachment": {"type": "hook_additional_context", "content": ["hi"]}},
                asst(0, "2026-10-24T10:00:00Z", 10_000, 0)]
        f = write(self.work / "t.jsonl", rows)
        b = leadcost.breakdown(Paths(self.hub), "claude", f)
        parts = {x["part"]: x["tokens"] for x in b["parts"]}
        self.assertEqual(b["first_turn_tokens"], 10_005)
        self.assertEqual(sum(parts.values()), 10_005)
        self.assertGreater(parts["MCP server browser (tool definitions)"], parts["built-in tool definitions"])
        self.assertIn("instruction file /p/CLAUDE.md", parts)
        self.assertTrue(any("MCP server browser" in a and "turn that server off" in a for a in b["advice"]))

    def test_cache_breaks_and_causes(self):
        rows = [{"type": "api-request", "cacheControl": [{"value": {"ttl": "1h"}}], "shapeHash": "a"},
                asst(0, "2026-10-24T10:00:00Z", 50_000, 0),
                asst(1, "2026-10-24T10:01:00Z", 2_000, 50_000),
                asst(2, "2026-10-24T12:00:00Z", 52_000, 0),                       # idle 2 h > 1 h
                asst(3, "2026-10-24T12:01:00Z", 60_000, 1_000, "claude-sonnet-5-5"),  # model switch
                {"type": "system", "subtype": "compact_boundary"},
                asst(4, "2026-10-24T12:02:00Z", 30_000, 0, "claude-sonnet-5-5"),     # compacted
                {"type": "assistant", "message": {"id": "e", "model": "<synthetic>", "usage": {"input_tokens": 0}}},
                asst(5, "2026-10-24T12:03:00Z", 1_000, 30_000, "claude-sonnet-5-5")]
        c = leadcost.cache_breaks(Paths(self.hub), "claude", write(self.work / "c.jsonl", rows))
        self.assertEqual(len(c["breaks"]), 3)
        self.assertIn("idle 119 min", c["breaks"][0]["why"][0])
        self.assertIn("model switched", c["breaks"][1]["why"][0])
        self.assertEqual(c["breaks"][2]["why"], ["the conversation was compacted"])
        self.assertGreater(c["extra_usd"], 0)
        self.assertEqual(c["causes"]["idle longer than the cache lives"], 1)


class TestCodex(Env):
    def test_breakdown_and_breaks(self):
        def tc(ts, inp, cached):
            return {"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": 9}}}}
        rows = [{"type": "session_meta", "payload": {"id": "x", "base_instructions": "b" * 8000}},
                {"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}},
                {"type": "response_item", "payload": {"type": "additional_tools", "tools": [
                    {"name": "functions", "tools": [{"name": "shell", "description": "z" * 2000},
                                                    {"name": "mcp__docs__read", "description": "z" * 6000}]}]}},
                {"type": "world_state", "payload": {"state": {"agents_md": {"directory": "/r", "text": "a" * 2000}}}},
                tc("2026-10-24T10:00:00Z", 6_000, 0),
                tc("2026-10-24T10:02:00Z", 60_000, 55_000),
                {"type": "compacted", "payload": {}},
                tc("2026-10-24T10:03:00Z", 40_000, 2_000)]
        f = write(self.work / "rollout.jsonl", rows)
        p = Paths(self.hub)
        b = leadcost.breakdown(p, "codex", f)
        parts = {x["part"]: x["tokens"] for x in b["parts"]}
        self.assertEqual(b["first_turn_tokens"], 6_000)
        self.assertIn("MCP server docs (tool definitions)", parts)
        self.assertIn("instruction file AGENTS.md (/r)", parts)
        c = leadcost.cache_breaks(p, "codex", f)
        self.assertEqual([x["why"] for x in c["breaks"]], [["the conversation was compacted"]])

    def test_cli_needs_a_session(self):
        r = self.ccx("lead", "--breakdown", "--as", "codex")
        self.assertEqual(r.returncode, 3)
        self.assertIn("no codex lead session", r.stdout)


if __name__ == "__main__":
    unittest.main()
