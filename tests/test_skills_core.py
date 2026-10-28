"""The bundled skills keep teaching the lead every core feature, and every ccx command and flag they name exists.

Trimming a skill must not silently drop the part that tells the lead a core feature exists (the person's rule:
features may improve, never be lost). The keyword per feature is the command or field a lead would use."""
import argparse
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import ROOT  # noqa: E402

from ccx.cli import build_parser  # noqa: E402

SKILLS = ROOT / "skills"
NAMES = ("agent-delegate", "task-routing", "task-split", "task-checkpoint", "project-manager")

# core feature -> what a skill must still mention (each string in at least one SKILL.md, as a whole word)
CORE = {
    "three CLIs as lead or sub-agent, both ways": ("--from", "--to", "DeepSeek", "ccx handoff", "ccx fresh"),
    "shared and project memory": ("ccx mem add", "ccx project status"),
    "shared work context": ("--context", ".ccx/context.md", "ccx peek"),
    "board and discuss": ("ccx say", "ccx board", "ccx discuss"),
    "independent review and --check": ("--review", "--check", "needs_lead", "edited_tests", "check_broken"),
    "cost routing and escalation": ("ccx propose", "--tier", "--minutes", "--no-escalate", "--no-fallback",
                                    "task_routing.py"),
    "full ledger": ("ccx verify", "ccx stats", "ccx lead", "ccx report"),
    "stop, resume, undo, worktree": ("ccx stop", "ccx resume", "ccx task resume", "ccx undo", "--worktree",
                                     "ccx show <run_id> --wait"),
    "auto-archive": ("ccx archive",),
    "ccx ui": ("ccx ui",),
    "hub": ("ccx where", "ccx projects", "--project", "ccx autonomy", "ccx intake"),
    "pipelining": ("ccx q", "ccx q add", "ccx q run", "ccx q done", "--any"),
    "whole-workflow tiers": ("--tradeoff",),
    # result fields a lead looks at first (needs_lead / edited_tests are anchored above); the rules themselves
    # are guarded by their own wording in DECISION_RULES
    "decision rules": ("namecheck", "weak"),
}
# the Chinese notes say some English anchors in Chinese (checked as plain substrings)
ZH_WORDS: dict[str, str] = {}

# the rules a lead acts on when a result comes back, by phrases that occur only in the rule itself (whitespace
# folded): dropping one silently changes how work is accepted. English in SKILL.md, Chinese in README.zh.md.
DECISION_RULES = {
    "SKILL.md": ("do not send the same brief again", "Never `ccx resume` a run that is still running",
                 "Judge `kind` only from a final result", "`review_issues` there means no fix round",
                 "Don't `ccx resume` for it"),
    "README.zh.md": ("别再派同一份简报", "还在跑的运行不要 `ccx resume`", "`kind` 只按最终结果判断",
                     "仍是 `review_issues`，说明修改轮没跑成", "不要为此 `ccx resume`"),
}


def _docs() -> list[Path]:
    out = []
    for n in NAMES:
        d = SKILLS / n
        out += sorted(d.glob("*.md")) + sorted((d / "references").glob("*.md"))
    return out


def _subparsers(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next((a.choices for a in p._actions if isinstance(a, argparse._SubParsersAction)), {})


def _positionals(p: argparse.ArgumentParser) -> list[argparse.Action]:
    return [a for a in p._actions if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]


def mentioned(word: str, text: str) -> bool:
    """`word` as a whole token: `--from` is not satisfied by `--from-transcript`."""
    return re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text) is not None


def ccx_mentions(text: str) -> list[str]:
    """Each `ccx ...` inside inline code or a fenced block; `a; ccx b` counts as two."""
    spans = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    spans = [l for s in spans for l in s.splitlines()]
    spans += re.findall(r"`([^`\n]+)`", re.sub(r"```.*?```", "", text, flags=re.S))
    spans = [p for s in spans for p in s.split(";")]
    return [m.group(0) for s in spans for m in re.finditer(r"\bccx [a-z][^`]*", s)]


def problems(mention: str, top: dict) -> list[str]:
    """What in one `ccx ...` mention the parser does not know: command, subcommand, a fixed positional value, flag.
    Quoted text is the command's argument, not its options; `# ...` is a comment."""
    words = re.sub(r"\"[^\"]*\"|'[^']*'", '""', mention.split("#")[0]).split()
    if words[1] not in top:
        return [f"no command {words[1]!r}"]
    p, rest = top[words[1]], words[2:]
    nested = _subparsers(p)
    if nested and rest and re.fullmatch(r"[a-z][a-z-]*", rest[0]):
        if rest[0] in nested:
            p, rest = nested[rest[0]], rest[1:]
        elif not _positionals(p):
            return [f"no subcommand {rest[0]!r} of ccx {words[1]}"]
    out = []
    bare = []
    for w in rest:
        if w.startswith("-"):
            break
        bare.append(w)
    for a, w in zip(_positionals(p), bare):
        if a.choices and not w.startswith(("<", "[", '"')) and w not in a.choices:
            out.append(f"{w!r} is not one of {sorted(a.choices)}")
    opts = {o for a in p._actions for o in a.option_strings}
    out += [f"no flag {f}" for f in re.findall(r"(?<![\w-])--[a-z][a-z-]*", " ".join(words)) if f not in opts]
    return out


