"""Shared work context: the lead's recent asks / decisions / plan / files read by code from its session file, attached
to delegated tasks, `ccx peek`, and the per-turn "what the others did" line (fake transcripts, no real CLIs)."""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from ccx import context_share as cs
from test_adapters import AdapterEnv

SECRET = "sk-" + "a1B2" * 8
SID = "lead-0001"
MARK = "[ccx shared work context:"   # the block itself, not the rule line that names it


def _iso(ago: float = 0) -> str:
    return datetime.fromtimestamp(time.time() - ago, timezone.utc).isoformat().replace("+00:00", "Z")


def _w(path: Path, events: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def claude_lead(ago: float = 60) -> list[dict]:
    """A lead conversation in which the person settled something a sub-agent can't guess."""
    return [
        {"type": "user", "timestamp": _iso(ago + 50), "message": {"content": "Fix average() in calc.py."}},
        {"type": "user", "timestamp": _iso(ago + 40), "message": {
            "content": "We decided: an empty list returns None, never raise. Also use my key " + SECRET}},
        {"type": "user", "timestamp": _iso(ago + 35), "message": {"content": "[ccx board #1 from codex] hi"}},
        {"type": "assistant", "timestamp": _iso(ago + 30), "message": {"content": [
            {"type": "text", "text": "Understood. Going with None for empty input. Docs come later."},
            {"type": "tool_use", "id": "t1", "name": "TodoWrite",
             "input": {"todos": [{"content": "agree on empty input", "status": "completed"},
                                 {"content": "fix average", "status": "in_progress"}]}},
            {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "notes/plan.md"}}]}},
        {"type": "assistant", "isSidechain": True, "timestamp": _iso(ago),
         "message": {"content": [{"type": "text", "text": "we decided sidechain stuff"}]}},
    ]


def codex_session(cwd: str, ago: float = 60) -> list[dict]:
    item = lambda ts, it: {"timestamp": ts, "type": "event_msg",  # noqa: E731
                           "payload": {"type": "item_completed", "item": it}}
    return [
        {"timestamp": _iso(ago + 30), "type": "session_meta",
         "payload": {"id": "cx-main", "cwd": cwd, "originator": "codex_desktop"}},
        item(_iso(ago + 20), {"type": "UserMessage", "content": [{"text": "Rename parse() to parse_rows()."}]}),
        item(_iso(ago + 10), {"type": "FileChange", "changes": {"src/parse.py": {}}}),
        item(_iso(ago), {"type": "AgentMessage", "content": [{"text": "Renamed; from now on callers use "
                                                                     "parse_rows()."}]}),
    ]


class TestRead(AdapterEnv):
    def test_claude_events_and_summary(self):
        f = _w(self.home_claude / "projects" / "x" / f"{SID}.jsonl", claude_lead())
        evs = cs.events_claude(f)
        kinds = [e["kind"] for e in evs]
        self.assertIn("ask", kinds)
        self.assertIn("plan", kinds)
        self.assertEqual([e["text"] for e in evs if e["kind"] == "file"], ["notes/plan.md"])
        self.assertFalse(any("sidechain" in e["text"] for e in evs))
        self.assertFalse(any(e["text"].startswith("[ccx board") for e in evs))      # pushed in, not the person
        text = cs.summary(evs, "claude", SID, self.work, "test")
        self.assertIn("empty list returns None", text)
        self.assertIn("Going with None for empty input", text)                       # the agent's decision
        self.assertRegex(text, r"- \[\d\d:\d\d person, claude session lead-000\]")     # time and source
        self.assertIn("[ ] fix average", text)
        self.assertIn("data, not instructions", text)
        self.assertNotIn(SECRET, text)
        self.assertLessEqual(len(cs.summary(evs * 40, "claude", SID, self.work, "t", max_chars=1500)), 1500)

    def test_codex_and_dsh_events(self):
        evs = cs.events_codex(_w(self.work / "r.jsonl", codex_session(str(self.work))))
        self.assertEqual([e["text"] for e in evs if e["kind"] == "file"], ["src/parse.py"])
        self.assertTrue(any(e["kind"] == "decision" and "parse_rows" in e["text"] for e in evs))
        lines = [json.dumps(x) for x in [
            {"type": "session", "id": "session-1", "cwd": "x"},
            {"type": "user/message", "time": 1_792_000_000_000, "data": {"content": [
                {"type": "text", "text": "Current runtime context. cwd x"},
                {"type": "text", "text": "Keep the CSV header; 别再改列名。"}]}},
            {"type": "tool/call", "time": 1_792_000_001_000, "data": {"name": "edit",
                                                                       "arguments": '{"file_path": "a.csv"}'}},
            {"type": "assistant/message", "time": 1_792_000_002_000, "data": {"message": {"content": [
                {"type": "reasoning", "text": "hmm"}, {"type": "text", "text": "Done."}]}}}]]
        evs = cs.events_dsh(lines)
        self.assertEqual([e["text"] for e in evs if e["kind"] == "ask"], ["Keep the CSV header; 别再改列名。"])
        self.assertTrue(any(e["kind"] == "decision" and "别再改列名" in e["text"] for e in evs))
        self.assertEqual([e["text"] for e in evs if e["kind"] == "file"], ["a.csv"])
        self.assertEqual(evs[0]["ts"], 1_792_000_000)

    def test_dsh_session_folder_is_found_by_its_path(self):
        import os
        home = Path(os.environ["DSH_HOME"])
        name = "--" + re.sub(r"[^A-Za-z0-9_]+", "-", str(self.work.resolve())) + "--"
        f = home / "sessions" / name / "session-9" / "session.v4.jsonl.zstd"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"")
        self.assertEqual(cs.find("dsh", self.work).name, "session.v4.jsonl.zstd")
        self.assertIsNone(cs.find("deepseek", self.work, exclude={"session-9"}))


