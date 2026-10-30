"""`ccx batch --merge` (ccx/merge.py, B3 item 5): small independent pieces become one run; each piece keeps its own
check, result line and `undo --piece`. Opt-in: without the flag `ccx batch` behaves as before. Fakes only."""
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


class TestGrouping:
    def test_same_key_without_shared_files_merges_up_to_the_limits(self):
        items = [(req(f"p{i}"), {"id": f"p{i}", "minutes": 2}) for i in range(7)]
        assert merge.groups(items, {}) == [[0, 1, 2, 3, 4], [5, 6]]           # max_pieces 5
        cfg = {"merge": {"max_pieces": 10, "total_minutes": 6}}
        assert merge.groups(items, cfg) == [[0, 1, 2], [3, 4, 5], [6]]        # 2 + 2 + 2 <= 6

    def test_what_keeps_pieces_apart(self):
        a, b = req("a"), req("b")
        assert merge.groups([(a, {"paths": ["x.py"]}), (b, {"paths": ["x.py", "y.py"]})], {}) == [[0], [1]]
        assert merge.groups([(a, {"paths": ["x.py"]}), (b, {"paths": ["z.py"]})], {}) == [[0, 1]]
        assert merge.groups([(a, {}), (b, {"paths": ["z.py"]})], {}) == [[0, 1]]        # undeclared: may merge
        assert merge.groups([(a, {}), (req("b", to="claude"), {})], {}) == [[0], [1]]
        assert merge.groups([(a, {}), (req("b", mode="read"), {})], {}) == [[0], [1]]
        assert merge.groups([(a, {}), (req("b", tier="T2"), {})], {}) == [[0], [1]]
        assert merge.groups([(a, {}), (req("b", cwd="elsewhere"), {})], {}) == [[0], [1]]
        assert merge.groups([(a, {}), (req("b", worktree=True), {})], {}) == [[0], [1]]
        assert merge.groups([(a, {"minutes": 12}), (b, {"minutes": 1})], {}) == [[0], [1]]   # too big a piece
        assert merge.groups([(a, {"minutes": "x"}), (b, {})], {}) == [[0, 1]]               # unparsable: default
        # a later piece that fits an earlier open group joins it; order inside stays the plan's
        assert merge.groups([(a, {}), (req("c", to="claude"), {}), (b, {})], {}) == [[0, 2], [1]]

    def test_settings_fall_back_on_bad_values(self):
        s = merge.settings({"merge": {"default": "yes", "max_pieces": 0, "piece_minutes": "3", "total_minutes": None}})
        assert (s["default"], s["max_pieces"], s["piece_minutes"], s["total_minutes"]) == (False, 1, 3.0, 15.0)
        assert merge.wanted(None, {}) is False
        assert merge.wanted(None, {"merge": {"default": True}}) is True
        assert merge.wanted(0, {"merge": {"default": True}}) is False
        assert merge.wanted(1, {}) is True


