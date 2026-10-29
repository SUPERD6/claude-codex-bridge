"""PR-F part 2: the retry after a failed check ([defaults] focused_retry), the reviewer's permission line, the run
card for an environment failure, sync's dry run and doctor's default table (fake CLIs only, no paid runs)."""
import json

from test_adapters import AdapterEnv

MARK = "BOOM-the-failing-assert"


def counting_check(counter, noise: int = 1500) -> str:
    """Fails the first time (printing `noise` characters and then MARK), passes after."""
    return ('python -c "import pathlib,sys;f=pathlib.Path(r\'%s\');n=int(f.read_text()) if f.exists() else 0;'
            'f.write_text(str(n+1));print(\'x\'*%d);print(\'%s\');sys.exit(0 if n else 1)"' % (counter, noise, MARK))


class TestFocusedRetry(AdapterEnv):
    def run_t1(self, env=None):
        check = counting_check(self.work / "check-runs.txt")
        return self.j("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--review", "off", "--check", check,
                      "fix it", env=env)

    def codex_calls(self):
        return [c for c in self.calls() if c["agent"] == "codex"]

    def test_default_off_keeps_the_escalation_note(self):
        out = self.run_t1()
        self.assertTrue(out["ok"])
        last = self.codex_calls()[-1]["prompt"]
        self.assertIn("you said done, but", last)
        self.assertNotIn("[ccx retry", last)
        self.assertNotIn("retry", self.rec(out["run_id"])["attempts"][0])

    def test_on_resumes_the_session_with_the_check_output(self):
        self.assertEqual(self.ccx("config", "set", "defaults.focused_retry", "true").returncode, 0)
        out = self.run_t1()
        self.assertTrue(out["ok"])
        first, second = self.codex_calls()[-2:]
        rec = self.rec(out["run_id"])
        sid = rec["attempts"][0]["session_id"]
        self.assertTrue(sid)
        self.assertEqual(second["argv"][:3], ["exec", "resume", sid])            # the same session, continued
        p = second["prompt"]
        self.assertIn("[ccx retry", p)
        self.assertIn("check-runs.txt", p)                                       # the failing command
        self.assertIn("(exit 1)", p)
        self.assertIn(MARK, p)                                                   # the end of its output
        self.assertGreater(p.count("x" * 100), 0)                                # ... ~2000 characters of it
        self.assertIn("Fix only what makes this check fail", p)
        self.assertNotIn("you said done, but", p)
        self.assertEqual(rec["attempts"][0]["retry"], "focused")
        self.assertIn("stronger model", p)                    # T1 -> T2 is another model: the note says so

    def test_ladder_is_the_same_on_and_off(self):
        off = self.run_t1()
        (self.work / "check-runs.txt").unlink()
        self.ccx("config", "set", "defaults.focused_retry", "true")
        on = self.run_t1()
        rungs = lambda o: [(a["tier"], a["rung"], a["kind"]) for a in self.rec(o["run_id"])["attempts"]]  # noqa: E731
        self.assertEqual(rungs(off), rungs(on))
        self.assertEqual(off["escalated"], on["escalated"])
        self.assertEqual((self.work / "check-runs.txt").read_text(), "2")       # once per attempt, as before

    def test_no_session_id_falls_back_to_a_fresh_start(self):
        self.ccx("config", "set", "defaults.focused_retry", "true")
        out = self.run_t1(env={"FAKE_NO_THREAD": "1"})
        self.assertTrue(out["ok"])
        second = self.codex_calls()[-1]
        self.assertNotEqual(second["argv"][:2], ["exec", "resume"])               # nothing to resume
        self.assertIn("fix it", second["prompt"])                                 # today's behaviour: the brief again
        self.assertNotIn("[ccx retry", second["prompt"])
        self.assertNotIn("retry", self.rec(out["run_id"])["attempts"][0])


def test_focused_retry_reads_the_setting():
    from ccx.delegate import focused_retry
    assert focused_retry({"defaults": {}}) is False
    assert focused_retry({"defaults": {"focused_retry": True}}) is True
    assert focused_retry({"defaults": {"focused_retry": "false"}}) is False
    from ccx.config import load_config, Paths
    import tempfile
    from pathlib import Path
    assert load_config(Paths(Path(tempfile.mkdtemp())))["defaults"]["focused_retry"] is False   # shipped: off


def test_check_retry_prompt_names_same_or_stronger_model():
    from ccx.prompts import CHECK_RETRY, CHECK_RETRY_SAME
    text = CHECK_RETRY.format(run_id="r1", cmd="pytest -q", exit=1, tail="E assert 1 == 2", model_line=CHECK_RETRY_SAME)
    assert "pytest -q" in text and "E assert 1 == 2" in text and "Same model as before" in text
    json.dumps(text)


# ---- 2. the reviewer is told ccx's own check result; no new permission
import subprocess  # noqa: E402

from test_ccx import Env  # noqa: E402


