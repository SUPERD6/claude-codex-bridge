"""L1-L3: BM25 ranking for `ccx mem search` and briefs, five fixed kinds behind [memory] by_kind, scene blocks by
project (`ccx mem compact --by project`). By default (by_kind off), a session start and a brief get what they got."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import memory_bench as mb  # noqa: E402
from ccx import memory  # noqa: E402
from ccx.config import Paths, set_setting  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestBm25(unittest.TestCase):
    def setUp(self):
        self.p = Paths(Path(tempfile.mkdtemp()))
        memory.ensure(self.p)

    def test_rare_word_wins_and_not_every_word_needed(self):
        for t in ("the build uses tox", "the build uses make", "the build uses gradle on the mobile app",
                  "release builds need the signing step"):
            memory.add(self.p, t, by="codex")
        hits = memory.search(self.p, ["build", "gradle"])
        self.assertIn("gradle", hits[0]["text"])                        # the rare word decides the order
        self.assertEqual(len(hits), 4)                                  # "build" (or "builds") alone is enough
        self.assertGreater(hits[0]["score"], hits[1]["score"])
        self.assertEqual(len(memory.search(self.p, ["build", "gradle"], all_words=True)), 1)   # the old filter
        self.assertEqual(len(memory.search(self.p, ["build"], limit=2)), 2)
        self.assertEqual(memory.search(self.p, ["nothing-like-this"]), [])

    def test_old_hits_are_still_found(self):
        """Anything the every-word filter found, BM25 finds too (a substring counts half)."""
        memory.add(self.p, "the snapshot stays under 3 KB", by="claude")
        memory.add(self.p, "注意这个坑：迁移没跑", by="claude")
        self.assertEqual(len(memory.search(self.p, ["snap"])), 1)
        self.assertEqual(len(memory.search(self.p, ["坑"])), 1)
        self.assertEqual(len(memory.search(self.p, ["ci"])), 0)

    def test_tokens(self):
        self.assertEqual(memory._tokens("Docs are bilingual."), ["docs", "bilingual"])
        self.assertIn("pytest", memory._tokens("pytest.ini"))
        self.assertEqual(memory._tokens("共享记忆"), ["共享", "享记", "记忆"])

    def test_fixed_query_set(self):
        """The before/after numbers quoted in the PR: relevant notes among the first 3."""
        r = mb.run(self.p)
        t = r["total"]
        self.assertEqual(r["best"], 13)
        self.assertEqual((t["search_before"], t["search_after"]), (7, 11))
        self.assertEqual((t["brief_before"], t["brief_after"]), (11, 12))
        self.assertTrue(all(x["search_after"] >= x["search_before"] for x in r["rows"]))
        self.assertGreaterEqual(r["kinds_right"], 35)


class TestDefaultsUnchanged(unittest.TestCase):
    """By default (by_kind off) a brief picks exactly what it picked before."""

    def test_brief_pick_is_the_old_one(self):
        p = Paths(Path(tempfile.mkdtemp()))
        es = mb.load(p)
        self.assertFalse(memory.by_kind_on(p))
        for q, _rel in mb.QUERIES:
            got = [e["seq"] for e in memory.for_brief(p, q, k=10, budget=100_000)]
            self.assertEqual(got, mb.old_brief(es, q)[:10], q)

    def test_switch(self):
        p = Paths(Path(tempfile.mkdtemp()))
        set_setting(p, "memory.by_kind", "true")
        self.assertTrue(memory.by_kind_on(p))
        mb.load(p)
        picked = memory.for_brief(p, "mobile-app shipped store")
        self.assertTrue(picked)
        self.assertNotIn("event", [memory.kind_of(e) for e in picked])  # events are found by search only
        with self.assertRaises(ValueError):
            set_setting(p, "memory.by_kind", "maybe")


class TestKinds(unittest.TestCase):
    def test_parse_and_guess(self):
        self.assertEqual(memory.parse_kind("坑"), "pitfall")
        self.assertEqual(memory.parse_kind("Preference"), "preference")
        self.assertEqual(memory.parse_kind("decision"), "constraint")          # memsuggest's word
        with self.assertRaises(ValueError):
            memory.parse_kind("misc")
        self.assertEqual(memory.kind_of({"topic": "pitfall", "text": "x"}), "pitfall")
        self.assertEqual(memory.kind_of({"topic": "build", "text": "the build uses tox"}), "fact")
        self.assertEqual(memory.kind_of({"topic": "x", "text": "zzz"}), "other")
        self.assertEqual(memory.kind_of({"kind": "event", "topic": "pitfall", "text": "x"}), "event")

    def test_add_keeps_kind_and_old_lines_stay(self):
        p = Paths(Path(tempfile.mkdtemp()))
        memory.ensure(p)
        before = memory._journal(p).read_text(encoding="utf-8")
        e = memory.add(p, "billing exports run on Fridays", by="claude", kind="事件")
        self.assertEqual(e["kind"], "event")
        self.assertTrue(memory._journal(p).read_text(encoding="utf-8").startswith(before))
        with self.assertRaises(ValueError):
            memory.add(p, "another", by="claude", kind="nope")

    def test_start_filter(self):
        new = [{"seq": 1, "by": "codex", "topic": "general", "text": "用户希望回复先给结论"},
               {"seq": 2, "by": "codex", "topic": "general", "text": "mobile-app shipped 3.2 last week"},
               {"seq": 3, "by": "codex", "topic": "general", "text": "注意：迁移会失败"}]
        self.assertIn("#2", memory.format_delta(new))                               # default: everything
        text = memory.format_delta(new, kinds=memory.START_KINDS)
        self.assertIn("#1", text)
        self.assertNotIn("#2", text)
        self.assertNotIn("#3", text)
        self.assertEqual(memory.format_delta(new[1:], kinds=memory.START_KINDS), "")


class TestScenes(unittest.TestCase):
    def test_blocks_by_project(self):
        p = Paths(Path(tempfile.mkdtemp()))
        mb.load(p)
        journal = memory._journal(p).read_text(encoding="utf-8")
        sc = memory.scenes(p, mb.PROJECTS)
        self.assertEqual(sorted(sc), sorted(mb.PROJECTS))
        self.assertTrue(all("ml-train" in x or x.startswith("…") for x in sc["ml-train"]))
        for lines in sc.values():
            self.assertLessEqual(len("\n".join(lines)), memory.SCENE_CHARS + 120)
        self.assertEqual(memory._journal(p).read_text(encoding="utf-8"), journal)


class TestCli(Env):
    def test_add_kind_search_kinds_compact_by_project(self):
        r = self.ccx("mem", "add", "the release build needs the signing step", "--kind", "坑", "--topic", "work")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["kind"], "pitfall")
        self.ccx("mem", "add", "the build uses gradle")
        r = self.ccx("mem", "search", "signing", "build")
        hits = json.loads(r.stdout)["hits"]
        self.assertEqual(len(hits), 2)
        self.assertIn("signing", hits[0]["text"])
        self.assertEqual(len(json.loads(self.ccx("mem", "search", "signing", "build", "--all-words").stdout)["hits"]),
                         1)
        k = json.loads(self.ccx("mem", "kinds", "--list").stdout)
        self.assertEqual(k["counts"]["pitfall"], 1)
        self.assertFalse(k["by_kind"])
        p = Paths(self.hub)
        memory.mark_used(p, [1], project="work")                  # `work` is a project notes were used in
        r = self.ccx("mem", "compact", "--by", "project")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["projects"], 1)
        self.assertEqual(len(memory.entries(p)), 2)               # journal left alone
        self.assertIn("signing", memory.scene_block(p, "work"))

    def test_start_unchanged_by_default_and_scene_opt_in(self):
        p = Paths(self.hub)
        memory.add(p, "mobile-app shipped 3.2 last week", "codex", topic="work")
        memory.mark_used(p, [1], project="work")
        self.ccx("mem", "compact", "--by", "project")
        out = self.ccx("mem", "delta", "--as", "claude", "--peek").stdout
        self.assertIn("shipped 3.2", out)                        # default: an event is still pushed
        self.assertNotIn("[ccx shared memory: work]", out)
        set_setting(p, "memory.by_kind", "true")
        set_setting(p, "memory.start_scene", "true")
        out = self.ccx("mem", "delta", "--as", "claude", "--peek").stdout
        self.assertNotIn("new since your last session", out)    # by kind: the event waits for a search
        self.assertIn("[ccx shared memory: work]", out)


if __name__ == "__main__":
    unittest.main()
