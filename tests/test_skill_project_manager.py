"""The project-manager skill (proposal K3): `ccx skills find` finds it. That every ccx command and flag it names
exists in the parser is checked for all bundled skills in test_skills_core.py."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import ROOT, Env  # noqa: E402

SKILL = ROOT / "skills" / "project-manager"


class TestSkillFrontmatter(unittest.TestCase):
    def test_name_and_description(self):
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        meta = dict(l.split(":", 1) for l in head.strip().splitlines())
        self.assertEqual(meta["name"].strip(), "project-manager")
        desc = meta["description"].strip()
        self.assertTrue(40 < len(desc) <= 1024, desc)        # skill loaders cap descriptions at 1024 characters
        for word in ("ccx where", "ccx run --project", "agent-delegate"):
            self.assertIn(word, desc)

    def test_chinese_notes_link_the_skill(self):
        self.assertIn("(SKILL.md)", (SKILL / "README.zh.md").read_text(encoding="utf-8"))


class TestSkillsFind(Env):
    def test_found_by_its_words(self):
        for query in (["project", "manager"], ["总管"], ["ccx", "where", "dispatch"]):
            r = self.ccx("skills", "find", *query)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)[0]["skill"], "project-manager", query)


if __name__ == "__main__":
    unittest.main()
