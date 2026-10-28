"""E8: a handoff assembled by code from the outgoing lead's session file (fake transcripts, no real CLIs)."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import transcript  # noqa: E402
from test_ccx import ROOT, Env  # noqa: E402

SECRET = "sk-" + "a1B2" * 8


def _w(path: Path, events: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def codex_events(cwd: str, sid: str = "019a-main", originator: str = "codex_desktop") -> list[dict]:
    item = lambda it: {"type": "event_msg", "payload": {"type": "item_completed", "item": it}}  # noqa: E731
    return [
        {"type": "session_meta", "payload": {"id": sid, "cwd": cwd, "originator": originator}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"text": "# AGENTS.md instructions for x"}]}},
        item({"type": "UserMessage", "content": [{"text": "Add a --json flag to the report command."}]}),
        item({"type": "CommandExecution", "command": ["bash", "-lc", "pytest -q"], "exit_code": 1,
              "aggregated_output": "1 failed: test_report_json"}),
        item({"type": "FileChange", "changes": {"ccx/report.py": {}, "tests/test_report.py": {}}}),
        item({"type": "UserMessage", "content": [{"text": f"use my key {SECRET} if needed"}]}),
        item({"type": "AgentMessage", "phase": "final_answer",
              "content": [{"text": "Flag added; test_report_json still fails on the date format."}]}),
    ]


def claude_events() -> list[dict]:
    return [
        {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
        {"type": "user", "isCompactSummary": True, "message": {"content": "This session is being continued..."}},
        {"type": "user", "message": {"content": '<artifact-view-context a="1">{"mode":"edit"}</artifact-view-context>'}},
        {"type": "user", "message": {"content": "Rename the setup wizard's steps."}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "TodoWrite",
             "input": {"todos": [{"content": "rename steps", "status": "completed"},
                                 {"content": "update docs", "status": "in_progress"}]}},
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "ccx/setup.py"}},
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "python -m unittest"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t3", "is_error": True,
                                                  "content": "FAILED (errors=2)"}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "sub-agent"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Steps renamed; docs next."}]}},
    ]


class TestRead(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.t = Path(tempfile.mkdtemp())

    def test_codex(self):
        d = transcript.read_codex(_w(self.t / "r.jsonl", codex_events("/w")))
        self.assertEqual(d["users"][0], "Add a --json flag to the report command.")   # injected AGENTS.md skipped
        self.assertEqual(d["files"], ["ccx/report.py", "tests/test_report.py"])
        self.assertEqual(d["failed"][0]["cmd"], "pytest -q")
        self.assertIn("date format", d["final"])

    def test_codex_old_format(self):
        args = {"plan": [{"step": "write parser", "status": "completed"}, {"step": "tests", "status": "pending"}]}
        ev = [{"type": "event_msg", "payload": {"type": "user_message", "message": "Build the parser."}},
              {"type": "response_item", "payload": {"type": "function_call", "name": "update_plan",
                                                    "arguments": json.dumps(args)}},
              {"type": "response_item", "payload": {"type": "function_call", "name": "apply_patch",
                                                    "arguments": json.dumps({"input": "*** Add File: p.py\n"})}}]
        d = transcript.read_codex(_w(self.t / "old.jsonl", ev))
        self.assertEqual([s["status"] for s in d["plan"]], ["completed", "pending"])
        self.assertEqual(d["files"], ["p.py"])
        self.assertEqual(d["users"], ["Build the parser."])

    def test_claude(self):
        d = transcript.read_claude(_w(self.t / "s.jsonl", claude_events()))
        self.assertEqual(d["users"], ["Rename the setup wizard's steps."])          # /clear skipped
        self.assertEqual(d["plan"][1], {"step": "update docs", "status": "in_progress"})
        self.assertEqual(d["files"], ["ccx/setup.py"])
        self.assertEqual(d["failed"][0]["cmd"], "python -m unittest")
        self.assertEqual(d["final"], "Steps renamed; docs next.")                    # sidechain ignored

    def test_claude_plan_deltas(self):
        # the desktop app's plan tool sends the whole list once, then only changes (seen live, 2026-10-24)
        plan = lambda inp: {"type": "assistant", "message": {"content": [  # noqa: E731
            {"type": "tool_use", "id": "p", "name": "mcp__ccd_turn__update_plan", "input": inp}]}}
        items = [{"content": s, "status": "pending"} for s in ("read", "build", "test", "ship")]
        items[0]["status"] = "in_progress"
        ev = [plan({"items": items}), plan({"advance": True}), plan({"advance": True}), plan({"done": [4], "start": 3})]
        d = transcript.read_claude(_w(self.t / "p.jsonl", ev))
        self.assertEqual([s["status"] for s in d["plan"]], ["completed", "completed", "in_progress", "completed"])

    def test_build_redacts_and_caps(self):
        f = _w(self.t / "r.jsonl", codex_events("/w"))
        text = transcript.build(transcript.read_codex(f), self.t, f, unfinished="task-1: 2/4 steps")
        self.assertNotIn(SECRET, text)
        self.assertIn("[redacted]", text)
        for h in ("## Goal", "## Plan", "## Where it stopped", "## Files it changed", "## Unfinished tasks",
                  "## Full transcript", "Check before trusting"):
            self.assertIn(h, text)
        d = transcript.read_codex(f)
        d["users"] = ["x" * 5000] + ["y" * 900] * 6
        d["final"] = "z" * 5000
        self.assertLessEqual(len(transcript.build(d, self.t, f, max_chars=3000)), 3000)

    def test_plan_from_a_numbered_list(self):
        # no plan tool: the plan written in a message, as Codex luna wrote it in the E8 trial (2026-10-24)
        msg = lambda text, phase="commentary": {"type": "event_msg", "payload": {  # noqa: E731
            "type": "item_completed", "item": {"type": "AgentMessage", "phase": phase, "content": [{"text": text}]}}}
        ev = [{"type": "session_meta", "payload": {"id": "019a-x", "cwd": "/w", "originator": "codex_desktop"}},
              msg("计划：\n\n1. 查看 a.py 和 b.py\n2. 实现 is_palindrome 和 chunks\n3. 运行测试后停止"),
              msg("1 file changed, 2 tests"), msg("已完成 a、b。", "final_answer")]
        d = transcript.read_codex(_w(self.t / "n.jsonl", ev))
        self.assertEqual(d["session"], "019a-x")
        text = transcript.build(d, self.t, self.t / "n.jsonl")
        self.assertIn("no plan tool was used", text)
        self.assertIn("2. 实现 is_palindrome 和 chunks", text)
        self.assertEqual(transcript.plan_from_text(["no list here", "1. only one"]), [])

    def test_git_status_keeps_its_leading_space(self):
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.t, check=True)
        (self.t / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.t, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.t, check=True)
        (self.t / "a.py").write_text("x = 2\n", encoding="utf-8")
        f = _w(self.t / "s.jsonl", claude_events())
        self.assertIn("```\n M a.py", transcript.build(transcript.read_claude(f), self.t, f))   # unstaged, not "M "

    def test_redact(self):
        for s in ("ghp_" + "x" * 30, "Bearer " + "q" * 30, "api_key=hunter2hunter2", "AKIA" + "A" * 16):
            self.assertEqual(transcript.redact(f"a {s} b").count("[redacted]"), 1, s)
        self.assertEqual(transcript.redact("plain words"), "plain words")


class TestCommand(Env):
    def test_codex_from_transcript(self):
        here = str(self.work.resolve())
        _w(self.home_codex / "sessions" / "2026" / "rollout-1-sub.jsonl",
           codex_events(here, "019a-sub", originator="codex_exec"))                 # a headless sub-run: skipped
        _w(self.home_codex / "sessions" / "2026" / "rollout-0-main.jsonl", codex_events(here))
        r = self.ccx("handoff", "--from-transcript", "codex", "--to", "claude", "also check the docs")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn("rollout-0-main", out["from_transcript"])
        text = (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("Add a --json flag", text)
        self.assertIn("## Added by hand\nalso check the docs", text)
        self.assertNotIn(SECRET, text)

    def test_unknown_format_falls_back_to_a_model(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "new.jsonl", [{"kind": "turn", "who": "person", "said": "hi"}])
        out_file = self.work / ".ccx" / "handoff-by-model.md"
        env = {"FAKE_WRITE": f"{out_file}=## Goal\nparse the logs (from the model) {SECRET}"}
        r = self.ccx("handoff", "--from-transcript", "claude", "--to", "codex", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("model fallback", text)
        self.assertIn("parse the logs (from the model)", text)
        self.assertNotIn(SECRET, text)
        self.assertFalse(out_file.exists())                                   # the draft is cleaned up
        self.assertTrue(any("could not read" in c["prompt"] for c in self.calls()))
        r = self.ccx("handoff", "--from-transcript", "claude", "--to", "codex", "--no-model")
        self.assertIn("no user message found", (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8"))

    def test_claude_from_transcript_and_missing(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "abc.jsonl", claude_events())
        r = self.ccx("handoff", "--from-transcript", "claude", "--to", "codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("update docs (in_progress)", (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8"))
        r = self.ccx("handoff", "--from-transcript", "codex", "--to", "claude")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no codex session file", r.stderr + r.stdout)

    def test_handoff_lists_the_conversations_ccx_runs(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "abc.jsonl", claude_events())
        mine = json.loads(self.ccx("run", "--to", "codex", "--tier", "T1", "--mode", "read", "--check", "exit 0",
                                   "look at x", env={"CCX_LEAD_SESSION": "abc"}).stdout)["run_id"]
        other = json.loads(self.ccx("run", "--to", "codex", "--tier", "T1", "--mode", "read", "look at y",
                                    env={"CCX_LEAD_SESSION": "someone-else"}).stdout)["run_id"]
        self.assertEqual(self.ccx("handoff", "--from-transcript", "claude", "--to", "codex", "--no-model").returncode, 0)
        text = (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("## ccx runs from this conversation", text)
        self.assertIn(f"`{mine}` codex", text)
        self.assertIn("check passed, unjudged", text)
        self.assertNotIn(other, text)

    def test_worktree_inside_the_main_checkout(self):
        # Claude Code's .claude/worktrees/<name> sits inside the main checkout: the project layer (.ccx) is the
        # main checkout's, but the lead's session is filed under the worktree's own folder (seen live, 2026-10-24).
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        self.assertEqual(self.ccx("project", "init").returncode, 0)
        wt = self.work / ".claude" / "worktrees" / "wt1"
        wt.mkdir(parents=True)
        slug = lambda d: re.sub(r"[^A-Za-z0-9]", "-", str(d.resolve()))  # noqa: E731
        _w(self.home_claude / "projects" / slug(self.work) / "other.jsonl",
           [{"type": "user", "message": {"content": "Someone else's work in the main checkout."}}])
        _w(self.home_claude / "projects" / slug(wt) / "mine.jsonl", claude_events())
        r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), "handoff", "--from-transcript", "claude", "--to",
                            "codex", "--no-model"], cwd=wt, env=self.env, capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mine.jsonl", json.loads(r.stdout)["from_transcript"])
        text = (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("Rename the setup wizard", text)
        self.assertNotIn("Someone else's work", text)


class TestFresh(Env):
    def test_fresh_hands_over_to_the_same_tool(self):
        """J4: a long Claude conversation hands over to a fresh Claude conversation, which sees it once."""
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "abc.jsonl", claude_events())
        out = json.loads(self.ccx("fresh", "--as", "claude", "--no-model", "--note", "start with the docs").stdout)
        self.assertIn('claude "Continue the work', out["next"])
        doc = (self.work / ".ccx" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("from=claude to=claude", doc)
        self.assertIn("start with the docs", doc)
        first = self.ccx("mem", "delta", "--as", "claude").stdout
        self.assertIn("[ccx handoff to you from claude]", first)
        self.assertNotIn("handoff to you", self.ccx("mem", "delta", "--as", "claude").stdout)   # once
        self.assertNotIn("handoff to you", self.ccx("mem", "delta", "--as", "codex").stdout)    # not for codex

    def test_fresh_preserves_handwritten_latest_and_lists_new_handoff_once(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "abc.jsonl", claude_events())
        latest = self.work / ".ccx" / "handoff.md"
        latest.parent.mkdir(parents=True, exist_ok=True)
        original = b"Personal notes\r\nkeep these bytes\x00\n"
        latest.write_bytes(original)
        out = json.loads(self.ccx("fresh", "--as", "claude", "--no-model", "--note", "new handoff").stdout)
        self.assertEqual(latest.read_bytes(), original)
        self.assertEqual(out["latest"], out["handoff"])
        self.assertEqual(out["latest_skipped"], "hand-written .ccx/handoff.md kept")
        self.assertTrue(Path(out["handoff"]).exists())
        first = self.ccx("mem", "delta", "--as", "claude").stdout
        self.assertIn("[ccx handoff to you from claude]", first)
        self.assertNotIn("handoff to you", self.ccx("mem", "delta", "--as", "claude").stdout)

    def test_handwritten_edit_to_ccx_latest_survives_second_handoff(self):
        from ccx import project
        project.handoff(self.work, "claude", "claude", "first")
        latest = self.work / ".ccx" / "handoff.md"
        latest.write_text(latest.read_text(encoding="utf-8") + "\nPersonal edit\n", encoding="utf-8")
        before = latest.read_bytes()
        out = project.handoff(self.work, "claude", "claude", "second")
        self.assertEqual(latest.read_bytes(), before)
        self.assertEqual(out["latest"], out["handoff"])
        self.assertEqual(out["latest_skipped"], "hand-written .ccx/handoff.md kept")

    def test_unedited_ccx_latest_is_replaced_by_new_handoff(self):
        from ccx import project
        first = project.handoff(self.work, "claude", "claude", "first")
        second = project.handoff(self.work, "claude", "claude", "second")
        latest = self.work / ".ccx" / "handoff.md"
        self.assertEqual(latest.read_text(encoding="utf-8"), Path(second["handoff"]).read_text(encoding="utf-8"))
        self.assertNotEqual(first["handoff"], second["handoff"])
        self.assertNotIn("latest_skipped", second)

    def test_legacy_ccx_latest_without_history_is_kept_and_updated(self):
        """A handoff.md ccx wrote before handoffs/ existed is adopted into handoffs/ once, then updated."""
        from ccx import project
        d = self.work / ".ccx"
        d.mkdir(parents=True, exist_ok=True)
        latest = d / "handoff.md"
        old = b"<!-- ccx:handoff from=codex to=claude ts=2026-01-02T03:04:05 -->\n# Handoff\n\nold notes\n"
        latest.write_bytes(old)
        (d / "handoff.seen.json").write_text(json.dumps({"claude": ["handoff.md"]}), encoding="utf-8")
        out = project.handoff(self.work, "claude", "codex", "new")
        self.assertNotIn("latest_skipped", out)
        self.assertEqual(latest.read_text(encoding="utf-8"), Path(out["handoff"]).read_text(encoding="utf-8"))
        kept = d / "handoffs" / "2026-01-02T030405-codex-to-claude.md"
        self.assertEqual(kept.read_bytes(), old)
        self.assertIn(kept.name, json.loads((d / "handoff.seen.json").read_text(encoding="utf-8"))["claude"])
        self.assertEqual(project.pending_handoffs(self.work, "claude"), [])   # already shown as handoff.md

    def test_handwritten_latest_without_header_is_not_adopted(self):
        from ccx import project
        latest = self.work / ".ccx" / "handoff.md"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text("my own notes\n", encoding="utf-8")
        out = project.handoff(self.work, "claude", "codex", "new")
        self.assertEqual(out["latest_skipped"], "hand-written .ccx/handoff.md kept")
        self.assertEqual(len(list((self.work / ".ccx" / "handoffs").glob("*.md"))), 1)

    def test_hint_points_at_fresh(self):
        from ccx import context
        self.assertIn("ccx fresh", context.advice({"agent": "claude", "turns": 40, "last_turn_tokens": 300_000,
                                                   "usd_per_turn": 0.1}))


if __name__ == "__main__":
    unittest.main()