class TestMergedRequest:
    def test_brief_lists_pieces_in_order_with_their_checks_and_files(self):
        reqs = [req("a", check="pytest -q tests/test_a.py", review="off", risk="low"),
                req("b", review="auto", risk="visible")]
        tasks = [{"id": "a", "paths": ["a.py", "tests/test_a.py"]}, {"id": "b"}]
        m = merge.merged_request(reqs, tasks)
        assert m.label == "merge:a+b" and m.check is None and m.escalate is False and m.allow_subagents is False
        assert (m.review, m.risk, m.route) == ("auto", "visible", None)
        b = m.brief
        assert b.index("Piece 1 of 2 - id: a (files: a.py, tests/test_a.py)") < b.index("Piece 2 of 2 - id: b")
        assert "Check for this piece: `pytest -q tests/test_a.py`" in b
        assert b.index("do a") < b.index("do b")
        assert "[id] done|partial|failed" in b and "Do not start sub-agents" in b

    def test_self_reported_lines(self):
        s = "[a] done: added it\n[b] FAILED: could not\nnotes\n[c] partial: half"
        assert merge.self_reported(s) == {"a": "done", "b": "failed", "c": "partial"}
        assert merge.self_reported(None) == {}

    def test_piece_files_and_restrict(self):
        assert merge.restrict(["a.py", "pkg/x.py", "pkg2/y.py", "b.py"], ["pkg", "./b.py"]) == ["pkg/x.py", "b.py"]
        rec = {"run_id": "r", "pieces": [{"id": "a", "paths": ["a.py"]}, {"id": "b", "paths": None}]}
        assert merge.piece_files(rec, "a") == ["a.py"]
        for bad in ("b", "zz"):
            try:
                merge.piece_files(rec, bad)
            except ValueError as e:
                assert ("declared no paths" if bad == "b" else "no piece") in str(e)
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

    def batch(self, tasks, *flags, code=None):
        f = self.work / "plan.json"
        f.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
        r = self.ccx("batch", str(f), "--from", "claude", *flags)
        if code is not None:
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout), r

    def pieces(self, n, **extra):
        return [{"id": f"p{i}", "to": "codex", "tier": "T1", "mode": "write", "review": "off", "minutes": 2,
                 "brief": f"write piece {i}", "cwd": str(self.work), **extra} for i in range(n)]

    def execs(self):
        return [c for c in self.calls() if c["agent"] == "codex" and c["argv"][:1] == ["exec"]]

    def test_off_by_default_is_as_before(self):
        out, _ = self.batch(self.pieces(3), code=0)
        self.assertNotIn("merged", out)
        self.assertEqual(len({r["run_id"] for r in out["results"]}), 3)
        self.assertEqual(len(self.execs()), 3)
        self.assertTrue(all("merged_run" not in r for r in out["results"]))

    def test_merge_runs_three_pieces_as_one_and_reports_each(self):
        out, _ = self.batch(self.pieces(3, check=PASS), "--merge", code=0)
        res = out["results"]
        self.assertEqual([r["label"] for r in res], ["p0", "p1", "p2"])
        self.assertEqual(len({r["run_id"] for r in res}), 1)
        self.assertEqual(len(self.execs()), 1)                              # one session for the three
        self.assertTrue(all(r["ok"] and r["merged_run"] == res[0]["run_id"] for r in res), res)
        self.assertEqual(res[0]["merged_with"], ["p0", "p1", "p2"])
        self.assertTrue(all(r["check"]["passed"] for r in res))           # each piece's own check ran
        self.assertEqual(out["merged"][0]["pieces"], ["p0", "p1", "p2"])
        c = self.execs()[0]
        self.assertIn("Piece 1 of 3 - id: p0", c["prompt"])
        self.assertIn("multi_agent", c["argv"])                              # no sub-agents of its own
        rec = self.rec(res[0]["run_id"])
        self.assertEqual([x["id"] for x in rec["pieces"]], ["p0", "p1", "p2"])
        self.assertEqual(rec["label"], "merge:p0+p1+p2")
        from ccx import ledger
        from ccx.config import Paths
        rows = [r for r in ledger.rows(Paths(self.hub)) if not r.get("type")]
        self.assertEqual(len(rows), 1)                                        # one ledger row

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
        self.assertEqual(ex[0]["argv"][:1], ["exec"])
        self.assertEqual(ex[1]["argv"][:2], ["exec", "resume"])             # one follow-up in the same session
        self.assertIn("[p1]", ex[1]["prompt"])
        self.assertNotIn("[p0]", ex[1]["prompt"].split("These failed:")[1].split("Fix only")[0])
        self.assertEqual(ex[2]["argv"][:1], ["exec"])                        # then the piece on its own, fresh
        self.assertNotEqual(ex[2]["argv"][:2], ["exec", "resume"])
        rec = self.rec(res[0]["run_id"])
        self.assertEqual(len(rec["attempts"]), 1)                            # the merged run did not escalate
        self.assertEqual(rec["merged"]["spun_off"], {"p1": res[1]["run_id"]})
        self.assertEqual(out["merged"][0]["fix_run"], rec["merged"]["fix_run"])

    def test_pieces_that_do_not_fit_run_alone_beside_the_merged_group(self):
        tasks = self.pieces(3) + [{"id": "big", "to": "codex", "tier": "T1", "mode": "write", "review": "off",
                                   "minutes": 30, "brief": "big", "cwd": str(self.work)}]
        out, _ = self.batch(tasks, "--merge", code=0)
        res = {r["label"] if "label" in r else "big": r for r in out["results"]}
        self.assertEqual(len(self.execs()), 2)
        self.assertNotIn("merged_run", res["big"])
        self.assertEqual(len(out["merged"]), 1)

    def test_merge_and_lanes_do_not_mix(self):
        out, r = self.batch(self.pieces(2), "--merge", "--lanes", "1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("lanes", json.dumps(out))

    def test_undo_piece_restores_only_that_pieces_files(self):
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                     "-m", "init"]):
            subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True)
        (self.work / "a.txt").write_text("old a", encoding="utf-8")
        (self.work / "b.txt").write_text("old b", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.work, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "files"], cwd=self.work,
                       check=True, capture_output=True)
        self.env.pop("FAKE_TOUCH")
        self.env["FAKE_WRITE"] = "a.txt=new a;b.txt=new b"
        tasks = self.pieces(2)
        tasks[0]["paths"], tasks[1]["paths"] = ["a.txt"], ["b.txt"]
        for t in tasks:
            t["worktree"] = False                          # in the project folder: undo works on it
        out, _ = self.batch(tasks, "--merge", code=0)
        run_id = out["results"][0]["run_id"]
        dry = json.loads(self.ccx("undo", run_id, "--piece", "p0").stdout)
        self.assertEqual(dry["restore"], ["a.txt"])
        self.assertEqual(dry["piece"], "p0")
        done = json.loads(self.ccx("undo", run_id, "--piece", "p0", "--apply").stdout)
        self.assertTrue(done["applied"])
        self.assertEqual((self.work / "a.txt").read_text(encoding="utf-8"), "old a")
        self.assertEqual((self.work / "b.txt").read_text(encoding="utf-8"), "new b")
        r = self.ccx("undo", run_id, "--piece", "p0", "--wrong", "--apply")
        self.assertNotEqual(r.returncode, 0)                                  # a verdict is per run, not per piece
