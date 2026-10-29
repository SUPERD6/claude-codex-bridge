"""PM review 2026-10-29, part A "honest story": the saving estimate no longer prices a sub-agent's start-up at the
lead's price and is never the headline; a write run without --check gets a one-line stderr nudge."""
import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from test_report import ReportEnv

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ccx" / "ui_static"


class TestTaskSizedEstimate(ReportEnv):
    def _summary(self):
        from ccx import report
        from ccx.config import paths
        with mock.patch.dict(os.environ, self.env), mock.patch.object(report, "_trial", return_value=None):
            p = paths()
            s = report.summarize(p, report.collect(p, 7, include_lead=False))
            return p, s, report.render_html(s)

    def test_task_sized_keeps_fresh_input_and_output_only(self):
        from ccx.report import task_sized
        u = {"input_tokens": 1200, "cache_write_tokens": 20000, "cached_input_tokens": 90000, "output_tokens": 300}
        self.assertEqual(task_sized(u), {"input_tokens": 1200, "output_tokens": 300})
        self.assertEqual(task_sized({}), {"input_tokens": 0, "output_tokens": 0})

    def test_saving_prices_only_the_task_sized_tokens_and_keeps_the_old_one_as_upper_bound(self):
        from ccx import learn
        from ccx.report import task_sized
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "implement")
        self.j("verify", out["run_id"], "--ok", "1")
        p, s, html = self._summary()
        t = s["totals"]
        with mock.patch.dict(os.environ, self.env):
            [e] = [x for x in report_events(p) if x["role"] == "sub"]
            from ccx.config import load_config
            lead = load_config(p).get("lead", {}).get("claude", "")
            over = learn.price_usd(p, "claude", lead, {"input_tokens": 1500 + 4000, "output_tokens": 400}) or 0.0
            want = learn.price_usd(p, "claude", lead, task_sized(e["usage"])) - e["ae"] - over
            upper = learn.price_usd(p, "claude", lead, e["usage"]) - e["ae"] - over
        self.assertEqual(t["saving_kind"], "model")
        self.assertAlmostEqual(t["saving"], round(want, 4), places=4)
        self.assertAlmostEqual(t["saving_upper"], round(upper, 4), places=4)
        self.assertLessEqual(t["saving"], t["saving_upper"])          # start-up no longer counted as lead spend
        self.assertIn("measured.md", t["saving_note"])
        self.assertIn("about even", t["saving_note"])

    def test_report_shows_spend_before_the_labelled_estimate(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "implement")
        self.j("verify", out["run_id"], "--ok", "1")
        _, _, html = self._summary()
        tiles = re.findall(r'<div class="k">([^<]+)</div>', html)
        self.assertEqual(tiles[-1], "Estimated saving (model)")            # demoted: after every spend tile
        self.assertLess(tiles.index("Sub-agent spend"), tiles.index("Estimated saving (model)"))
        self.assertIn("measured totals so far about even (docs/measured.md)", html)

    def test_stats_summary_puts_spend_first_and_labels_the_saving(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "implement")
        self.j("verify", out["run_id"], "--ok", "1")
        st = self.j("stats", "--summary")
        self.assertEqual(list(st)[:2], ["spend", "saving"])
        self.assertEqual(st["spend"]["runs"], 1)
        self.assertEqual(st["saving"]["kind"], "model")
        self.assertIn("model estimate", st["saving"]["note"])
        self.assertIn("docs/measured.md", st["saving"]["note"])
        self.assertIn("saving", st["totals"])                         # the old keys stay for scripts that read them


def report_events(p):
    from ccx import report
    return report.collect(p, 7, include_lead=False)["events"]