class TestCoreFeaturesTaught(unittest.TestCase):
    def test_each_core_feature_is_in_some_skill(self):
        text = "\n".join((SKILLS / n / "SKILL.md").read_text(encoding="utf-8") for n in NAMES)
        for feature, words in CORE.items():
            for w in words:
                self.assertTrue(mentioned(w, text), f"core feature '{feature}': no skill mentions {w!r}")

    def test_chinese_notes_teach_them_too(self):
        text = "\n".join((SKILLS / n / "README.zh.md").read_text(encoding="utf-8") for n in NAMES
                         if (SKILLS / n / "README.zh.md").exists())
        for feature, words in CORE.items():
            for w in words:
                ok = ZH_WORDS[w] in text if w in ZH_WORDS else mentioned(w, text)
                self.assertTrue(ok, f"core feature '{feature}': no README.zh.md mentions {ZH_WORDS.get(w, w)!r}")

    def test_decision_rules_kept(self):
        for name, phrases in DECISION_RULES.items():
            text = " ".join((SKILLS / "agent-delegate" / name).read_text(encoding="utf-8").split())
            for ph in phrases:
                self.assertIn(ph, text, f"agent-delegate/{name}: decision rule dropped")

    def test_no_stale_rules(self):
        """A4: no 70% quota gate (routing prices quota instead, E4), and no hand-editing of tiers.toml."""
        routing = (SKILLS / "task-routing" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("70%", routing)
        quota = next(a for a in _subparsers(build_parser())["run"]._actions if "--quota" in a.option_strings)
        self.assertNotIn("70%", quota.help)
        rubric = (SKILLS / "agent-delegate" / "references" / "rubric.md").read_text(encoding="utf-8")
        self.assertNotIn("<hub>/ccx/tiers.toml", rubric)
        self.assertNotIn("(`ccx config set`)", rubric)   # it has no per-agent tier key
        self.assertNotIn("from_quota", (SKILLS / "task-routing" / "data" / "priors.toml").read_text(encoding="utf-8"))

    def test_one_call_wait_taught(self):
        """A2: long work is one `ccx run ... --bg --wait 540` call, with the fallback `ccx show <run_id> --wait`."""
        for name in ("SKILL.md", "README.zh.md"):
            text = (SKILLS / "agent-delegate" / name).read_text(encoding="utf-8")
            for w in ("--bg --wait 540", "600000", "ccx show <run_id> --wait", "--worktree", "ccx q run"):
                self.assertIn(w, text, f"{name}: {w}")

    def test_queue_merge_step_taught_where_pieces_are_planned(self):
        """Parallel queue writers run in worktrees (#141): the skill text that plans several pieces must not say
        they all run in this checkout, and must teach the merge + `ccx q done` step for waiting pieces."""
        for name in ("SKILL.md", "README.zh.md"):
            text = (SKILLS / "agent-delegate" / name).read_text(encoding="utf-8")
            self.assertNotIn("runs them all in this checkout", text, name)
            self.assertNotIn("让所有块在当前检出里跑", text, name)
            for w in ("worktree", "`waiting`", "`unmerged`", "`dep_blocked`", "ccx q done <id> --ok 1"):
                self.assertIn(w, text, f"{name}: {w}")

    def test_whole_word(self):
        self.assertFalse(mentioned("--from", "use --from-transcript"))
        self.assertTrue(mentioned("--from", "`--from codex`"))


class TestEveryCommandExists(unittest.TestCase):
    def test_commands_and_flags_in_all_skill_docs(self):
        top = _subparsers(build_parser())
        seen = 0
        for doc in _docs():
            for mention in ccx_mentions(doc.read_text(encoding="utf-8")):
                self.assertEqual(problems(mention, top), [], f"{doc}: `{mention}`")
                seen += 1
        self.assertGreater(seen, 60)

    def test_catches_wrong_names(self):
        top = _subparsers(build_parser())
        self.assertTrue(problems("ccx project bogus", top))
        self.assertTrue(problems("ccx autonomy sett L2 --project x", top))
        self.assertTrue(problems("ccx autonomy set L9 --project x", top))
        self.assertTrue(problems("ccx run --nonexistent", top))
        self.assertEqual(problems('ccx run "add --nonexistent"', top), [])
        self.assertEqual(problems("ccx autonomy set L2 --project x", top), [])

    def test_mentions_parser(self):
        self.assertEqual(ccx_mentions("run `ccx where \"x\"` then\n```\nccx run --project a \"b\"\n```"),
                         ['ccx run --project a "b"', 'ccx where "x"'])
        self.assertEqual(ccx_mentions("`ccx run --bg x; ccx show 1 --wait`"),
                         ["ccx run --bg x", "ccx show 1 --wait"])


if __name__ == "__main__":
    unittest.main()