class _ReviewEnv(Env):
    """test_review.TestReviewRun's set-up and helpers (copied, so its tests do not run twice)."""
    def setUp(self):
        super().setUp()
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def go(self, *extra):
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n", "FAKE_REVIEW": "pass"}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", *extra, "change x to 2 in a.py", env=env)
        self.assertIn(r.returncode, (0, 2), r.stderr)
        return json.loads(r.stdout)

    def reviews(self):
        return [c for c in self.calls() if c["agent"] == "claude" and "[ccx review" in c["prompt"]]


class TestReviewerNeedsNoTests(_ReviewEnv):
    def test_no_new_permission_and_the_check_is_named(self):
        from ccx import prompts
        from ccx.config import Paths, load_config
        self.go("--check", "exit 0")
        call = self.reviews()[0]
        rev, argv = call["prompt"], call["argv"]
        allowed = argv[argv.index("--allowed-tools") + 1]
        read = load_config(Paths(self.hub))["permissions"]["claude"]["read"]
        self.assertEqual(allowed, read[read.index("--allowed-tools") + 1])          # nothing added, not the check
        self.assertNotIn("exit 0", allowed)
        self.assertIn("ccx ran the acceptance command `exit 0`", rev)
        self.assertIn("You need not run it yourself.", rev)
        self.assertIn("one plain command per call", prompts.REVIEW_PERMISSION_CLAUDE)
        self.assertIn("Permission: " + prompts.REVIEW_PERMISSION_CLAUDE, rev)


def test_brief_shows_the_end_of_the_check_output_when_it_ran():
    from ccx import review
    chk = {"cmd": "pytest -q", "passed": True, "exit": 0, "tail": "noise\n" * 300 + "7 passed in 1.2s"}
    text = review.brief("r1", "do x", "did x", "+x = 1", 4000, chk, [])
    checks = text.split("## Checks\n", 1)[1].split("## Answer", 1)[0]
    assert checks.startswith("ccx ran the acceptance command `pytest -q` after the change: passed.")
    assert "7 passed in 1.2s" in checks and "You need not run it yourself." in checks
    assert len(checks) < review.CHECK_TAIL_IN_BRIEF + 300                        # only the end of it
    # the recorded-brief parser (scripts/eval/review_replay.py) still reads the check line
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "review_replay", Path(__file__).resolve().parent.parent / "scripts" / "eval" / "review_replay.py")
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)
    assert rr.parse_brief(text)["check"] == {"cmd": "pytest -q", "passed": True, "exit": 0}
    none = review.brief("r1", "do x", "did x", "+x = 1", 4000, None, [])
    assert "nobody ran the tests for you" in none and "need not run it" not in none


# ---- 4. ccx ui: an environment failure, and an empty hub
from test_ui import STATIC, pieces, put_run  # noqa: E402


class TestUiEnvAndStart(Env):
    def setUp(self):
        super().setUp()
        (self.work / ".git").mkdir()

    def test_env_run_shows_the_hint_and_doctor_not_try_again(self):
        from ccx import ui
        from ccx.config import Paths
        put_run(self.hub, "r-env", self.work, kind="env", ok=False, env_error="ShellExecuteExW failed: 1223",
                result={"status": "blocked", "summary": "could not run anything"})
        p = pieces(ui.collect(Paths(self.hub)))[0]
        act = p["act"]
        self.assertEqual(act["what"], "a_env")
        self.assertEqual(act["why"][0], "w_env")
        self.assertIn("ShellExecuteExW failed: 1223", act["why"][1]["hint"])        # the run's own fix hint
        labels = [b["label"] for b in act["buttons"]]
        self.assertNotIn("b_retry", labels)
        doctor = next(b for b in act["buttons"] if b["label"] == "b_doctor")
        self.assertEqual((doctor["cmd"], doctor["style"]), ("ccx doctor", "primary"))
        # other failures keep "Try again"
        put_run(self.hub, "r-fail", self.work, ok=False, result={"status": "failed", "summary": "nope"})
        acts = {x["run_id"]: x["act"] for x in pieces(ui.collect(Paths(self.hub)))}
        self.assertIn("b_retry", [b["label"] for b in acts["r-fail"]["buttons"]])

    def test_empty_hub_says_what_to_do_first(self):
        from ccx import ui, setup
        from ccx.config import Paths
        data = ui.collect(Paths(self.hub))
        self.assertEqual(data["projects"], [])
        self.assertEqual(data["start"]["first"], setup.first_command("codex"))     # README / setup's first command
        from ccx.cli import build_parser
        import argparse
        sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual(data["start"]["demo"], "ccx demo" if "demo" in sub.choices else None)
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('t("empty") }</p>` + startHTML()'.replace(" }", "}"), js)
        strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
        for lg in ("zh", "en"):
            self.assertIn("{cmd}", strings[lg]["empty_first"])
            self.assertIn("{cmd}", strings[lg]["empty_demo"])