class TestUiWording(unittest.TestCase):
    def setUp(self):
        self.strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
        self.js = (STATIC / "app.js").read_text(encoding="utf-8")

    def test_model_estimate_is_labelled_and_links_the_measurements(self):
        for lang in ("en", "zh"):
            s = self.strings[lang]
            for k in ("month_saving", "month_extra"):
                self.assertIn("{link}", s[k], (lang, k))
            for k in ("month_saving_m", "month_extra_m"):
                self.assertIn(k, s, (lang, k))
        self.assertIn("Model estimate", self.strings["en"]["month_saving"])
        self.assertIn("about even", self.strings["en"]["month_saving"])
        self.assertIn("基本持平", self.strings["zh"]["month_saving"])
        self.assertNotIn("Relative estimate", json.dumps(self.strings))
        for lang in ("en", "zh"):
            self.assertTrue(self.strings[lang]["measured_url"].endswith("relayline/blob/main/docs/measured.md"))
        self.assertIn('t("measured_url")', self.js)

    def test_spend_comes_first_and_the_estimate_is_not_bold(self):
        body = self.js.split("function weekHTML()", 1)[1].split("\n  }", 1)[0]
        self.assertLess(body.index("monthSpentHTML()"), body.index("week_spent"))
        self.assertLess(body.index("week_spent"), body.index("monthSavingHTML()"))
        saving = self.js.split("function monthSavingHTML()", 1)[1].split("\n  }", 1)[0]
        self.assertNotIn("<b>", saving)


class TestHelpWording(unittest.TestCase):
    def test_help_does_not_promise_a_saving(self):
        from ccx import cli
        text = " ".join(cli.build_parser().format_help().split())
        for promise in ("this month's saving", "spend and savings", "quota and savings"):
            self.assertNotIn(promise, text)


class TestDocsAgree(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_skill_count_is_the_same_everywhere(self):
        n = len([d for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").exists()])
        word = {4: "four", 5: "five", 6: "six"}[n]
        market = json.loads(self.read(".claude-plugin/marketplace.json"))["plugins"][0]["description"]
        codex = json.loads(self.read(".codex-plugin/plugin.json"))["description"]
        for text in (market, codex):
            self.assertIn(f"The {word} relayline skills", text)

    def test_readme_leads_with_the_job_and_the_honest_comparison(self):
        for name, hold in (("README.md", "hold-out confirmation pending"), ("README.zh.md", "留出集确认还没做")):
            s = self.read(name)
            first = s.split("## ", 2)[1]                           # title block + the comparison section
            self.assertIn(hold, first, name)
            for must in ("builtin2", "$0.114", "$0.135", "$0.116–0.135"):
                self.assertIn(must, first, (name, must))
            self.assertNotIn("Four pillars", s)
            self.assertNotIn("四根柱子", s)
            quick = s.split("```bash", 2)[2]
            self.assertIn("--check", quick.split("```", 1)[0], name)

    def test_best_case_numbers_live_in_measured(self):
        for name in ("docs/measured.md", "docs/measured.zh.md"):
            s = self.read(name)
            self.assertIn("36/36", s)
            self.assertIn("builtin2", s)
            self.assertNotIn("README's four numbers", s)

    def test_faq_has_the_builtin_row_and_no_discuss_contradiction(self):
        en, zh = self.read("docs/faq.md"), self.read("docs/faq.zh.md")
        self.assertIn("| Claude Code's built-in sub-agent", en)
        self.assertIn("| Claude Code 自带的子智能体", zh)
        self.assertNotIn("One way, for now", en)
        self.assertNotIn("现在能做的是单向的", zh)
        self.assertNotIn("multi-provider consensus", en)


class TestNoCheckNudge(ReportEnv):
    def test_write_run_without_check_gets_one_stderr_line(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--mode", "write", "add a helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sum("no --check" in ln for ln in r.stderr.splitlines()), 1, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "done")      # stdout is still the one JSON result
        self.assertNotIn("no --check", r.stdout)

    def test_no_nudge_with_a_check_or_for_a_read_run(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--mode", "write",
                     "--check", "python -c pass", "add a helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("no --check", r.stderr)
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--mode", "read", "explain x")
        self.assertNotIn("no --check", r.stderr)


if __name__ == "__main__":
    unittest.main()
