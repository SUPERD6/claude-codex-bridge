"""First-run fixes from a new-user walkthrough (2026-10-29): the README's first delegation really delegates, an
environment failure does not climb the ladder, setup without a terminal shows the plan, logins come first, doctor's
Codex-as-lead row is one line, plain lines for a person at a terminal, English words in English output, undo in
everyday help, and a one-line edit starts on the cheapest rung."""
import io
import json
import re
import subprocess
import unittest
from pathlib import Path

from test_ccx import Env

from ccx import router, setup
from ccx.commands.common import human_tail, person_named_to
from ccx.delegate import compact, env_failure, exit_ok, human_summary, recap

ROOT = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[一-鿿]")
NOT_LOGGED_IN = ("WARNING: proceeding, even though we could not create PATH aliases: Refusing to create helper "
                 "binaries under temporary dir\nNot logged in")


class FirstEnv(Env):
    def j(self, *args, env=None, code=0):
        r = self.ccx(*args, env=env)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def rec(self, run_id):
        return json.loads((self.hub / "ccx" / "runs" / run_id / "run.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 1: the first delegation really delegates
class TestFirstDelegation(FirstEnv):
    def test_a_person_naming_to_gets_a_small_task_delegated_with_a_note(self):
        r = self.ccx("run", "--to", "codex", "--mode", "read", "Summarise README.md in three lines")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)                          # no lead tool in the env: a person at a terminal
        self.assertIn("run_id", out)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("cheaper", out["route"]["cheaper_self"])
        self.assertIn("doing it yourself would be cheaper", r.stderr)
        self.assertEqual(out["tier"], "T1")                    # the cheapest rung, as --force does

    def test_a_lead_call_is_still_refused(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--mode", "read", "Summarise README.md in three lines")
        self.assertFalse(out["delegated"])
        self.assertIn("do-it-yourself", out["advice"])
        self.assertEqual(self.calls(), [])
        out = self.j("run", "--to", "codex", "--mode", "read", "Summarise README.md in three lines",
                     env={"CLAUDECODE": "1"})                  # detected, not named: the same
        self.assertFalse(out["delegated"])

    def test_who_counts_as_a_person(self):
        self.assertTrue(person_named_to("user", "codex"))
        self.assertFalse(person_named_to("user", "auto"))
        self.assertFalse(person_named_to("claude", "codex"))
        self.assertFalse(person_named_to("user", "codex", force=True))     # --force already delegates

    def test_readme_install_and_setup_suggest_the_same_command_and_it_is_delegated(self):
        cmd = setup.first_command("codex")
        for doc in ("README.md", "README.zh.md", "docs/install.md", "docs/install.zh.md"):
            self.assertIn(cmd, (ROOT / doc).read_text(encoding="utf-8"), doc)
        self.assertNotEqual(router.classify(setup.FIRST_TASK).tier, "T0")       # a lead's call delegates it too
        out = self.j("run", "--from", "claude", "--to", "codex", "--mode", "read", setup.FIRST_TASK)
        self.assertEqual((out["tier"], out["status"]), ("T1", "done"))


# ------------------------------------------------------------------ 2: environment failures do not climb
class TestEnvFailure(FirstEnv):
    def test_sandbox_helper_failure_stops_without_climbing(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--mode", "read", "look at x",
                     env={"FAKE_STATUS": "env"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)    # exit code as before (the CLI answered blocked)
        out = json.loads(r.stdout)
        self.assertEqual(out["kind"], "env")
        self.assertIs(out["ok"], False)                          # blocked never reports ok:true
        self.assertNotIn("escalated", out)
        self.assertEqual(len(self.calls()), 1)                   # no climb, no retry
        self.assertIn(f"ccx resume {out['run_id']}", out["hint"])
        self.assertIn("not the task", out["hint"])
        self.assertIn("fix the environment", out["recap"])
        rec = self.rec(out["run_id"])
        self.assertEqual(rec["attempts"][-1]["kind"], "env")
        self.assertIn("ShellExecuteExW", rec["env_error"])
        self.assertIsNone(rec.get("learned"))                    # says nothing about the model's ability

    def test_plain_blocked_still_climbs(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T1", "x y z",
                     env={"FAKE_STATUS": "blocked_then_done"})
        self.assertIn("escalated", out)

    def test_what_counts_as_an_environment_failure(self):
        helper = "orchestrator_helper_launch_canceled: ShellExecuteExW failed to launch setup helper: 1223"
        self.assertTrue(env_failure("blocked", True, "ok", helper))
        self.assertTrue(env_failure(None, False, "error", "CreateProcessWithLogonW failed: 267"))
        self.assertTrue(env_failure("failed", True, "ok", "", "ERROR helper: orchestrator_helper_launch failed"))
        self.assertIsNone(env_failure("done", True, "ok", helper))           # a finished attempt never is
        policy = ('error=exec_command failed: CreateProcess { message: "Rejected(\\"`powershell.exe` rejected: '
                  'blocked by policy\\")" }')
        self.assertIsNone(env_failure("blocked", True, "ok", policy))         # the sandbox policy: retried, not env
        self.assertIsNone(env_failure("blocked", True, "ok", "the tests fail on line 3"))
        # the task's own failures about processes are the model's to get past: they still climb
        for line in ("CreateProcess failed (os error 2) for program pytest",
                     'WARN exec_command failed: CreateProcess { message: "program not found: rg" }',
                     "The CreateProcess call fails with ERROR_FILE_NOT_FOUND when the path has spaces",
                     "Windows error 1223 handling in installer still broken"):
            self.assertIsNone(env_failure("failed", True, "ok", line), line)

    def test_a_failed_task_about_createprocess_still_climbs(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T1", "fix the launcher",
                     env={"FAKE_STATUS": "blocked_then_done",
                          "FAKE_SUMMARY": "I could not fix the CreateProcess error handling in launcher.c"})
        self.assertIn("escalated", out)
        self.assertNotEqual(out.get("kind"), "env")

    def test_blocked_is_not_ok_but_the_exit_code_is_unchanged(self):
        rec = {"run_id": "r1", "to": "codex", "tier": "T1", "ok": True, "kind": "ok", "cwd": "",
               "attempts": [{"model": "m", "effort": "low", "ae_usd": 0.01}],
               "result": {"status": "blocked", "summary": "could not"}}
        self.assertIs(compact(rec)["ok"], False)
        self.assertTrue(exit_ok(rec))
        rec["result"]["status"] = "done"
        self.assertIs(compact(rec)["ok"], True)

    def test_selftest_reports_a_blocked_answer_as_not_ok_with_the_old_exit_code(self):
        r = self.ccx("selftest", env={"FAKE_STATUS": "blocked"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)    # exit code as before
        out = json.loads(r.stdout)
        self.assertTrue(out["selftest"])
        self.assertTrue(all(row["ok"] is False for row in out["selftest"]), out)   # same as `ccx run` says
        self.assertIs(out["all_ok"], False)

    def test_auth_recap_points_at_the_login(self):
        rec = {"run_id": "r2", "to": "codex", "tier": "T1", "ok": False, "kind": "auth", "auth_problem": True,
               "cwd": "", "attempts": [{"model": "m", "effort": "low"}], "result": None, "error": "401"}
        res = compact(rec)
        self.assertIn("codex login", recap(rec, res))
        self.assertNotIn("next: ccx show", recap(rec, res))

    def test_a_foreground_run_says_it_is_still_working_on_stderr_only(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "look at x",
                     env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "2", "CCX_PROGRESS_SEC": "0.4"})
        self.assertIn("still working", r.stderr)
        self.assertNotIn("still working", r.stdout)
        json.loads(r.stdout)                                     # stdout: the JSON alone, as before

    def test_a_lead_piping_stderr_gets_no_progress_lines(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "look at x",
                     env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "1.5", "CCX_PROGRESS_SEC": ""})
        self.assertNotIn("still working", r.stdout + r.stderr)   # stderr is not a terminal: nothing added


# ------------------------------------------------------------------ 3 + 4: setup
class TestSetupFirstRun(FirstEnv):
    def test_not_on_a_terminal_shows_every_step_and_changes_nothing(self):
        hub = self.hub.parent / "newhub"
        r = self.ccx("setup", "--hub", str(hub), stdin="")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for want in (f'ccx init --hub "{hub}"', "ccx sync\n", "ccx sync --apply", "ccx doctor",
                     setup.first_command("codex"), "Nothing was changed"):
            self.assertIn(want, r.stdout)
        self.assertFalse(hub.exists())
        self.assertFalse((self.home_claude / "settings.json").exists())
        self.assertFalse((self.home_codex / "config.toml").exists())

    def test_logins_come_first_and_yes_skips_the_paid_selftest(self):
        hub = self.hub.parent / "newhub"
        r = self.ccx("setup", "--yes", "--hub", str(hub), env={"CCX_HUB": "", "FAKE_CODEX_LOGIN": NOT_LOGGED_IN})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipped: codex not logged in", r.stdout)
        self.assertNotIn("exec", json.dumps(self.calls()))            # no selftest run reached a CLI
        before = r.stdout.index("Before your first delegation")
        self.assertLess(before, r.stdout.index("Your first delegation"))
        self.assertIn("codex login", r.stdout[before:])

    def test_another_hub_is_named_and_its_command_has_force(self):
        old, new = self.hub.parent / "old-hub", self.hub.parent / "new-hub"
        Path(self.env["CCX_CONFIG"]).write_text(f"hub = '{old}'\n", encoding="utf-8")
        r = self.ccx("setup", "--hub", str(new), stdin="")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"replaces the hub set before ({old.resolve()})", r.stdout)
        self.assertIn(f'ccx init --hub "{new}" --force', r.stdout)      # the printed step works as printed
        r = self.ccx("setup", "--hub", str(old), stdin="")
        self.assertNotIn("--force", r.stdout)                            # the same hub: nothing to force
        r = self.ccx("setup", "--yes", "--hub", str(new), env={"CCX_HUB": ""})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)          # --yes never switches hubs unasked
        self.assertIn("--force", r.stdout)
        self.assertIn(str(old), Path(self.env["CCX_CONFIG"]).read_text(encoding="utf-8"))
        self.assertFalse(new.exists())

    def test_not_on_a_terminal_lists_the_login_first(self):
        r = self.ccx("setup", "--hub", str(self.hub.parent / "h2"), stdin="", env={"FAKE_CODEX_LOGIN": NOT_LOGGED_IN})
        plan = r.stdout[r.stdout.index("Not on a terminal"):]
        self.assertLess(plan.index("codex login"), plan.index("ccx init --hub"))


