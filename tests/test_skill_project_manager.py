"""The project-manager skill (proposal K3): `ccx skills find` finds it, and every ccx command and flag it names
exists in the parser, so the skill can't drift from `ccx -h` silently."""
import argparse
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import ROOT, Env  # noqa: E402

from ccx.cli import build_parser  # noqa: E402

SKILL = ROOT / "skills" / "project-manager"
DOCS = (SKILL / "SKILL.md", SKILL / "README.zh.md")


def _subparsers(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next((a.choices for a in p._actions if isinstance(a, argparse._SubParsersAction)), {})


def ccx_mentions(text: str) -> list[str]:
    """Each `ccx ...` inside inline code or a fenced block, as one string."""
    spans = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    spans = [l for s in spans for l in s.splitlines()]
    spans += re.findall(r"`([^`\n]+)`", re.sub(r"```.*?```", "", text, flags=re.S))
    return [m.group(0) for s in spans for m in re.finditer(r"\bccx [a-z][^`]*", s)]


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


class TestCommandsExist(unittest.TestCase):
    def test_every_command_and_flag_is_in_the_parser(self):
        top = _subparsers(build_parser())
        seen = 0
        for doc in DOCS:
            for mention in ccx_mentions(doc.read_text(encoding="utf-8")):
                words = mention.split()
                self.assertIn(words[1], top, f"{doc.name}: {mention}")
                p = top[words[1]]
                nested = _subparsers(p)
                if nested and len(words) > 2 and words[2] in nested:
                    p = nested[words[2]]
                opts = {o for a in p._actions for o in a.option_strings}
                for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]*", mention):
                    self.assertIn(flag, opts, f"{doc.name}: {flag} in `{mention}`")
                seen += 1
        self.assertGreater(seen, 20)                              # the regex really found the commands

    def test_mentions_parser(self):
        self.assertEqual(ccx_mentions("run `ccx where \"x\"` then\n```\nccx run --project a \"b\"\n```"),
                         ['ccx run --project a "b"', 'ccx where "x"'])


class TestSkillsFind(Env):
    def test_found_by_its_words(self):
        for query in (["project", "manager"], ["总管"], ["ccx", "where", "dispatch"]):
            r = self.ccx("skills", "find", *query)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)[0]["skill"], "project-manager", query)


if __name__ == "__main__":
    unittest.main()
