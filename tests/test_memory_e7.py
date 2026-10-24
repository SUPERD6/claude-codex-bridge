"""Memory that doesn't go stale silently: sources, replacement, checks, search, a size cap at session start."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from ccx import memory
from ccx.config import Paths


class TestMemoryFreshness(unittest.TestCase):
    def setUp(self):
        self.p = Paths(Path(tempfile.mkdtemp()))
        memory.ensure(self.p)

    def test_source_and_replacement(self):
        a = memory.add(self.p, "Claude quota is only readable via --quota", by="claude")
        b = memory.add(self.p, "Claude quota is read from rate_limit_event", by="claude", source="ccx/quota.py",
                       supersedes=a["seq"])
        self.assertEqual(b["supersedes"], a["seq"])
        self.assertEqual([e["seq"] for e in memory.live_entries(self.p)], [b["seq"]])
        text = memory.format_delta([a, b])
        self.assertIn(f"(replaces #{a['seq']})", text)
        self.assertIn("[source: ccx/quota.py]", text)
        self.assertNotIn("only readable", text)                          # the old one is not pushed any more
        with self.assertRaises(ValueError):
            memory.add(self.p, "x", by="claude", supersedes=999)

    def test_stale_until_checked(self):
        e = memory.add(self.p, "the build uses tox", by="codex")
        lines = memory._journal(self.p).read_text(encoding="utf-8").splitlines()
        old = json.loads(lines[-1])
        old["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 40 * 86400))
        memory._journal(self.p).write_text(json.dumps(old) + "\n", encoding="utf-8")
        self.assertEqual([x["seq"] for x in memory.stale(self.p)], [e["seq"]])
        memory.verify(self.p, e["seq"])
        self.assertEqual(memory.stale(self.p), [])

    def test_search_and_cap(self):
        memory.add(self.p, "tests run with python -m pytest", by="codex", topic="build")
        memory.add(self.p, "docs are bilingual", by="claude")
        hits = memory.search(self.p, ["PYTEST"])
        self.assertEqual(len([h for h in hits if h["seq"]]), 1)
        many = [{"seq": i, "by": "codex", "topic": "t", "text": "x" * 200} for i in range(1, 40)]
        text = memory.format_delta(many)
        self.assertLess(len(text), memory.DELTA_CHARS + 400)
        self.assertIn("more: `ccx mem search", text)
        self.assertIn("#39", text.splitlines()[1])                        # newest first


if __name__ == "__main__":
    unittest.main()