# ------------------------------------------------------------------ 4 + 5: doctor
class TestDoctorFirstRun(FirstEnv):
    def test_codex_login_row_shows_the_status_line_and_the_summary_lists_it_first(self):
        r = self.ccx("doctor", env={"FAKE_CODEX_LOGIN": NOT_LOGGED_IN})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        row = next(x for x in r.stdout.splitlines() if x.startswith("codex login"))
        self.assertIn("Not logged in", row)
        self.assertIn("`codex login`", row)
        self.assertNotIn("PATH aliases", row)
        todo = r.stdout[r.stdout.index("To do, in this order:"):]
        self.assertLess(todo.index("codex login"), todo.index("ccx init"))
        self.assertLess(todo.index("ccx init"), todo.index("ccx sync"))

    def test_codex_as_lead_is_one_info_line_unless_asked(self):
        r = self.ccx("doctor")
        rows = [x for x in r.stdout.splitlines() if x.startswith("Codex as lead")]
        self.assertEqual(len(rows), 1)
        self.assertIn("info", rows[0])
        self.assertIn("--codex-lead", rows[0])
        self.assertNotIn("danger-full-access", r.stdout)
        full = self.ccx("doctor", "--codex-lead").stdout
        self.assertIn("sandbox_mode = not set", full)


