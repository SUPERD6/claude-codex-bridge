"""The bundled skills keep teaching the lead every core feature, and every ccx command and flag they name exists.

Trimming a skill must not silently drop the part that tells the lead a core feature exists (the person's rule:
features may improve, never be lost). The keyword per feature is the command or field a lead would use."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import ROOT  # noqa: E402
from test_skill_project_manager import _subparsers  # noqa: E402

from ccx.cli import build_parser  # noqa: E402

SKILLS = ROOT / "skills"
NAMES = ("agent-delegate", "task-routing", "task-split", "task-checkpoint", "project-manager")

# core feature -> what a skill must still mention (each string in at least one SKILL.md)
CORE = {
    "three CLIs as lead or sub-agent, both ways": ("--from", "--to", "DeepSeek", "ccx handoff", "ccx fresh"),
    "shared and project memory": ("ccx mem add", "ccx project status"),
    "shared work context": ("--context", ".ccx/context.md", "ccx peek"),
    "board and discuss": ("ccx say", "ccx board", "ccx discuss"),
    "independent review and --check": ("--review", "--check", "needs_lead", "edited_tests", "check_broken"),
    "cost routing and escalation": ("ccx propose", "--tier", "--minutes", "--no-escalate", "--no-fallback",
                                    "task_routing.py"),
    "full ledger": ("ccx verify", "ccx stats", "ccx lead", "ccx report"),
    "stop, resume, undo, worktree": ("ccx stop", "ccx resume", "ccx undo", "--worktree", "ccx show <run_id> --wait"),
    "auto-archive": ("ccx archive",),
    "ccx ui": ("ccx ui",),
    "hub": ("ccx where", "ccx projects", "--project", "ccx autonomy", "ccx intake"),
}


def _docs() -> list[Path]:
    out = []
    for n in NAMES:
        d = SKILLS / n
        out += sorted(d.glob("*.md")) + sorted((d / "references").glob("*.md"))
    return out


def ccx_mentions(text: str) -> list[str]:
    """Each `ccx ...` inside inline code or a fenced block; `a; ccx b` counts as two."""
    spans = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    spans = [l for s in spans for l in s.splitlines()]
    spans += re.findall(r"`([^`\n]+)`", re.sub(r"```.*?```", "", text, flags=re.S))
    spans = [p for s in spans for p in s.split(";")]
    return [m.group(0) for s in spans for m in re.finditer(r"\bccx [a-z][^`]*", s)]


class TestCoreFeaturesTaught(unittest.TestCase):
    def test_each_core_feature_is_in_some_skill(self):
        text = "\n".join((SKILLS / n / "SKILL.md").read_text(encoding="utf-8") for n in NAMES)
        for feature, words in CORE.items():
            for w in words:
                self.assertIn(w, text, f"core feature '{feature}': no skill mentions {w!r}")


class TestEveryCommandExists(unittest.TestCase):
    def test_commands_and_flags_in_all_skill_docs(self):
        top = _subparsers(build_parser())
        seen = 0
        for doc in _docs():
            for mention in ccx_mentions(doc.read_text(encoding="utf-8")):
                words = mention.split()
                self.assertIn(words[1], top, f"{doc}: {mention}")
                p = top[words[1]]
                nested = _subparsers(p)
                if nested and len(words) > 2 and words[2] in nested:
                    p = nested[words[2]]
                opts = {o for a in p._actions for o in a.option_strings}
                for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]*", mention):
                    self.assertIn(flag, opts, f"{doc}: {flag} in `{mention}`")
                seen += 1
        self.assertGreater(seen, 60)

    def test_split_on_semicolon(self):
        self.assertEqual(ccx_mentions("`ccx run --bg x; ccx show 1 --wait`"),
                         ["ccx run --bg x", "ccx show 1 --wait"])


if __name__ == "__main__":
    unittest.main()
