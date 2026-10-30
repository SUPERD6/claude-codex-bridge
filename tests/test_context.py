"""H10: how much the lead's own conversation re-reads each turn, and the one-line hint (fake transcripts only)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import context  # noqa: E402
from ccx.config import Paths  # noqa: E402
from ccx.sync import sync_all, uninstall  # noqa: E402
from test_ccx import Env  # noqa: E402


def transcript(path: Path, turns: int, cached: int) -> Path:
    lines = [{"type": "user", "message": {"content": "hi"}}]
    for i in range(turns):
        lines.append({"type": "assistant", "sessionId": "s1", "timestamp": "2026-10-24T10:00:00Z",
                      "message": {"id": f"m{i}", "model": "claude-opus-5-5",
                                  "usage": {"input_tokens": 10, "cache_creation_input_tokens": 500,
                                            "cache_read_input_tokens": cached, "output_tokens": 200}}})
    lines.append({"type": "assistant", "isSidechain": True, "message": {"id": "side", "usage": {"input_tokens": 9}}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return path


class TestHint(Env):
    def test_quiet_when_short_then_once_per_20_turns(self):
        p = Paths(self.hub)
        f = transcript(self.work / "t.jsonl", 3, 20_000)
        hook = {"session_id": "s1", "transcript_path": str(f)}
        self.assertEqual(context.hint(p, "claude", hook), "")                 # 20.5k a turn: nothing
        transcript(f, 30, 400_000)
        text = context.hint(p, "claude", hook)
        self.assertIn("re-reads about 401k tokens every turn", text)
        self.assertIn("30 turns", text)
        self.assertEqual(context.hint(p, "claude", hook), "")                 # just said it
        transcript(f, 50, 400_000)
        self.assertNotEqual(context.hint(p, "claude", hook), "")              # 20 turns later, once more
        self.assertEqual(context.hint(p, "codex", hook), "")                  # no per-turn hook for Codex yet

    def test_a_sub_agent_gets_no_hint(self):
        from unittest import mock
        f = transcript(self.work / "t.jsonl", 30, 400_000)
        hook = {"session_id": "sub", "transcript_path": str(f)}
        with mock.patch.dict("os.environ", {"CCX_DEPTH": "1"}):
            self.assertEqual(context.hint(Paths(self.hub), "claude", hook), "")
        r = self.ccx("lead", "--hint", "--as", "claude", stdin=json.dumps(hook), env={"CCX_DEPTH": "1"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = self.ccx("turn", "--as", "claude", stdin=json.dumps(hook), env={"CCX_DEPTH": "1"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("re-reads about", context.hint(Paths(self.hub), "claude", hook))   # the lead still does

    def test_cli_hint_reads_the_hook_json_and_never_fails(self):
        f = transcript(self.work / "t.jsonl", 5, 300_000)
        r = self.ccx("lead", "--hint", "--as", "claude", stdin=json.dumps({"session_id": "x", "transcript_path": str(f)}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[ccx]", r.stdout)
        r = self.ccx("lead", "--hint", "--as", "claude", stdin="not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_lead_sessions_and_uninstall(self):
        transcript(self.home_claude / "projects" / "proj" / "s1.jsonl", 4, 250_000)
        r = self.ccx("lead", "--hours", "100000")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads(r.stdout)["sessions"][0]
        self.assertEqual((s["turns"], s["last_turn_tokens"]), (4, 250_510))
        self.assertTrue(s["advice"])
        p = Paths(self.hub)
        sync_all(p, apply=True, parts=["hooks"])
        uninstall(p, apply=True)
        st = json.loads((self.home_claude / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("UserPromptSubmit", st.get("hooks", {}))


if __name__ == "__main__":
    unittest.main()
