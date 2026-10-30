"""`ccx batch --merge` (ccx/merge.py, B3 item 5): small independent write pieces become one run; each piece keeps its
own check, result line and `undo --piece`. Opt-in: without the flag `ccx batch` behaves as before. Fakes only."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccx import merge  # noqa: E402
from ccx.delegate import Request  # noqa: E402
from test_adapters import AdapterEnv  # noqa: E402

FAIL = 'python -c "import sys; sys.exit(1)"'
PASS = 'python -c "import sys; sys.exit(0)"'


def req(label, to="codex", tier="T1", mode="write", cwd=".", **kw):
    return Request(to=to, brief=f"do {label}", tier=tier, mode=mode, cwd=Path(cwd), label=label, **kw)


M2 = {"minutes": 2}


class TestGrouping:
    def test_same_key_without_shared_paths_merges_up_to_the_limits(self):
        items = [(req(f"p{i}"), {"id": f"p{i}", "minutes": 2}) for i in range(7)]
        assert merge.groups(items, {}) == [[0, 1, 2, 3, 4], [5, 6]]           # max_pieces 5
        cfg = {"merge": {"max_pieces": 10, "total_minutes": 6}}
        assert merge.groups(items, cfg) == [[0, 1, 2], [3, 4, 5], [6]]        # 2 + 2 + 2 <= 6

    def test_what_keeps_pieces_apart(self):
        a, b = req("a"), req("b")
        assert merge.groups([(a, {"paths": ["x.py"], **M2}), (b, {"paths": ["./x.py", "y.py"], **M2})], {}) == [[0], [1]]
        assert merge.groups([(a, {"paths": ["x.py"], **M2}), (b, {"paths": ["z.py"], **M2})], {}) == [[0, 1]]
        assert merge.groups([(a, M2), (b, {"paths": ["z.py"], **M2})], {}) == [[0, 1]]        # undeclared: may merge
        for other in (req("b", to="claude"), req("b", tier="T2"), req("b", cwd="elsewhere"), req("b", worktree=True),
                      req("b", namecheck="fail")):
            assert merge.groups([(a, M2), (other, M2)], {}) == [[0], [1]]
        assert merge.groups([(req("a", mode="read"), M2), (req("b", mode="read"), M2)], {}) == [[0], [1]]  # write only
        assert merge.groups([(a, {"minutes": 12}), (b, M2)], {}) == [[0], [1]]          # too big a piece
        assert merge.groups([(a, {}), (b, M2)], {}) == [[0], [1]]                        # no estimate: may be big
        assert merge.groups([(a, {"minutes": "x"}), (b, M2)], {}) == [[0], [1]]
        assert merge.groups([(req("a", task="t", step=1), M2), (b, M2)], {}) == [[0], [1]]   # checkpoint steps
        # a later piece that fits an earlier open group joins it; order inside stays the plan's
        assert merge.groups([(a, M2), (req("c", to="claude"), M2), (b, M2)], {}) == [[0, 2], [1]]

    def test_settings_and_choice(self):
        s = merge.settings({"merge": {"default": "yes", "max_pieces": 0, "piece_minutes": "3", "total_minutes": None}})
        assert (s["default"], s["max_pieces"], s["piece_minutes"], s["total_minutes"]) == (False, 1, 3.0, 15.0)
        on, lanes = {"merge": {"default": True}}, {"lanes": {"default": 2}}
        assert merge.choose(None, None, {}) == (False, None)
        assert merge.choose(None, None, on) == (True, None)
        assert merge.choose(0, None, on) == (False, None)
        assert merge.choose(1, None, {}) == (True, None)
        assert merge.choose(1, None, lanes) == (True, None)                 # the flag beats lanes' config default
        assert merge.choose(None, 1, on) == (False, None)                   # --lanes beats merge's config default
        assert merge.choose(None, None, {**on, **lanes}) == (False, None)   # both from config: lanes, no error
        assert merge.choose(1, 1, {})[1] and not merge.choose(1, 1, {})[0]  # both on the command line: an error


class TestMergedRequest:
    def test_brief_and_settings(self):
        reqs = [req("a", check="pytest -q tests/test_a.py", review="off", risk="low", budget_usd=0.5),
                req("b", review="auto", risk="visible", budget_usd=0.25)]
        tasks = [{"id": "a", "paths": ["a.py", "tests/test_a.py"]}, {"id": "b"}]
        m = merge.merged_request(reqs, tasks)
        assert m.label == "merge:a+b" and m.check is None and m.escalate is False and m.allow_subagents is False
        assert (m.review, m.risk, m.route, m.budget_usd, m.finish_note) == ("auto", "visible", None, 0.75, merge.FINISH)
        b = m.brief
        assert b.index("Piece 1 of 2 - id: a (files: a.py, tests/test_a.py)") < b.index("Piece 2 of 2 - id: b")
        assert "Check for this piece: `pytest -q tests/test_a.py`" in b
        assert "never failed or blocked because one piece" in merge.FINISH

    def test_ids_labels_and_eval_prefix(self):
        assert merge.piece_ids([req(""), req(""), req("x"), req("x")]) == ["#1", "#2", "x", "x#4"]
        rs = [req("eval-a", route={"no_ab": True, "b": 3.0}), req("eval-b")]
        m = merge.merged_request(rs, [{}, {}])
        assert m.label == "eval-merge:eval-a+eval-b" and m.route == {"no_ab": True}

    def test_self_reported_lines_as_models_write_them(self):
        s = ("- [a] done: added it\n**[b]** FAILED: could not\n1. `[c]`: partial - half\n[d] — 完成\n"
             "[e]：失败 · [f] done\nnotes")
        assert merge.self_reported(s) == {"a": "done", "b": "failed", "c": "partial", "d": "done", "e": "failed",
                                          "f": "done"}
        assert merge.self_reported(None) == {}

    def test_piece_files_and_restrict(self):
        assert merge.restrict(["a.py", "pkg/x.py", "pkg2/y.py", "b.py", '"\\346\\226\\207.py"'],
                              ["pkg", "./b.py", "文.py"]) == ["pkg/x.py", "b.py", '"\\346\\226\\207.py"']
        rec = {"run_id": "r", "pieces": [{"id": "a", "paths": ["a.py"]}, {"id": "b", "paths": None}]}
        assert merge.piece_files(rec, "a") == ["a.py"]
        for bad, why in (("b", "declared no paths"), ("zz", "no piece")):
            try:
                merge.piece_files(rec, bad)
            except ValueError as e:
                assert why in str(e)
            else:
                raise AssertionError(bad)
        try:
            merge.piece_files({"run_id": "r"}, "a")
        except ValueError as e:
            assert "not a merged run" in str(e)


class TestBatchMerge(AdapterEnv):
    def setUp(self):
        super().setUp()
        self.env["FAKE_TOUCH"] = "1"

    def batch(self, tasks, *flags, code=None, env=None):
        f = self.work / "plan.json"
        f.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        r = self.ccx("batch", str(f), "--from", "claude", *flags, env=env)
        if code is not None:
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout), r

    def pieces(self, n, **extra):
        return [{"id": f"p{i}", "to": "codex", "tier": "T1", "mode": "write", "review": "off", "minutes": 2,
                 "brief": f"write piece {i}", "cwd": str(self.work), **extra} for i in range(n)]

    def execs(self):
        return [c for c in self.calls() if c["agent"] == "codex" and c["argv"][:1] == ["exec"]]

    def rows(self):
        from ccx import ledger
        from ccx.config import Paths
        return ledger.rows(Paths(self.hub))

    def test_off_by_default_is_as_before(self):
        out, _ = self.batch(self.pieces(3), code=0)
        self.assertNotIn("merged", out)
        self.assertEqual(len({r["run_id"] for r in out["results"]}), 3)
        self.assertEqual(len(self.execs()), 3)
        self.assertTrue(all("merged_run" not in r for r in out["results"]))
        self.assertTrue(all("merged pieces" not in c["prompt"] for c in self.execs()))
        out, _ = self.batch(self.pieces(2), "--no-merge", code=0, env={"CCX_HUB": str(self.hub)})
        self.assertNotIn("merged", out)

    def test_merge_runs_three_pieces_as_one_and_reports_each(self):
        self.env["FAKE_SUMMARY"] = "[p0] done: x\n[p1] done: y\n[p2] done: z"
        tasks = self.pieces(3, check=PASS)
        tasks[2].pop("check")                                                  # judged by its own line
        out, _ = self.batch(tasks, "--merge", code=0)
        res = out["results"]
        self.assertEqual([r["label"] for r in res], ["p0", "p1", "p2"])
        self.assertEqual(len({r["run_id"] for r in res}), 1)
        self.assertEqual(len(self.execs()), 1)                              # one session for the three
        self.assertTrue(all(r["ok"] and r["merged_run"] == res[0]["run_id"] for r in res), res)
        self.assertEqual(res[0]["merged_with"], ["p0", "p1", "p2"])
        self.assertTrue(res[0]["check"]["passed"] and "check" not in res[2])
        self.assertEqual(out["merged"][0]["pieces"], ["p0", "p1", "p2"])
        c = self.execs()[0]
        self.assertIn("Piece 1 of 3 - id: p0", c["prompt"])
        self.assertIn("never failed or blocked because one piece", c["prompt"])   # the merged Finish text
        self.assertNotIn("run the full set once at the end", c["prompt"])        # not the usual SELFCHECK
        self.assertIn("multi_agent", c["argv"])                              # no sub-agents of its own
        rec = self.rec(res[0]["run_id"])
        self.assertEqual([x["id"] for x in rec["pieces"]], ["p0", "p1", "p2"])
        self.assertEqual(rec["label"], "merge:p0+p1+p2")
        runs = [r for r in self.rows() if not r.get("type")]
        self.assertEqual(len(runs), 1)                                        # one ledger row
        ev = [r for r in self.rows() if r.get("type") == "merge"]
        self.assertEqual([x["state"] for x in ev[0]["pieces"]], ["done", "done", "done"])

    def test_failed_piece_gets_one_follow_up_then_its_own_run_never_the_whole_batch(self):
        tasks = self.pieces(3, check=PASS)
        tasks[1]["check"] = FAIL
        out, r = self.batch(tasks, "--merge")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        res = out["results"]
        self.assertTrue(res[0]["ok"] and res[2]["ok"])
        self.assertFalse(res[1]["ok"])
        self.assertTrue(res[1]["spun_off"])
        self.assertNotEqual(res[1]["run_id"], res[0]["run_id"])              # a run of its own
        ex = self.execs()
        self.assertEqual(ex[1]["argv"][:2], ["exec", "resume"])             # one follow-up in the same session
        failed_part = ex[1]["prompt"].split("These are not done:")[1].split("Fix only")[0]
        self.assertIn("[p1]", failed_part)
        self.assertNotIn("[p0]", failed_part)
        self.assertNotEqual(ex[2]["argv"][:2], ["exec", "resume"])          # then the piece on its own, fresh
        rec = self.rec(res[0]["run_id"])
        self.assertEqual(len(rec["attempts"]), 1)                            # the merged run did not escalate
        self.assertEqual(rec["merged"]["spun_off"], {"p1": res[1]["run_id"]})
        # the follow-up and the spun-off run point back at the merged run, in run.json and in the ledger
        rows = {x["run_id"]: x for x in self.rows() if not x.get("type")}
        fix = rec["merged"]["fix_run"]
        self.assertEqual(rows[fix]["merge_of"], res[0]["run_id"])
        self.assertEqual(rows[res[1]["run_id"]]["merge_of"], res[0]["run_id"])
        self.assertNotIn("merge_of", rows[res[0]["run_id"]])

    def test_overall_blocked_does_not_redo_pieces_whose_checks_passed(self):
        out, _ = self.batch(self.pieces(3, check=PASS), "--merge", code=0, env={"FAKE_STATUS": "blocked"})
        self.assertTrue(all(r["ok"] for r in out["results"]), out)
        self.assertEqual(len(self.execs()), 1)                               # no follow-up, nothing spun off

    def test_a_stop_starts_nothing_more(self):
        out, r = self.batch(self.pieces(2, check=FAIL), "--merge", env={"FAKE_STATUS": "auth"})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(self.execs()), 1)
        self.assertTrue(all(x["piece_state"] == "not_run" and "resume" in x["hint"] for x in out["results"]), out)

    def test_pieces_without_ids_stay_apart(self):
        tasks = self.pieces(2, check=FAIL)
        for t in tasks:
            t.pop("id")
        out, _ = self.batch(tasks, "--merge")
        res = out["results"]
        self.assertEqual([r["label"] for r in res], ["#1", "#2"])
        self.assertEqual(len({r["run_id"] for r in res}), 2)                # each its own spun-off run, none lost
        self.assertTrue(all(r.get("spun_off") for r in res))

    def test_a_piece_without_check_or_line_is_unconfirmed_not_redone(self):
        self.env["FAKE_SUMMARY"] = "[p0] done: x"
        out, r = self.batch(self.pieces(2), "--merge")
        self.assertEqual(r.returncode, 2)
        res = out["results"]
        self.assertTrue(res[0]["ok"])
        self.assertEqual((res[1]["ok"], res[1]["kind"]), (False, "unconfirmed"))
        self.assertNotIn("spun_off", res[1])
        self.assertEqual(len(self.execs()), 2)                               # asked once in the follow-up, no rerun

    def test_pieces_that_do_not_fit_run_alone_beside_the_merged_group(self):
        tasks = self.pieces(3, check=PASS) + [{"id": "big", "to": "codex", "tier": "T1", "mode": "write",
                                               "review": "off", "minutes": 30, "brief": "big", "cwd": str(self.work)}]
        out, _ = self.batch(tasks, "--merge", code=0)
        res = {r["label"] if "label" in r else "big": r for r in out["results"]}
        self.assertEqual(len(self.execs()), 2)
        self.assertNotIn("merged_run", res["big"])
        self.assertEqual(len(out["merged"]), 1)

    def test_merge_and_lanes_on_the_command_line_do_not_mix(self):
        out, r = self.batch(self.pieces(2), "--merge", "--lanes", "1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("lanes", json.dumps(out))

    def test_undo_piece_restores_only_that_pieces_paths(self):
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                     "-m", "init"]):
            subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True)
        (self.work / "a.txt").write_text("old a", encoding="utf-8")
        (self.work / "b.txt").write_text("old b", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.work, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], cwd=self.work,
                       check=True, capture_output=True)
        self.env.pop("FAKE_TOUCH")
        self.env["FAKE_WRITE"] = "a.txt=new a;b.txt=new b"
        self.env["FAKE_SUMMARY"] = "[p0] done: a\n[p1] done: b"
        tasks = self.pieces(2)
        tasks[0]["paths"], tasks[1]["paths"] = ["a.txt"], ["b.txt"]
        for t in tasks:
            t["worktree"] = False                          # in the project folder: undo works on it
        out, _ = self.batch(tasks, "--merge", code=0)
        run_id = out["results"][0]["run_id"]
        self.assertEqual(out["results"][0]["files_changed"], [])        # fake reports a.py: outside both pieces
        self.assertEqual(out["merged"][0]["unattributed"], ["a.py"])
        dry = json.loads(self.ccx("undo", run_id, "--piece", "p0").stdout)
        self.assertEqual((dry["restore"], dry["piece"]), (["a.txt"], "p0"))
        done = json.loads(self.ccx("undo", run_id, "--piece", "p0", "--apply").stdout)
        self.assertTrue(done["applied"])
        self.assertEqual((self.work / "a.txt").read_text(encoding="utf-8"), "old a")
        self.assertEqual((self.work / "b.txt").read_text(encoding="utf-8"), "new b")
        self.assertFalse((self.hub / "ccx" / "runs" / run_id / "undone.json").exists())   # the run itself stands
        r = self.ccx("undo", run_id, "--piece", "p0", "--wrong", "--apply")
        self.assertNotEqual(r.returncode, 0)                                  # a verdict is per run, not per piece
