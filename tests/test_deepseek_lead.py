"""DeepSeek as the lead: dsh itself, or a DeepSeek model behind Claude Code / Codex, is told apart from the
environment, recorded with its vendor, and gets no continuation across read/write; ccx finds the desktop dsh."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import runners  # noqa: E402,F401  (imported first: ccx.agents alone hits an import cycle)
from ccx.agents import dsh  # noqa: E402
from ccx.commands.common import lead_identity  # noqa: E402
from ccx.config import load_config  # noqa: E402
from test_ccx import Env  # noqa: E402

CFG = None


def cfg():
    global CFG
    CFG = CFG or load_config()
    return CFG


class TestIdentity(unittest.TestCase):
    def test_plain_tools_and_the_person(self):
        self.assertEqual(lead_identity({}, cfg()), "user")
        self.assertEqual(lead_identity({"CLAUDECODE": "1"}, cfg()), "claude")
        self.assertEqual(lead_identity({"CLAUDECODE": "1", "ANTHROPIC_BASE_URL": "https://api.anthropic.com"},
                                       cfg()), "claude")

    def test_dsh_is_the_innermost(self):
        self.assertEqual(lead_identity({"DSH_SESSION_ID": "session-1", "CLAUDECODE": "1"}, cfg()), "dsh")

    def test_deepseek_behind_claude_code(self):
        url = cfg()["providers"]["deepseek"]["env"]["ANTHROPIC_BASE_URL"]
        self.assertEqual(lead_identity({"CLAUDECODE": "1", "ANTHROPIC_BASE_URL": url + "/"}, cfg()), "deepseek")
        self.assertEqual(lead_identity({"CLAUDECODE": "1", "ANTHROPIC_BASE_URL": "https://example.com"}, cfg()),
                         "claude")                                   # unknown endpoint: still Claude Code

    def test_explicit_wins(self):
        self.assertEqual(lead_identity({"CCX_LEAD": "deepseek-codex", "CODEX_THREAD_ID": "t"}, cfg()),
                         "deepseek-codex")

    def test_vendor_is_deepseek_on_every_route(self):
        from ccx import agents
        for name in ("dsh", "deepseek", "deepseek-codex"):
            self.assertEqual(agents.vendor(name, cfg()), "deepseek", name)


class TestDesktopDsh(unittest.TestCase):
    def test_found_from_the_install_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(dsh.desktop_cli([d, ""]))
            cli = Path(d, *dsh.DESKTOP_CLI)
            cli.parent.mkdir(parents=True)
            cli.write_text("@echo off\n", encoding="utf-8")
            self.assertEqual(dsh.desktop_cli(["", d]), str(cli))

    def test_tests_never_find_a_real_one(self):
        import os
        self.assertEqual(os.environ.get("CCX_NO_LOCATE"), "1")
        self.assertIsNone(runners.find_bin("dsh-not-installed"))


class TestDeepSeekLeadRuns(Env):
    def j(self, *args, env=None):
        r = self.ccx(*args, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def rows(self):
        return [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_a_dsh_lead_is_recorded_as_deepseek(self):
        out = self.j("run", "--to", "codex", "--tier", "T1", "--mode", "read", "--no-ab", "look at a.py",
                     env={**self.env, "DSH_SESSION_ID": "session-lead"})
        row = next(r for r in self.rows() if r.get("run_id") == out["run_id"])
        self.assertEqual((row["caller"], row["caller_vendor"]), ("dsh", "deepseek"))
        # the sub-agent is not taken for the dsh lead
        call = [c for c in self.calls() if c.get("agent") == "codex"][-1]
        self.assertNotIn("DSH_SESSION_ID", json.dumps(call))

    def test_deepseek_behind_claude_code_leads_and_claude_works_on_anthropic(self):
        url = cfg()["providers"]["deepseek"]["env"]["ANTHROPIC_BASE_URL"]
        lead = {**self.env, "CLAUDECODE": "1", "ANTHROPIC_BASE_URL": url, "ANTHROPIC_API_KEY": "lead-key"}
        out = self.j("run", "--to", "claude", "--tier", "T1", "--mode", "read", "--no-ab", "look at a.py", env=lead)
        row = next(r for r in self.rows() if r.get("run_id") == out["run_id"])
        self.assertEqual((row["caller"], row["caller_vendor"]), ("deepseek", "deepseek"))
        call = [c for c in self.calls() if c.get("agent") == "claude"][-1]
        self.assertNotEqual(call["base_url"], url)                          # not the lead's DeepSeek endpoint
        self.assertIsNone(call["api_key"])                                  # nor its key

    def test_no_continuation_across_read_and_write_for_dsh(self):
        from ccx.commands.common import find_continuable
        from ccx.config import Paths
        p = Paths(self.hub)
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        import time
        row = {"run_id": "r1", "lead_session": "L", "cwd": str(self.work.resolve()), "to": "dsh", "mode": "read",
               "session_id": "s", "ts": time.time()}
        (self.hub / "ccx" / "ledger.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertEqual(find_continuable(p, "L", self.work, "dsh", "read"), "r1")
        self.assertIsNone(find_continuable(p, "L", self.work, "dsh", "write"))   # its session keeps read-only
        (self.hub / "ccx" / "ledger.jsonl").write_text(json.dumps({**row, "to": "codex"}) + "\n", encoding="utf-8")
        self.assertEqual(find_continuable(p, "L", self.work, "codex", "write"), "r1")  # flags on every call


if __name__ == "__main__":
    unittest.main()