# ------------------------------------------------------------------ 6: plain lines for a person
class TestHumanOutput(unittest.TestCase):
    class Tty(io.StringIO):
        def __init__(self, tty):
            super().__init__()
            self.tty = tty

        def isatty(self):
            return self.tty

    def test_only_on_a_terminal(self):
        on, off = self.Tty(True), self.Tty(False)
        human_tail(["Result: done"], on)
        human_tail(["Result: done"], off)
        self.assertIn("Result: done", on.getvalue())
        self.assertEqual(off.getvalue(), "")

    def test_summary_says_result_cost_and_next(self):
        rec = {"run_id": "r3", "to": "codex", "tier": "T1", "ok": True, "kind": "ok", "cwd": "",
               "attempts": [{"model": "gpt-x", "effort": "low", "ae_usd": 0.0025}],
               "result": {"status": "done", "summary": "three lines"}}
        lines = human_summary(rec, compact(rec))
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("Result: done: three lines"))
        self.assertIn("$0.0025", lines[1])
        self.assertIn("ccx verify r3", lines[2])



# ------------------------------------------------------------------ 7: English output has English words
class TestRouteLanguage(FirstEnv):
    def test_piped_output_stays_json(self):
        json.loads(self.ccx("route", "rename x").stdout)       # nothing after the JSON on a pipe

    def test_route_label_follows_the_language(self):
        for brief in ("rename x", "Summarise README.md in three lines", "implement a parser with tests for it"):
            out = self.j("route", brief)
            self.assertFalse(CJK.search(out["label"] + out["when"]), out)
        self.ccx("config", "set", "ui.lang", "zh")
        self.assertTrue(CJK.search(self.j("route", "rename x")["label"]))


