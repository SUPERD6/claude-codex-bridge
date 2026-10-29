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
