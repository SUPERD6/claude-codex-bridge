"""Which shared notes a sub-agent's brief gets (memory.for_brief, default word overlap): words lose the dots and
dashes at their ends (`JSON.` is `json`) and common English and Chinese words don't count. Checked offline on the L5
memory cases (scripts/eval/l5_memory.py); no model calls."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

import l5_memory  # noqa: E402
from ccx import memory  # noqa: E402
from ccx.config import Paths  # noqa: E402


class TestWords(unittest.TestCase):
    def test_punctuation_at_the_ends_off(self):
        w = memory._words("Write it as JSON. Then run ccx-run- and read a.b.c")
        self.assertIn("json", w)
        self.assertNotIn("json.", w)
        self.assertIn("ccx-run", w)
        self.assertIn("a.b.c", w)

    def test_stop_words_dropped(self):
        self.assertEqual(memory._words("the and with this that"), set())
        self.assertEqual(memory._words("我们这个"), {"们这"})
        self.assertIn("记忆", memory._words("我们的记忆"))


class TestL5Cases(unittest.TestCase):
    def pick(self, case: dict) -> list[str]:
        p = Paths(Path(tempfile.mkdtemp()))
        memory.ensure(p)
        for topic, text in l5_memory.DISTRACTORS:
            memory.add(p, text, by="claude", topic=topic)
        memory.add(p, case["memory"], by="claude", topic=case["kind"])
        return [e["text"] for e in memory.for_brief(p, case["brief"], by_kind=False)]

    def test_mem_json_note_reaches_the_brief(self):
        case = l5_memory.by_id("mem-json")      # missed 4 of 4 runs in round 3: `JSON.` and `the` decided it
        self.assertIn(case["memory"], self.pick(case))

    def test_every_case_gets_its_note_and_few_distractors(self):
        distractors = 0
        for case in l5_memory.CASES:
            got = self.pick(case)
            self.assertIn(case["memory"], got, case["id"])
            distractors += sum(t != case["memory"] for t in got)
        self.assertLessEqual(distractors, 2)    # was 12 over the 6 cases when "the" counted


if __name__ == "__main__":
    unittest.main()