# ------------------------------------------------------------------ 8: undo
class TestUndoFirstRun(FirstEnv):
    def test_undo_is_everyday_and_apply_is_explained(self):
        h = self.ccx("-h").stdout
        self.assertIn("\n  undo ", h.split("Everyday:", 1)[1].split("\n\n", 1)[0])
        self.assertIn("really restore", self.ccx("undo", "-h").stdout)

    def test_nothing_to_undo_says_so(self):
        def git(*a):
            subprocess.run(["git", *a], cwd=self.work, check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (self.work / "a.py").write_text("x = 1\n")
        (self.work / ".gitignore").write_text(".ccx/\n")
        git("add", "-A")
        git("commit", "-qm", "init")
        out = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "write", "--review", "off",
                     "edit a.py", code=2)                  # no_changes: exit 2, as it always was
        u = self.j("undo", out["run_id"])
        self.assertEqual((u["restore"], u["move_aside"]), ([], []))
        self.assertIn("nothing to undo", u["nothing_to_undo"])
        self.assertNotIn("warning", u)
        snap = self.hub / "ccx" / "runs" / out["run_id"] / "undo.json"
        data = json.loads(snap.read_text(encoding="utf-8"))
        data["base"] = "0" * 40                                  # the base commit is gone (gc, rebase)
        snap.write_text(json.dumps(data), encoding="utf-8")
        u = self.j("undo", out["run_id"])
        self.assertNotIn("nothing_to_undo", u)                   # a git failure is never "nothing to undo"
        self.assertIn("git could not list", u["git_error"])
        self.assertIn("warning", u)


# ------------------------------------------------------------------ 9: a one-line edit starts cheap
class TestOneLineEdit(unittest.TestCase):
    def test_one_line_edits_route_to_the_cheapest_rung(self):
        for brief in ("Add a line 'Tested by newuser' at the end of README.md",
                      "Append a sentence to CONTRIBUTING.md about running the tests before committing"):
            self.assertEqual(router.classify(brief).tier, "T1", brief)

    def test_real_work_keeps_its_tier(self):
        for brief, tier in (("Add a line-by-line diff viewer to the report page", "T2"),
                            ("Implement retry with exponential backoff in the HTTP client and add tests for it", "T2"),
                            ("Fix the race condition in the queue worker that sometimes drops items", "T3"),
                            # "a line" next to hard or critical work is not a one-line edit (tiers as before it)
                            ("Add a line to the scheduler that acquires the lock before reading the shared queue "
                             "to fix the race condition", "T3"),
                            ("Remove the line that disables CSRF verification in the auth middleware and fix the "
                             "failing tests across the API", "T3"),
                            ("Replace the line in the migration that drops the users table; make it idempotent and "
                             "test on the database schema", "T3"),
                            ("Remove the line that swallows the exception and fix the concurrency bug in the queue "
                             "across modules", "T4"),
                            ("Add a line to the CLI that validates --port and add tests for the parser", "T2"),
                            ("Insert a sentence in docs/api.md about rate limits and implement the endpoint", "T2")):
            self.assertEqual(router.classify(brief).tier, tier, brief)

    def test_the_pull_down_alone_never_makes_it_do_it_yourself(self):
        for brief in ("Add a sentence to the docs about installing on Windows",
                      "Add a line to handle an empty list in parser.py"):
            self.assertEqual(router.classify(brief).tier, "T1", brief)     # was T2; delegated, never T0


if __name__ == "__main__":
    unittest.main()
