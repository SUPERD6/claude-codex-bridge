"""scripts/eval/preflight_e2e.py (H15) against the fake CLIs: each step's verdict comes from files, records and the
ledger; steps that need a second vendor are skipped in Codex-only mode; the spend cap skips the rest."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from test_ccx import Env

EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(EVAL))

import preflight_e2e  # noqa: E402

HAS_PYTEST = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0
SLUGIFY = "import re\ndef slugify(text):\n    return re.sub('[^a-z0-9]+', '-', text.lower()).strip('-')\n"
SLUGIFY_DOC = SLUGIFY.replace("    return", '    """Slug."""\n    return')


@unittest.skipUnless(HAS_PYTEST, "the steps judge by running pytest")
class TestPreflightSteps(Env):
    def pf(self):
        pf = preflight_e2e.Preflight(self.work / "pf", cap=0.5)
        pf.env.update({k: v for k, v in self.env.items() if k.startswith(("CCX_CODEX_BIN", "CCX_CLAUDE_BIN",
                                                                         "CODEX_HOME", "CLAUDE_CONFIG", "FAKE_LOG",
                                                                         "CCX_CONFIG", "CCX_NO_QUOTA"))})
        return pf

    def test_delegate_followup_undo_handoff(self):
        pf = self.pf()
        pf.env["FAKE_WRITE"] = f"textutil.py={SLUGIFY}"
        d = pf.delegate()
        self.assertTrue(d["ok"], d)
        pf.env["FAKE_WRITE"] = f"textutil.py={SLUGIFY_DOC}"
        f = pf.followup()                                     # the follow-up really edits (else: no_changes)
        self.assertTrue(f["ok"] and f["same_session"], f)
        u = pf.undo()
        self.assertTrue(u["ok"], u)
        self.assertEqual(u["changed_before"], ["textutil.py"])
        pf.env.pop("FAKE_WRITE")
        pf.env["FAKE_SUMMARY"] = "Write a test for strings that are only punctuation."
        h = pf.handoff()
        self.assertTrue(h["ok"], h)
        pf.env["FAKE_SUMMARY"] = "something else"
        self.assertFalse(pf.handoff()["ok"])                  # judged by what it read, not by finishing

    def test_stop_then_resume(self):
        pf = self.pf()
        pf.env.update(FAKE_STATUS="hang", FAKE_HANG_S="8")
        s = pf.stop()
        self.assertTrue(s["ok"], s)
        self.assertEqual((s["state"], s["kind"], s["ledger_rows"]), ("stopped", "user_stopped", 1))
        self.assertGreater(s["tokens_counted"], 0)            # the fake's session file: what it spent before the stop
        self.assertTrue(s["same_session"])


class TestResumeReview(Env):
    def test_resume_takes_review_like_run(self):
        # Codex-only preflight: a write follow-up must not call another vendor for its review
        (self.work / "a.py").write_text("0\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "s"]):
            subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True)
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--review", "off", "x", env={"FAKE_WRITE": "a.py=1"})
        rid = json.loads(r.stdout)["run_id"]
        self.ccx("resume", rid, "more", "--review", "off", env={"FAKE_WRITE": "a.py=2"})
        self.assertEqual({c["agent"] for c in self.calls()}, {"codex"})
        self.ccx("resume", rid, "more", "--review", "on", env={"FAKE_WRITE": "a.py=3"})
        self.assertIn("claude", {c["agent"] for c in self.calls()})          # the reviewer, another vendor


class TestPreflightMain(Env):
    def test_codex_only_skips_second_vendor_steps_and_cap_skips_the_rest(self):
        out = self.work / "pf.jsonl"
        rc = preflight_e2e.main(["--only", "delegate,review,reverse", "--cap", "0", "--work", str(self.work / "pf"),
                                 "--out", str(out)])
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(rc, 1)                                # nothing ran: not a pass
        self.assertIn("cap", row["steps"]["delegate"]["skipped"])
        self.assertIn("--agents all", row["steps"]["review"]["skipped"])
        self.assertIn("--agents all", row["steps"]["reverse"]["skipped"])
        self.assertEqual(row["ledger"], [])
