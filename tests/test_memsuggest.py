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


    def test_task_instructions_and_progress_lines_are_not_notes(self):
        from ccx.transcript import read_claude
        import tempfile
        session = [
            {"type": "user", "message": {"content": "在 `D:\\work\\proj` 继续 ccx 的统一施工顺序第 3–10 步，最终开源发布。"}},
            {"type": "user", "message": {"content": "#34 默认 tradeoff 改成 save。把 `ccx/review.py` 默认改成 off。"}},
            {"type": "user", "message": {"content": "原生能力优先、约束只放在边界上。"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text":
                "E8 真跑发现一个问题：只读子任务没去读文件。J6：STATUS 压成一页，原来 24 KB。"
                "PR #21 原来漏了一个测试。The root cause was a race on **run.json** while it is replaced。"
                "试验中发现的问题已经修好，提交号 `688e3ad`，已推送。\n## 顺带发现两个小 bug\n还没做 / 需要注意\n"
                "现在能找到，并沿用原来的模型。你原来的判断是对的，我发现上一条说偏了。"}]}},
        ]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s2.jsonl"
            f.write_text("".join(json.dumps(e) + "\n" for e in session), encoding="utf-8")
            got = [(c["kind"], c["text"]) for c in memsuggest.gather(read_claude(f), f)]
        self.assertEqual(got, [("preference", "原生能力优先、约束只放在边界上。"),
                               ("pitfall", "The root cause was a race on run.json while it is replaced。")])

    def test_one_off_instructions_fragments_and_questions_are_not_notes(self):
        users = ["#41、#42 绿了就默认 squash 合并。", "修这次的小问题：默认不要预演。", "然后每天你可以默认更新一次。",
                 "这个以后不要了，为什么 CI 没动过，不是自动的吗。", "Fix the build by default, please.",
                 "commit 9f3c2ab 以后不要回滚。", "以后不要弹出命令行窗口，默认隐藏。",
                 "就比如说我有几十个项目，我说得不准确，他以后也要能找到是哪个。"]
        texts = ["我们决定要不要再开一个会话，还在等你决定。", "Right now the quota is careful at 80% this week.",
                 "F9 推翻了提案 C4 的决定，要在记录里写一笔。", "还有一点要注意：评测时用的是最高思考强度，派活时只用 low。",
                 "注意：`.ccx/` 在 `.gitignore` 里，这个文件不会上传。", "发现 0.164 关掉开关后照样起子智能体，原来其实没起作用。"]
        d = {"agent": "claude", "users": users, "texts": texts}
        got = [c["text"] for c in memsuggest.gather(d, Path("x.jsonl"), limit=20)]
        self.assertEqual(got, [users[6], users[7], texts[3], texts[4], texts[5]])


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

    def test_only_the_first_three_the_persons_words_first(self):
        p = Paths(self.hub)
        memsuggest.add(p, [{"kind": "pitfall", "text": f"pitfall number {i} is long enough", "by": "claude",
                            "source": "s"} for i in range(3)]
                       + [{"kind": "decision", "text": "we decided to keep one queue file", "by": "claude", "source": "s"},
                          {"kind": "preference", "text": "from now on PR text in Chinese", "by": "user", "source": "s"}])
        out = self.j("mem", "suggestions")
        self.assertEqual([i["kind"] for i in out["pending"]], ["preference", "decision", "pitfall"])
        self.assertEqual(out["more"], 2)
        self.assertEqual(len(self.j("mem", "suggestions", "--all")["pending"]), 5)
        start = self.ccx("mem", "delta", "--as", "codex", "--peek").stdout
        self.assertIn("5 suggested note(s)", start)
        self.assertIn("from now on PR text in Chinese", start)
        self.assertIn("pitfall number 2", start)                     # newest pitfall
        self.assertNotIn("pitfall number 0", start)
        self.assertIn("--all", start)

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

    def test_who_wrote_who_used_report(self):
        p = Paths(self.hub)
        n = memory.add(p, "the parser tests need the fixtures folder", "codex", topic="parser")
        memory.add(p, "billing exports run on Fridays", "claude")
        memory.mark_used(p, [n["seq"]])                                         # before `by` was kept
        self.assertEqual(self.ccx("mem", "delta", "--as", "claude").returncode, 0)    # shows codex's note only
        self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "fix the parser tests")
        r = json.loads(self.ccx("mem", "report", "--days", "14", "--json").stdout)
        self.assertEqual(r["matrix"]["codex"], {"unknown": 1, "claude": 1, "codex": 1})   # start + brief
        self.assertNotIn("claude", r["matrix"])                               # the billing note: nobody
        self.assertEqual(r["via"], {"unknown": 1, "start": 1, "brief": 1})
        self.assertEqual(r["by_project"][self.work.name]["codex"]["codex"], 1)
        self.assertEqual((r["written"], r["written_never_used"]), ({"codex": 1, "claude": 1}, 1))
        text = self.ccx("mem", "report").stdout
        self.assertIn("written by \\ used by", text)
        self.assertIn("3 time(s)", text)


if __name__ == "__main__":
    unittest.main()