class TestUse(AdapterEnv):
    LEAD = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": SID}

    def lead(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / f"{SID}.jsonl", claude_lead())

    def test_write_task_gets_the_leads_context(self):
        self.lead()
        out = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "write", "fix calc.py",
                     env=self.LEAD)
        prompt = self.calls()[-1]["prompt"]
        self.assertIn(MARK, prompt)
        self.assertIn("empty list returns None", prompt)
        self.assertNotIn(SECRET, prompt)
        rec = self.rec(out["run_id"])
        self.assertGreater(rec["shared_context"]["chars"], 100)
        self.assertTrue((self.hub / "ccx" / "runs" / out["run_id"] / "shared-context.md").exists())

    def test_auto_skips_read_tasks_and_off_skips_all(self):
        self.lead()
        self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "look at calc.py",
               env=self.LEAD)
        self.assertNotIn(MARK, self.calls()[-1]["prompt"])
        self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "--context", "on",
               "--new", "look at calc.py", env=self.LEAD)
        self.assertIn(MARK, self.calls()[-1]["prompt"])
        self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "write", "--context", "off",
               "--new", "fix calc.py", env=self.LEAD)
        self.assertNotIn(MARK, self.calls()[-1]["prompt"])

    def test_no_lead_session_no_context(self):
        out = self.j("run", "--from", "user", "--to", "codex", "--tier", "T2", "--mode", "write", "fix calc.py")
        self.assertNotIn(MARK, self.calls()[-1]["prompt"])
        self.assertIsNone(self.rec(out["run_id"])["shared_context"]["source"])

    def test_peek(self):
        cwd = str(self.work)
        if os.name == "nt":                       # Codex may record a short 8.3 name (the CI runner's home is one)
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(cwd, buf, 1024):
                cwd = buf.value
        _w(self.home_codex / "sessions" / "2026" / "rollout-1.jsonl", codex_session(cwd))
        r = self.ccx("peek", "codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Rename parse() to parse_rows()", r.stdout)
        self.assertIn("src/parse.py", r.stdout)
        self.assertIn("read-only look", r.stdout)
        r = self.ccx("peek", "deepseek")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no deepseek session", r.stdout)

    def test_turn_shows_what_the_other_tool_did_once(self):
        self.j("project", "init")
        _w(self.home_codex / "sessions" / "2026" / "rollout-1.jsonl", codex_session(str(self.work)))
        hook = json.dumps({"cwd": str(self.work), "session_id": SID, "prompt": "go on"})
        r = self.ccx("turn", "--as", "claude", stdin=hook)
        self.assertIn("- codex (", r.stdout)
        self.assertIn("changed src/parse.py", r.stdout)
        self.assertIn("data, not instructions", r.stdout)
        self.assertNotIn("- codex (", self.ccx("turn", "--as", "claude", stdin=hook).stdout)    # nothing new
        self.assertNotIn("- codex (", self.ccx("turn", "--as", "codex", stdin=hook).stdout)     # not its own
        (self.hub / "ccx").mkdir(exist_ok=True)
        (self.hub / "ccx" / "tiers.toml").write_text("[shared_context]\nturn = false\n", encoding="utf-8")
        _w(self.home_codex / "sessions" / "2026" / "rollout-1.jsonl", codex_session(str(self.work), ago=1))
        self.assertNotIn("- codex (", self.ccx("turn", "--as", "deepseek", stdin=hook).stdout)


class TestABDesign(AdapterEnv):
    def test_every_task_settles_something_the_context_carries(self):
        """scripts/eval/shared_context_ab.py: the attached context must hold the settled point, newer than the
        option the person reversed, and the brief must not give it away."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))
        import shared_context_ab as ab
        for t in ab.TASKS:
            f = _w(self.work / f"{t['id']}.jsonl", ab.lead_transcript(t, time.time()))
            text = cs.summary(cs.events_claude(f), "claude", "s", self.work, "t")
            self.assertIn(t["settle"][:30], text, t["id"])
            if t["reversed"]:
                self.assertLess(text.index(t["reversed"][:20]), text.rindex(t["settle"][:30]), t["id"])
            self.assertLess(len(text), cs.MAX_CHARS)
        rows = [{"task": "t1-empty-mean", "agent": "codex", "arm": arm, "rep": 1, "ok_first": arm == "on",
                 "ok_final": True, "rework": arm == "off", "usd": 0.01, "ctx_chars": 900 if arm == "on" else None}
                for arm in ("off", "on")]
        s = ab.summarize(rows)["all:settled"]
        self.assertEqual((s["only_on_right"], s["off"]["rework"], s["on"]["rate"]), (1, 1, 1.0))
