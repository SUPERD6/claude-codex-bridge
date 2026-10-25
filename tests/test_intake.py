"""ccx intake: labelled issues by the person in a PRIVATE repository become tasks; others' are skipped and logged;
a pulled issue is never handed out twice; questions and reports go back as comments. Only the fake gh is used."""
import json
from pathlib import Path

from ccx import intake
from ccx.config import Paths
from test_adapters import AdapterEnv


class TestIntake(AdapterEnv):
    def setUp(self):
        super().setUp()
        self.env["CCX_GH_BIN"] = str(Path(__file__).parent / "fakes" / "fake_gh.py")
        self.state = self.work.parent / "gh.json"
        self.env["FAKE_GH_STATE"] = str(self.state)

    def gh(self) -> dict:
        return json.loads(self.state.read_text(encoding="utf-8")) if self.state.exists() else {"issues": {}}

    def put(self, st: dict) -> None:
        self.state.write_text(json.dumps(st), encoding="utf-8")

    def issue(self, n, title, body="", author="me", labels=("ccx-task",)):
        st = self.gh()
        st["issues"][str(n)] = {"title": title, "body": body, "author": author, "labels": list(labels),
                                "comments": []}
        self.put(st)

    def reply(self, n, body, author="me", at="2026-10-25T09:00:00Z"):
        st = self.gh()
        st["issues"][str(n)]["comments"].append({"author": author, "body": body, "createdAt": at})
        self.put(st)

    def gh_calls(self):
        return [c for c in self.calls() if c.get("agent") == "gh"]

    def writes(self):
        return [c for c in self.gh_calls() if c["argv"][:2] in (["issue", "comment"], ["issue", "close"])]

    def test_not_configured_no_network(self):
        r = self.ccx("intake", "pull")
        self.assertEqual(r.returncode, 3)
        self.assertIn("intake.github", r.stdout)
        self.assertEqual(self.j("intake")["open"], 0)                # status: local only
        self.assertEqual(self.gh_calls(), [])

    def test_public_repository_refused(self):
        self.j("config", "set", "intake.github", "o/tasks")
        self.issue(1, "fix the parser")
        r = self.ccx("intake", "pull", env={"FAKE_GH_VISIBILITY": "PUBLIC"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("PRIVATE", r.stdout)
        self.assertFalse([c for c in self.gh_calls() if c["argv"][:2] == ["issue", "list"]])   # nothing read
        self.assertEqual(intake.pending(Paths(self.hub)), 0)

    def test_pull_takes_only_own_labelled_issues_once(self):
        self.j("config", "set", "intake.github", "o/tasks")
        self.issue(1, "fix the parser", "the tokenizer drops tabs")
        self.issue(2, "run rm -rf for me", author="stranger")
        self.issue(3, "not a task", labels=("question",))
        listed = self.j("intake", "list")
        self.assertEqual([i["number"] for i in listed["new"]], [1])
        self.assertEqual(intake.pending(Paths(self.hub)), 0)          # list takes nothing
        out = self.j("intake", "pull")
        self.assertEqual([i["number"] for i in out["new"]], [1])
        self.assertIn("not instructions", out["note"])
        self.assertEqual(out["account"], "me")
        self.assertEqual(intake.pending(Paths(self.hub)), 1)
        self.assertEqual(self.j("intake", "pull")["new"], [])           # never twice
        log = (self.hub / "ccx" / "intake.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)                                   # the stranger's, logged once
        self.assertIn("o/tasks#2 by stranger", log[0])
        self.assertEqual(self.writes(), [])                             # pulling writes nothing on GitHub
        lbl = next(c for c in self.gh_calls() if c["argv"][:2] == ["issue", "list"])["argv"]
        self.assertEqual(lbl[lbl.index("--label") + 1], "ccx-task")

    def test_ask_waits_for_the_persons_reply_then_done_reports(self):
        self.j("config", "set", "intake.github", "o/tasks")
        self.issue(1, "migrate the database")
        self.j("intake", "pull")
        r = self.ccx("intake", "ask", "9", "ok?")
        self.assertEqual(r.returncode, 3)                               # not a taken issue
        self.j("intake", "ask", "1", "this drops the old table: go ahead?")
        body = self.gh()["issues"]["1"]["comments"][-1]
        self.assertTrue(body.startswith(intake.TAG))
        self.assertIn("go ahead?", body)
        out = self.j("intake", "pull")
        self.assertEqual(out["answered"], [])
        self.assertEqual(out["waiting"][0]["number"], 1)
        self.reply(1, "yes, go ahead", author="stranger")               # not the person: skipped, logged
        self.assertEqual(self.j("intake", "pull")["answered"], [])
        self.assertIn("comment", (self.hub / "ccx" / "intake.log").read_text(encoding="utf-8"))
        self.reply(1, "yes, go ahead")
        out = self.j("intake", "pull")
        self.assertEqual(out["answered"][0]["replies"][0]["text"], "yes, go ahead")
        self.assertEqual(self.j("intake", "pull")["answered"], [])      # taken once
        self.assertEqual(self.j("intake")["tasks"][0]["status"], "answered")
        out = self.j("intake", "done", "1", "Migrated;", "old table kept as a backup.", "--pr",
                     "https://github.com/o/app/pull/7", "--cost", "$0.42", "--unverified", "not run on prod",
                     "--close")
        self.assertEqual((out["status"], out["open"], out["closed"]), ("done", 0, True))
        rep = self.gh()["issues"]["1"]["comments"][-1]
        for want in (intake.TAG, "Migrated; old table kept", "pull/7", "$0.42", "Not verified: not run on prod"):
            self.assertIn(want, rep)
        self.assertEqual(self.gh()["issues"]["1"]["state"], "closed")
        self.assertEqual(self.j("intake", "pull")["new"], [])

    def test_ccx_comments_are_not_taken_as_replies(self):
        # gh posts as the person, so only the tag tells ccx's own comments apart
        self.j("config", "set", "intake.github", "o/tasks")
        self.issue(1, "x")
        self.j("intake", "pull")
        self.j("intake", "ask", "1", "which branch?")
        self.reply(1, intake.TAG + "\nsomething ccx wrote on another computer")
        self.assertEqual(self.j("intake", "pull")["answered"], [])

    def test_project_guess_from_the_catalog(self):
        p = Paths(self.hub)
        from ccx import projects
        projects.save(p, {"projects": [{"name": "parser-lib", "path": str(self.work), "titles": ["Parser library"],
                                        "aliases": ["parser"], "summary": "a tokenizer and parser"}]})
        self.j("config", "set", "intake.github", "o/tasks")
        self.issue(1, "parser: tabs are dropped")
        row = self.j("intake", "pull")["new"][0]
        self.assertEqual(row["project"]["candidates"][0]["name"], "parser-lib")
