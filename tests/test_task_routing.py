"""Tests for the standalone task-routing skill script."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "task-routing" / "scripts" / "task_routing.py"
spec = importlib.util.spec_from_file_location("task_routing", SCRIPT)
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)


class TestMath(unittest.TestCase):
    def setUp(self):       # the math on the hand-set priors; the built-in A/B head start is tested in TestObserved
        self.pri = {k: v for k, v in tr.load_priors().items() if k != "observed"}
        self.state = {"offsets": {}, "counts": {}, "outcomes": []}
        os.environ.pop("CODEX_HOME", None)

    def test_difficulty_bounds(self):
        self.assertEqual(tr.difficulty(1, "one", "spec", "low", "pattern"), 0)
        self.assertEqual(tr.difficulty(20, "system", "unknown", "critical", "new"), 10)

    def test_irt_midpoint_and_monotone(self):
        a = self.pri["irt"]["a"]
        self.assertAlmostEqual(tr.p_success(5, 5, a), 0.5)
        self.assertGreater(tr.p_success(7, 5, a), tr.p_success(6, 5, a))

    def test_effort_raises_cost(self):
        lo = next(r for r in self.pri["rungs"] if tr.rung_key(r) == "codex:gpt-6-luna:low")
        hi = next(r for r in self.pri["rungs"] if tr.rung_key(r) == "codex:gpt-6-luna:high")
        self.assertLess(tr.attempt_cost(lo, 4, self.pri)["usd"], tr.attempt_cost(hi, 4, self.pri)["usd"])

    def test_easy_task_picks_cheap_and_says_self(self):
        res = tr.route(0, self.pri, self.state, ["codex", "claude"])
        self.assertRegex(res["pick"]["rung"], "luna|haiku")                 # the cheapest tier
        self.assertTrue(res["advice"].startswith("do-it-yourself"))

    def test_hard_task_picks_stronger(self):
        easy = tr.route(2, self.pri, self.state, ["codex"])["pick"]["theta"]
        hard = tr.route(7, self.pri, self.state, ["codex"])["pick"]["theta"]
        self.assertGreater(hard, easy)

    def test_impossible_task_says_split(self):
        res = tr.route(10, self.pri, self.state, ["codex", "claude"])
        self.assertTrue(res["advice"].startswith("split"))

    def test_fast_tradeoff_no_cascade_and_meets_tau(self):
        res = tr.route(4, self.pri, self.state, ["claude"], tradeoff="fast")
        self.assertIn("no cascade", res["rule"])
        self.assertGreaterEqual(res["pick"]["p"], 0.9)

    def test_not_verifiable_disables_cascade(self):
        res = tr.route(4, self.pri, self.state, ["codex"], verifiable=False)
        self.assertIn("not verifiable", res["rule"])

    def test_learning_moves_theta(self):
        before = tr.route(5, self.pri, self.state, ["codex"])
        for _ in range(5):
            tr.record("codex:gpt-6.1-sol:medium", 5, True, self.pri, self.state)
        self.assertGreater(self.state["offsets"]["codex:gpt-6.1-sol:medium"], 0)
        tr.record("codex:gpt-6-luna:high", 5, False, self.pri, self.state)
        self.assertLess(self.state["offsets"]["codex:gpt-6-luna:high"], 0)

    def test_model_discovery_filters_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "models_cache.json").write_text(json.dumps({"models": [
                {"slug": "gpt-6-luna", "visibility": "list"},
                {"slug": "gpt-7-nova", "visibility": "list"}]}))
            os.environ["CODEX_HOME"] = d
            try:
                res = tr.route(3, self.pri, self.state, ["codex"])
            finally:
                os.environ.pop("CODEX_HOME")
        self.assertTrue(all("luna" in x["rung"] for x in res["rows"]))
        self.assertEqual(res["new_models_without_prior"], ["gpt-7-nova"])


    def test_three_way_choice(self):
        tw = lambda **kw: tr.three_way(pri=self.pri, state=self.state, lead="claude:opus:high",   # noqa: E731
                                       delegate_agents=["codex", "claude"], ctx_tokens=150000, remaining_turns=20, **kw)
        r = tw(b=3)
        ways = {o["way"]: o for o in r["options"]}
        self.assertEqual(set(ways), {"self", "builtin", "delegate"})
        self.assertTrue(ways["builtin"]["rung"].startswith("claude-builtin:"))
        single = tr.p_success(next(x for x in self.pri["rungs"] if f"claude:{x['model']}:{x['effort']}" ==
                                   ways["builtin"]["rung"].replace("claude-builtin", "claude"))["theta"], 3,
                              self.pri["irt"]["a"])
        self.assertAlmostEqual(ways["builtin"]["p"], round(single, 3))     # one attempt: no escalation
        self.assertNotIn("builtin", {o["way"] for o in tw(b=3, needs=("undo",))["options"]})
        hot = tw(b=3, quota={"codex": 0.95})                                 # codex nearly out: not codex
        self.assertNotEqual(hot["rung"].split(":")[0], "codex")
        self.assertIn("codex 91% of API (95% used)", hot["why"])
        small = tr.three_way(b=2, pri=self.pri, state=self.state, lead="claude:haiku:low",
                             delegate_agents=["codex"], ctx_tokens=0, remaining_turns=1)
        self.assertEqual(small["recommend"], "self")                         # a cheap lead keeps small work

    def test_total_cost_trades_money_against_quota(self):
        self.assertEqual(tr.shadow_lambda(None), 0.3)                       # floor: quota is kept for the lead
        self.assertEqual(tr.shadow_lambda(0.5), 0.3)
        self.assertAlmostEqual(tr.shadow_lambda(0.8), 0.65)                 # rising from 60% used...
        self.assertEqual(tr.shadow_lambda(1.0), 2.0)                        # ...doubled when it would run out
        rows = lambda q: {x["rung"]: x for x in tr.route(3, self.pri, self.state, ["codex", "deepseek"],   # noqa: E731
                                                         quota=q)["rows"]}
        calm, hot = rows({"codex": 0.2}), rows({"codex": 0.99})
        luna = "codex:gpt-6-luna:high"
        self.assertGreater(hot[luna]["total"]["quota"], calm[luna]["total"]["quota"])
        ds = "deepseek:deepseek-flash:low"
        self.assertEqual(calm[ds]["total"]["quota"], 0)                     # pay per token: money, not quota
        self.assertGreater(calm[ds]["total"]["money"], 0)
        self.assertEqual(calm[ds]["total"]["money"], hot[ds]["total"]["money"])
        risky = tr.route(3, self.pri, self.state, ["codex"], risk="critical")["pick"]["total"]["risk"]
        self.assertGreater(risky, tr.route(3, self.pri, self.state, ["codex"])["pick"]["total"]["risk"])

    def test_three_way_prices_the_leads_quota(self):
        tw = lambda **kw: tr.three_way(b=3, pri=self.pri, state=self.state, lead="claude:opus:high",   # noqa: E731
                                       delegate_agents=["codex", "deepseek"], ctx_tokens=50000,
                                       remaining_turns=10, **kw)
        calm, hot = tw(quota={"claude": 0.2}), tw(quota={"claude": 0.99})
        own = lambda r: next(o for o in r["options"] if o["way"] == "self")["total"]                  # noqa: E731
        self.assertGreater(own(hot), own(calm))                             # doing it yourself costs more quota
        self.assertEqual(hot["recommend"], "delegate")

    def test_deepseek_ladder_continues_on_claude(self):
        rows = tr.route(3, self.pri, self.state, ["deepseek", "claude"], max_escalations=3)["rows"]
        flash = next(x for x in rows if x["rung"] == "deepseek:deepseek-flash:low")
        self.assertEqual(flash["escalates_to"][:2], ["deepseek:deepseek-flash:high", "deepseek:deepseek-flash:max"])
        self.assertTrue(flash["escalates_to"][2].startswith("claude:"))       # then Claude, never v4-pro
        self.assertFalse(any("v4-pro" in x["rung"] for x in rows))

    def test_deepseek_effort_follows_difficulty(self):
        # one attempt (not verifiable, no escalation): the effort has to fit the difficulty up front
        pick = lambda b: tr.route(b, self.pri, self.state, ["deepseek"], verifiable=False)["pick"]["rung"]  # noqa: E731
        self.assertTrue(pick(1).endswith(":low"))
        self.assertFalse(pick(3).endswith(":low"))                             # harder work: high or max

    def test_offpeak_price(self):
        import calendar
        at = lambda *t: calendar.timegm((2026, 10, *t, 0, 0, 0, 0))   # noqa: E731
        self.assertEqual(tr.price_mult(self.pri, "deepseek", at(26, 2, 30)), 1.0)    # Monday 02:30 UTC: peak
        self.assertEqual(tr.price_mult(self.pri, "deepseek", at(26, 12, 0)), 0.5)    # Monday noon: off-peak
        self.assertEqual(tr.price_mult(self.pri, "deepseek", at(24, 2, 30)), 0.5)    # Saturday: off-peak
        self.assertEqual(tr.price_mult(self.pri, "claude", at(26, 2, 30)), 1.0)

    def test_builtin_startup_is_measured_not_slim(self):
        r = {"agent": "claude-builtin", "model": "haiku", "effort": "low"}
        self.assertEqual(tr.startup_tokens(self.pri, r), self.pri["cost"]["startup_by"]["claude-builtin"])

    def test_startup_tokens_by_mode(self):
        rung = lambda agent, effort: next(r for r in self.pri["rungs"] if r["agent"] == agent and r["effort"] == effort)  # noqa: E731
        c = self.pri["cost"]
        self.assertEqual(tr.startup_tokens(self.pri, rung("codex", "low")), c["startup_by"]["codex:lean"])
        self.assertEqual(tr.startup_tokens(self.pri, rung("codex", "high")), c["startup_tokens"]["codex"])
        hk = rung("claude", "low")
        self.assertEqual(tr.startup_tokens(self.pri, hk, "read"), c["startup_by"]["claude:read"])
        self.assertEqual(tr.startup_tokens(self.pri, hk, "write"), c["startup_tokens"]["claude"])
        self.assertLess(tr.attempt_cost(hk, 3, self.pri, mode="read")["input"],
                        tr.attempt_cost(hk, 3, self.pri, mode="write")["input"])

    def test_unavailable_mark_expires_and_follows_cli_version(self):
        tr.mark_unavailable(self.state, "codex", "gpt-6-luna", cli="codex-cli 0.153.0")
        self.assertTrue(tr.unavailable(self.state, "codex", "gpt-6-luna", cli="codex-cli 0.153.0"))
        self.assertTrue(tr.unavailable(self.state, "codex", "gpt-6-luna"))         # version unknown: still counts
        self.assertFalse(tr.unavailable(self.state, "codex", "gpt-6-luna", cli="codex-cli 0.164.0"))
        self.state["unavailable"]["codex:gpt-6-luna"]["ts"] -= 8 * 86400
        self.assertFalse(tr.unavailable(self.state, "codex", "gpt-6-luna"))
        self.state["unavailable"]["codex:gpt-6-luna"] = __import__("time").time()  # old format: bare timestamp
        self.assertTrue(tr.unavailable(self.state, "codex", "gpt-6-luna", cli="codex-cli 0.164.0"))


    def test_ccx_works_with_an_older_skill_copy(self):
        sys.path.insert(0, str(ROOT))
        from ccx.learn import _with_cli
        old = lambda state, agent, model: "old"            # noqa: E731 — signature before the cli argument
        self.assertEqual(_with_cli(old, {}, "codex", "m", cli="v"), "old")
        self.assertTrue(_with_cli(tr.unavailable, {"unavailable": {"codex:m": {"ts": 1e18, "cli": "v"}}},
                                  "codex", "m", cli="v"))

class TestObserved(unittest.TestCase):
    """A/B round 1 as a low-weight head start for rungs this hub has not learned yet."""
    def setUp(self):
        self.pri = tr.load_priors()
        self.a = self.pri["irt"]["a"]

    def theta(self, k):
        return next(r["theta"] for r in self.pri["rungs"] if tr.rung_key(r) == k)

    def test_shift_goes_part_way_toward_what_was_observed(self):
        off = tr.observed_offsets(self.pri)
        self.assertEqual(set(off), {"codex:gpt-6-luna:low", "claude:sonnet:medium"})
        k = "codex:gpt-6-luna:low"
        before, after = (tr.p_success(self.theta(k) + d, 2.32, self.a) for d in (0, off[k]))
        self.assertLess(before, after)
        self.assertLess(after, 38 / 45)                    # weight 0.5: part of the way, not all of it
        self.assertTrue(0 < off["claude:sonnet:medium"] <= 1.5)    # 42 of 42: finite, within the cap
        none = tr.observed_offsets({**self.pri, "observed": {**self.pri["observed"], "weight": 0}})
        self.assertEqual(set(none.values()), {0.0})

    def test_used_until_the_hub_learns_the_rung(self):
        k = "codex:gpt-6-luna:low"
        fresh = {"offsets": {}, "counts": {}, "outcomes": []}
        self.assertEqual(tr.offset(fresh, self.pri, k), tr.observed_offsets(self.pri)[k])
        self.assertEqual(tr.offset({"offsets": {k: -0.2}}, self.pri, k), -0.2)
        self.assertEqual(tr.offset(fresh, self.pri, "claude:haiku:low"), 0.0)
        res = tr.route(2.32, self.pri, fresh, ["codex"])
        row = next(x for x in res["rows"] if x["rung"] == k)
        self.assertAlmostEqual(row["theta"], round(self.theta(k) + tr.observed_offsets(self.pri)[k], 2), places=2)
        out = tr.record(k, 2.32, True, self.pri, fresh)    # the first outcome builds on the head start
        self.assertGreater(fresh["offsets"][k], tr.observed_offsets(self.pri)[k])
        self.assertGreater(out["predicted_p"], tr.p_success(self.theta(k), 2.32, self.a))


class TestCLI(unittest.TestCase):
    def test_route_record_show_standalone(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "TASK_ROUTING_HOME": d}
            env.pop("CCX_HUB", None)
            run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], env=env,  # noqa: E731
                                            capture_output=True, text=True, cwd=d)
            r = run("route", "--files", "3", "--coupling", "cross", "--clarity", "goal",
                    "--risk", "low", "--novelty", "pattern", "--lead", "claude:opus:high",
                    "--ctx-tokens", "60000")
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertIn(out["self_vs_delegate"]["recommend"], ("self", "delegate"))
            r = run("record", "--rung", out["pick"], "--b", str(out["b"]), "--ok", "1")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(Path(d, "state.json").exists())
            self.assertIn(out["pick"], run("show").stdout)



class TestSharedState(unittest.TestCase):
    def test_state_in_hub_when_installed_under_skills(self):
        with tempfile.TemporaryDirectory() as hub:
            import shutil
            dst = Path(hub) / "skills" / "task-routing"
            shutil.copytree(SCRIPT.parent.parent, dst)
            (Path(hub) / "AGENTS.md").write_text("# hub marker\n")
            env = {k: v for k, v in os.environ.items() if k not in ("TASK_ROUTING_HOME", "CCX_HUB")}
            r = subprocess.run([sys.executable, str(dst / "scripts" / "task_routing.py"), "record",
                                "--rung", "codex:gpt-6-luna:low", "--b", "2", "--ok", "1"],
                               env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((Path(hub) / "ccx" / "routing-state.json").exists())


class TestBenchmarks(unittest.TestCase):
    """Fetching is replaced by canned bytes: tests never touch the network."""
    def setUp(self):
        self.b = tr.bench()
        self.d = Path(tempfile.mkdtemp()) / "benchmarks.json"

    @staticmethod
    def _zip():
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("epoch_capabilities_index/eci_scores.csv",
                       "Model,Display name,eci,eci_ci_low,eci_ci_high,date\nm1,Model One,150.5,148,153,2026-10-01\n")
            z.writestr("frontiercode_external.csv",
                       "Model version,Main score,Harness,Reasoning effort,Release date\nm1_high,0.44,codex,high,2026-10-01\n")
            z.writestr("gpqa_diamond.csv", "Model version,mean_score,Best score (across scorers),Release date,stderr\n"
                                           "m1_max,0.9,0.91,2026-10-01,0.01\n")
        return buf.getvalue()

    def _get(self, url):
        if url.endswith(".zip"):
            return self._zip()
        if "datasets-server" in url:
            if "offset=0" in url and "config=text&" in url:
                return json.dumps({"rows": [{"row": {"model_name": "Model One (Max)", "rating": 1450.0,
                                                     "rating_lower": 1440.0, "rating_upper": 1460.0}}]}).encode()
            return json.dumps({"rows": []}).encode()
        return json.dumps({"openai": {"models": {"m1": {"cost": {"input": 0.1, "output": 0.5}}}}}).encode()

    def test_refresh_parses_all_three_sources_and_credits_them(self):
        s = self.b.refresh(self.d, get=self._get)
        self.assertTrue(all(v["ok"] for v in s["sources"].values()))
        self.assertTrue(any("CC BY 4.0" in c for c in s["credit"]))
        d = self.b.load(self.d)
        by = {(x["benchmark"], x["model"]): x for x in d["scores"]}
        self.assertEqual(by[("eci", "m1")]["lo"], 148.0)
        self.assertEqual((by[("frontiercode", "m1_high")]["effort"], by[("frontiercode", "m1_high")]["harness"]),
                         ("high", "codex"))
        self.assertAlmostEqual(by[("gpqa_diamond", "m1_max")]["hi"], 0.91 + 1.96 * 0.01)
        self.assertIn(("lmarena_text", "Model One (Max)"), by)
        self.assertEqual(d["prices"]["openai/m1"]["input"], 0.1)
        self.assertFalse(self.b.is_stale(self.d))

    def test_a_failing_source_keeps_the_old_data(self):
        self.b.refresh(self.d, get=self._get)
        def broken(url):
            if url.endswith(".zip"):
                raise OSError("offline")
            return self._get(url)
        s = self.b.refresh(self.d, get=broken)
        self.assertFalse(s["sources"]["epoch"]["ok"])
        self.assertFalse(self.b.is_stale(self.d))                       # not straight away...
        d = self.b.load(self.d)
        d["fetched_at"] -= 7 * 3600
        self.d.write_text(json.dumps(d), encoding="utf-8")
        self.assertTrue(self.b.is_stale(self.d))                        # ...but a failed source is retried after 6 h
        self.d.write_text(json.dumps({**d, "fetched_at": d["fetched_at"] + 7 * 3600}), encoding="utf-8")
        self.assertIn("offline", s["sources"]["epoch"]["error"])
        self.assertTrue(any(x["benchmark"] == "eci" for x in self.b.load(self.d)["scores"]))

    def test_local_plugins_add_a_source_and_their_kind_weights(self):
        d = Path(tempfile.mkdtemp())
        (d / "mine.py").write_text(
            "NAME = 'mine'\nCREDIT = 'my data'\nKIND_WEIGHTS = {'code': {'my_index': 2}}\n"
            "def fetch(get):\n    return [{'benchmark': 'my_index', 'model': 'm1', 'score': 1.0, 'effort': ''}]\n",
            encoding="utf-8")
        (d / "off.py").write_text("NAME = 'off'\ndef available():\n    return False\n"
                                  "def fetch(get):\n    raise RuntimeError('should not run')\n", encoding="utf-8")
        (d / "broken.py").write_text("this is not python", encoding="utf-8")
        s = self.b.refresh(self.d, get=self._get, plugin_dirs=[d])
        self.assertTrue(s["sources"]["mine"]["ok"])
        self.assertEqual(s["sources"]["off"]["n"], 0)                    # skipped, not failed
        data = self.b.load(self.d)
        self.assertTrue(any(x["source"] == "mine" for x in data["scores"]))
        self.assertEqual(data["kind_weights"]["code"]["my_index"], 2)
        self.assertIn("my data", s["credit"])

    def test_stale_after_a_week(self):
        self.assertTrue(self.b.is_stale(self.d))                        # no cache yet
        self.b.refresh(self.d, get=self._get)
        d = self.b.load(self.d)
        d["fetched_at"] -= 8 * 86400
        self.d.write_text(json.dumps(d), encoding="utf-8")
        self.assertTrue(self.b.is_stale(self.d))


class TestCalibration(unittest.TestCase):
    def setUp(self):
        self.pri = tr.load_priors()
        self.state = {"offsets": {}, "counts": {}, "outcomes": []}

    def test_cost_factor_follows_observed_costs(self):
        rung = "codex:gpt-6.1-sol:medium"
        r = next(x for x in self.pri["rungs"] if tr.rung_key(x) == rung)
        est = tr.attempt_cost(r, 4, self.pri)["usd"]
        for _ in range(8):
            tr.record(rung, 4, True, self.pri, self.state, cost_usd=est * 3)   # reality is 3x the model
        f = self.state["cost_factor"][rung]
        self.assertGreater(f, 2.5)
        row = next(x for x in tr.route(4, self.pri, self.state, ["codex"])["rows"] if x["rung"] == rung)
        self.assertTrue(row["cost"]["calibrated"])
        self.assertAlmostEqual(row["cost"]["usd"], est * f, places=6)

    def test_repo_checkout_is_not_a_hub(self):
        self.assertIsNone(tr.installed_hub(ROOT / "skills"))


if __name__ == "__main__":
    unittest.main()


class TestMerge(unittest.TestCase):
    """Benchmarks become rung abilities: fit on anchor rungs, read off the rest, weight by fit and relevance."""
    def setUp(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import merge
        self.m = merge
        self.rungs = [{"agent": "claude", "model": "haiku", "effort": "max", "theta": 3.0},
                      {"agent": "claude", "model": "sonnet", "effort": "max", "theta": 5.0},
                      {"agent": "claude", "model": "opus", "effort": "max", "theta": 8.0},
                      {"agent": "codex", "model": "luna", "effort": "max", "theta": 4.0},
                      {"agent": "codex", "model": "sol", "effort": "max", "theta": 7.0},
                      {"agent": "deepseek", "model": "flash", "effort": "max", "theta": 2.0},
                      {"agent": "deepseek", "model": "flash", "effort": "low", "theta": 1.0}]
        self.aliases = {"haiku": [("claudehaiku55", 1)], "sonnet": [("claudesonnet55", 1)],
                        "opus": [("claudeopus55", 1)], "luna": [("gpt6luna", 1)], "sol": [("gpt61sol", 1)],
                        "flash": [("deepseekv41flash1017", 1), ("deepseekv41flash", 0.5)]}

    def rows(self, bench, pairs):
        return [{"benchmark": bench, "model": n, "score": s, "effort": ""} for n, s in pairs]

    def test_split_name(self):
        self.assertEqual(self.m.split_name("claude-haiku-5-5_max"), ("claudehaiku55", "max"))
        self.assertEqual(self.m.split_name("Claude Haiku 5.5 (High)"), ("claudehaiku55", "high"))
        self.assertEqual(self.m.split_name("DeepSeek-V4-Pro (High, 20260813)"), ("deepseekv4pro20260813", "high"))
        self.assertEqual(self.m.split_name("gpt-6-astra_unknown"), ("gpt6astra", ""))

    def test_a_linear_benchmark_reproduces_the_anchors_and_places_the_rest(self):
        # score = 10 * theta for every anchor; flash (not an anchor: other agent) scores like theta 6
        s = self.rows("frontiercode", [("claude-haiku-5-5_max", 30), ("claude-sonnet-5-5_max", 50),
                                       ("claude-opus-5-5_max", 80), ("gpt-6-luna_max", 40), ("gpt-6.1-sol_max", 70),
                                       ("deepseek-v4.1-flash-1017_max", 60)])
        out = self.m.merged_thetas(s, self.rungs, self.aliases, kind="code")
        self.assertAlmostEqual(out["deepseek:flash:max"]["bench_theta"], 6.0, places=1)
        self.assertGreater(out["deepseek:flash:max"]["theta"], 4.5)     # pulled from the prior 2.0 toward 6
        # the low-effort rung gets the same row moved down by the effort shift
        self.assertAlmostEqual(out["deepseek:flash:low"]["bench_theta"], 6.0 - 2.8, places=1)
        self.assertEqual(out["claude:opus:max"]["used"][0][0], "frontiercode")

    def test_an_older_version_counts_less_and_too_few_anchors_change_nothing(self):
        base = [("claude-haiku-5-5_max", 30), ("claude-sonnet-5-5_max", 50), ("claude-opus-5-5_max", 80),
                ("gpt-6-luna_max", 40)]
        s = self.rows("eci", base + [("deepseek-v4.1-flash_max", 60)]) + \
            self.rows("frontiercode", base + [("deepseek-v4.1-flash-1017_max", 20)])
        out = self.m.merged_thetas(s, self.rungs, self.aliases, kind="code")
        used = dict(out["deepseek:flash:max"]["used"])
        self.assertGreater(used["frontiercode"], used["eci"])          # exact version beats the older one
        few = self.m.merged_thetas(self.rows("eci", base[:3]), self.rungs, self.aliases)
        self.assertIsNone(few["deepseek:flash:max"]["bench_theta"])     # 3 anchors < 4: benchmark skipped

    def test_kind_changes_which_benchmarks_count(self):
        s = self.rows("simpleqa_verified", [("claude-haiku-5-5_max", 30), ("claude-sonnet-5-5_max", 50),
                                            ("claude-opus-5-5_max", 80), ("gpt-6-luna_max", 40),
                                            ("deepseek-v4.1-flash-1017_max", 70)])
        self.assertIsNone(self.m.merged_thetas(s, self.rungs, self.aliases, kind="code")
                          ["deepseek:flash:max"]["bench_theta"])
        self.assertIsNotNone(self.m.merged_thetas(s, self.rungs, self.aliases, kind="research")
                             ["deepseek:flash:max"]["bench_theta"])

    def test_route_uses_the_cache_when_there_is_one(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["TASK_ROUTING_HOME"] = d
            try:
                pri = tr.load_priors()
                plain = tr.route(3, pri, {"offsets": {}, "counts": {}}, ["claude"])["rows"]
                self.assertNotIn("bench", plain[0])
                rows = [{"source": "epoch", "benchmark": "eci", "model": m, "score": sc, "effort": e}
                        for m, sc, e in [("claude-haiku-5-5", 10, "low"), ("claude-sonnet-5-5", 40, "medium"),
                                         ("claude-sonnet-5-5", 45, "high"), ("claude-opus-5-5", 60, "high"),
                                         ("claude-opus-5-5", 70, "max")]]
                Path(d, "benchmarks.json").write_text(json.dumps({"fetched_at": 1, "scores": rows}),
                                                      encoding="utf-8")
                tr._MERGE_CACHE.clear()
                merged = tr.route(3, pri, {"offsets": {}, "counts": {}}, ["claude"])["rows"]
                self.assertTrue(all("bench" in r for r in merged))
                self.assertTrue(all("theta_prior" in r for r in merged))
            finally:
                os.environ.pop("TASK_ROUTING_HOME")
                tr._MERGE_CACHE.clear()


class TestDifficultyUnit(unittest.TestCase):
    def test_minutes_to_b_and_blend(self):
        self.assertEqual(tr.b_from_minutes(1), 0)
        self.assertEqual(tr.b_from_minutes(8), 3)
        self.assertEqual(tr.b_from_minutes(10 ** 6), 10)
        d = tr.combine_difficulty(5, 8)                                   # rubric 5, 8 minutes -> 3
        self.assertAlmostEqual(d["b"], 0.6 * 3 + 0.4 * 5)
        self.assertEqual(tr.combine_difficulty(None, 64)["b"], 6)
        self.assertEqual(tr.combine_difficulty(4, None, bias=0.5)["parts"]["lead_bias"], 0.5)
        self.assertAlmostEqual(tr.h50_minutes(6), 64)

    def test_a_lead_that_underestimates_gets_a_higher_b(self):
        st = {}
        for _ in range(5):
            tr.record_bias(st, "claude", ok=False, predicted_p=0.9)
        self.assertGreater(tr.lead_bias(st, "claude"), 0.3)
        self.assertEqual(tr.lead_bias(st, "codex"), 0.0)
        self.assertEqual(len(st["difficulty_log"]), 5)

    def test_refit_needs_data_then_finds_the_item_that_matters(self):
        self.assertIn("need at least", tr.refit({})["note"])
        log = []
        for i in range(60):
            many = i % 2 == 0                                             # many files -> fails, one file -> works
            log.append({"items": {"files": 9 if many else 1, "coupling": "one", "clarity": "goal", "risk": "low",
                                  "novelty": "pattern"}, "ok": not many, "minutes": None})
        w = tr.refit({"difficulty_log": log})["weights"]
        self.assertGreater(w["files"], 0.3)
        self.assertAlmostEqual(w["risk"], 0.0, places=2)
