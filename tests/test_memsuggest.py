"""H5/H6: notes worth keeping gathered at a handoff (accepted by the person), this project's notes first at session
start, usage counts and long-unused notes (fake transcripts and hubs only)."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import memory, memsuggest  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402


def claude_session() -> list[dict]:
    return [
        {"type": "user", "message": {"content": "From now on keep the PR text in Chinese. Is the CI green?"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text":
            "We decided to keep the queue in one file. The cause was a stale lock in .ccx; removing it fixed the run. "
            "Here is the plan:"}]}},
        {"type": "user", "message": {"content": "以后不要提交 two-way-test-log.txt。"}},
    ]


class TestGather(unittest.TestCase):
    def test_kinds_and_filters(self):
        from ccx.transcript import read_claude
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s1.jsonl"
            f.write_text("".join(json.dumps(e) + "\n" for e in claude_session()), encoding="utf-8")
            got = memsuggest.gather(read_claude(f), f)
        kinds = [(c["kind"], c["text"]) for c in got]
        self.assertIn(("preference", "From now on keep the PR text in Chinese."), kinds)
        self.assertIn(("preference", "以后不要提交 two-way-test-log.txt。"), kinds)
        self.assertIn(("decision", "We decided to keep the queue in one file."), kinds)
        self.assertTrue(any(k == "pitfall" and "stale lock" in t for k, t in kinds))
        self.assertFalse(any(t.endswith("?") or t.endswith(":") for _, t in kinds))   # no questions, no lead-ins
        self.assertEqual(got[0]["kind"], "preference")                                 # the person's words first
        self.assertIn("claude session s1", got[0]["source"])


class TestFlow(Env):
    def write_session(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        d = self.home_claude / "projects" / slug
        d.mkdir(parents=True)
        (d / "abc.jsonl").write_text("".join(json.dumps(e) + "\n" for e in claude_session()), encoding="utf-8")

    def j(self, *args):
        r = self.ccx(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_suggest_accept_reject_and_the_start_hint(self):
        self.write_session()
        out = self.j("mem", "suggest", "--from-transcript", "claude")
        self.assertGreaterEqual(len(out["added"]), 3)
        again = self.j("mem", "suggest", "--from-transcript", "claude")
        self.assertEqual(again["added"], [])                                  # nothing twice
        self.assertIn("suggested note", self.ccx("mem", "delta", "--as", "codex", "--peek").stdout)
        first, second = out["added"][0]["id"], out["added"][1]["id"]
        acc = self.j("mem", "accept", str(first), "--text", "PR text in Chinese")
        self.assertEqual(acc["status"], "accepted")
        note = [e for e in memory.entries(Paths(self.hub)) if e["text"] == "PR text in Chinese"][0]
        self.assertEqual(note["by"], "user")
        self.assertIn("claude session abc", note["source"])
        self.assertEqual(self.j("mem", "reject", str(second))["status"], "rejected")
        self.assertNotEqual(self.ccx("mem", "accept", str(second)).returncode, 0)      # already decided
        left = self.j("mem", "suggestions")["pending"]
        self.assertNotIn(first, [i["id"] for i in left])

    def test_handoff_from_transcript_gathers_suggestions(self):
        self.write_session()
        out = self.j("handoff", "--from-transcript", "claude", "--to", "codex", "--no-model")
        self.assertGreaterEqual(out["suggested_notes"], 3)


class TestRelevanceAndUse(Env):
    def test_this_project_first_and_usage(self):
        p = Paths(self.hub)
        a = memory.add(p, "general note one", "codex")
        b = memory.add(p, "the work folder keeps its fixtures in tests/data", "codex", topic="work")
        new = memory.delta(p, "claude", advance=False)
        shown: list[int] = []
        text = memory.format_delta(new, project="work", shown=shown)
        self.assertLess(text.index(f"#{b['seq']}"), text.index(f"#{a['seq']}"))   # relevant first, though older
        memory.mark_used(p, shown)
        self.assertEqual(memory.usage(p)[b["seq"]]["n"], 1)
        r = self.ccx("mem", "search", "fixtures")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(memory.usage(p)[b["seq"]]["n"], 2)
        self.assertEqual(memory.unused(p), [])                                   # all recent
        self.assertEqual([e["seq"] for e in memory.unused(p, days=-1)], [a["seq"], b["seq"]])


if __name__ == "__main__":
    unittest.main()
