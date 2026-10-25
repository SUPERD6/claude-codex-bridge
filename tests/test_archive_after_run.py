"""sessions.archive = after_run (the user's request, 2026-10-25): a sub-agent session is archived as soon as its run's
result is final, kept while it may still be continued, and put back by itself when it is continued. Fake CLIs only."""
import json

from test_ccx import Env

ON = {"CCX_NO_AUTO_ARCHIVE": "0"}
LUNA = ["--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low"]


class ArchiveEnv(Env):
    def go(self, *args, env=None, code=None):
        r = self.ccx(*args, env={**ON, **(env or {})})
        if code is not None:
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def rec(self, run_id):
        return json.loads((self.hub / "ccx" / "runs" / run_id / "run.json").read_text(encoding="utf-8"))

    def archived(self):
        f = self.hub / "ccx" / "archived.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def codex_calls(self, verb):
        return [c["argv"][1] for c in self.calls() if c["argv"][:1] == [verb]]


class TestAfterRun(ArchiveEnv):
    def test_a_checked_done_run_is_archived_at_once(self):
        out = self.go("run", *LUNA, "x", code=0)
        sid = self.rec(out["run_id"])["session_id"]
        self.assertEqual(self.codex_calls("archive"), [sid])
        [e] = self.archived()
        self.assertEqual((e["run_id"], e["why"]), (out["run_id"], "after_run"))

    def test_claude_transcript_is_moved_aside(self):
        out = self.go("run", "--from", "codex", "--to", "claude", "--model", "sonnet", "--effort", "low",
                       "--check", "python -c pass", "x", env={"FAKE_STATUS": "done"}, code=0)
        self.assertEqual([e["run_id"] for e in self.archived()], [out["run_id"]])

    def test_runs_that_may_go_on_are_kept(self):
        self.go("run", *LUNA, "--no-fallback", "x", env={"FAKE_STATUS": "quota"})
        self.go("run", *LUNA, "--no-escalate", "x", env={"FAKE_STATUS": "blocked"})
        self.go("run", *LUNA, "--no-escalate", "--check", "python -c \"raise SystemExit(1)\"", "x")
        self.go("run", "--from", "codex", "--to", "claude", "--tier", "T2", "--seat", "reviewer", "review a.py")
        self.go("ask", "--from", "claude", "--to", "codex", "q")
        self.assertEqual(self.archived(), [])
        self.assertEqual(self.codex_calls("archive"), [])

    def test_unchecked_done_waits_for_the_verdict(self):
        out = self.go("run", "--from", "codex", "--to", "claude", "--model", "sonnet", "--effort", "low", "x",
                       env={"FAKE_STATUS": "done"}, code=0)
        if self.archived():
            self.skipTest("the fake Claude checked itself here")
        self.assertEqual(self.archived(), [])
        self.go("verify", out["run_id"], "--ok", "1")
        self.assertEqual([e["run_id"] for e in self.archived()], [out["run_id"]])

    def test_resume_brings_the_session_back_first(self):
        out = self.go("run", *LUNA, "x", code=0)
        sid = self.rec(out["run_id"])["session_id"]
        self.go("resume", out["run_id"], "one more thing", code=0)
        verbs = [c["argv"][:3] for c in self.calls() if c["argv"][:1] in (["unarchive"], ["exec"])]
        self.assertEqual(verbs[-2:], [["unarchive", sid], ["exec", "resume", sid]])
        self.assertEqual(self.codex_calls("archive"), [sid, sid])            # final again: archived again

    def test_auto_continue_reaches_an_archived_session(self):
        env = {"CCX_LEAD_SESSION": "lead-1"}
        a = self.go("run", *LUNA, "x", env=env, code=0)
        b = self.go("run", *LUNA, "y", env=env, code=0)
        self.assertEqual(b.get("continued_from"), a["run_id"])               # archived after run, still continued
        sid = self.rec(a["run_id"])["session_id"]
        self.assertEqual(self.codex_calls("unarchive"), [sid])

    def test_archived_by_hand_is_not_continued(self):
        env = {"CCX_LEAD_SESSION": "lead-1"}
        self.go("config", "set", "sessions.archive", "off")
        a = self.go("run", *LUNA, "x", env=env, code=0)
        self.go("archive", a["run_id"], "--apply")
        b = self.go("run", *LUNA, "y", env=env, code=0)
        self.assertNotIn("continued_from", b)

    def test_hours_and_off_leave_it_to_session_start(self):
        for m in ("hours", "off"):
            self.go("config", "set", "sessions.archive", m)
            self.go("run", *LUNA, "--new", "x", code=0)
        self.assertEqual(self.archived(), [])
        r = self.ccx("config", "set", "sessions.archive", "sometimes")
        self.assertNotEqual(r.returncode, 0)
