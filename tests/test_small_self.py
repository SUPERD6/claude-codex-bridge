"""P0-6 routing.small_self: `ccx route` / `ccx propose` advise doing a small task yourself (off by default)."""
import unittest

from test_report import ReportEnv

ROUTE = ("route", "--b", "4", "--to", "codex")


class TestSmallSelf(ReportEnv):
    def on(self):
        self.j("config", "set", "routing.small_self", "on")

    def test_off_by_default(self):
        out = self.j(*ROUTE, "--files", "1")
        self.assertNotIn("small_self", out)
        self.assertNotIn("advice", out)
        self.assertTrue(out["rung"].startswith("codex:"))

    def test_small_task_is_do_it_yourself(self):
        self.on()
        out = self.j(*ROUTE, "--files", "1")
        ss = out["small_self"]
        self.assertEqual((ss["applied"], ss["files"], ss["files_from"]), (True, 1, "--files"))
        self.assertTrue(out["advice"].startswith("do-it-yourself: small task"))
        self.assertTrue(out["rung"].startswith("codex:"))           # routing itself is unchanged
        from ccx.commands.delegation import _route_summary
        self.assertEqual(_route_summary(out)[-1], "Next: do it yourself")

    def test_not_small(self):
        self.on()
        for extra in (("--files", "2"), ()):
            out = self.j(*ROUTE, *extra)
            self.assertNotIn("small_self", out, extra)
            self.assertNotIn("advice", out, extra)

    def test_exceptions_keep_delegating(self):
        self.on()
        for extra, word in ((("--needs", "undo"), "--needs"), (("--lead-ctx", "200000"), "context is large"),
                            (("--lead", "claude:opus:high", "--quota", "claude=0.95"), "quota is tight")):
            out = self.j(*ROUTE, "--files", "1", *extra)
            self.assertFalse(out["small_self"]["applied"], extra)
            self.assertIn(word, out["small_self"]["why"])
            self.assertNotIn("advice", out, extra)
        self.j("config", "set", "policy.picked", "save")          # the person's tier wins
        out = self.j(*ROUTE, "--files", "1")
        self.assertFalse(out["small_self"]["applied"])
        self.assertIn("policy.picked", out["small_self"]["why"])

    def test_threshold_from_config(self):
        self.on()
        self.j("config", "set", "routing.small_self_files", "2")
        self.assertTrue(self.j(*ROUTE, "--files", "2")["small_self"]["applied"])

    def test_keyword_route(self):
        self.on()
        text = "add a helper that parses the date strings and wire it into the report command output"
        self.assertNotEqual(self.j("route", text)["tier"], "T0")
        self.assertNotIn("small_self", self.j("route", text))
        out = self.j("route", "--files", "1", text)
        self.assertTrue(out["small_self"]["applied"])
        from ccx.commands.delegation import _route_summary
        self.assertEqual(_route_summary(out)[-1], "Next: do it yourself")

    def test_brief_named_file(self):
        self.on()
        (self.work / "mod.py").write_text("x = 1\n", encoding="utf-8")
        out = self.j(*ROUTE, "--risk", "low", "change mod.py so x is 2")
        self.assertEqual((out["small_self"]["files"], out["small_self"]["files_from"]), (1, "brief"))

    def test_propose_and_run(self):
        self.on()
        pr = self.j("propose", "--b", "4", "--to", "codex", "--files", "1", "--lead", "claude:opus:high",
                    "--lead-ctx", "0", "add a parser")
        self.assertEqual((pr["worth_offering"], pr["recommend"]), (False, "self"))
        long = self.j("propose", "--minutes", "30", "--to", "codex", "--files", "1", "--lead", "claude:opus:high",
                      "--lead-ctx", "0", "add a parser")                 # the offer path passes 15+ minutes
        self.assertTrue(long["small_self"]["applied"])
        rt = self.j(*ROUTE, "--files", "1", "--lead", "claude:opus:high", "--lead-ctx", "0")
        self.assertEqual(rt["choice"]["recommend"], "self")
        self.assertTrue(pr["small_self"]["applied"])
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "--files", "1", "add a parser")
        self.assertEqual(out["status"], "done", out)             # an explicit `ccx run` still delegates


if __name__ == "__main__":
    unittest.main()
