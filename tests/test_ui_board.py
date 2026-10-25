"""K6: `ccx ui` as the manager's board — buttons that run ccx commands (prepare, confirm, run once), every project in
the catalog, this month's saving, and the optional slots for an autonomy level and an inbox (fake records only)."""
import http.client
import json
import sys
import threading
import time
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import ledger, ui  # noqa: E402
from ccx import queue as wq  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_ui import pieces, put_run  # noqa: E402


def task_of(data: dict, kind: str) -> tuple[dict, dict]:
    for pr in data["projects"]:
        for t in pr["tasks"]:
            if t["kind"] == kind:
                return pr, t
    raise AssertionError(f"no {kind} task")


class TestButtons(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()

    def test_only_ccx_commands_from_the_list_can_run(self):
        runs = [["ccx", "verify", "r1", "--ok", "1"], ["ccx", "stop", "r1"], ["ccx", "resume", "r1", "go on"],
                ["ccx", "run", "--mode", "write", "--cwd", ".", "do it"], ["ccx", "q", "done", "q1", "--ok", "1"],
                ["ccx", "q", "budget", "{usd}", "--cwd", "."], ["ccx", "q", "--cwd", ".", "resume"]]
        for argv in runs:
            self.assertIsNotNone(ui._op(argv), argv)
        self.assertEqual(ui._op(["ccx", "resume", "r1"]), "spend")
        self.assertEqual(ui._op(["ccx", "verify", "r1", "--ok", "1"]), "record")
        for argv in (["ccx", "show", "r1"], ["ccx", "config", "set", "x", "y"], ["ccx", "sync", "--apply"],
                     ["git", "diff"], ["codex", "login"], ["ccx", "q", "add", "x"], ["ccx", "q", "--cwd", ".", "add"],
                     ["ccx"], []):
            self.assertIsNone(ui._op(argv), argv)
        with self.assertRaises(ValueError):                       # the last guard, whoever calls it
            ui.execute(self.p, ["ccx", "sync", "--apply"], background=False)

    def test_form_values_are_checked_and_stay_one_argument(self):
        argv = ["ccx", "verify", "r1", "--ok", "0", "--reason", "{reason}", "--note", "{note}"]
        self.assertEqual(ui.fill(argv, {"reason": "wrong", "note": "off by one"})[-3:], ["wrong", "--note", "off by one"])
        self.assertEqual(ui.fill(argv, {"reason": "rm -rf /", "note": ""})[-3:], ["other", "--note", "other"])
        evil = ui.fill(argv, {"reason": "wrong", "note": "x\n; del *\r\x00" + "y" * 400})[-1]
        self.assertEqual(len(evil), 200)
        self.assertNotRegex(evil, r"[\x00-\x1f]")
        q = ["ccx", "q", "done", "q1", "--ok", "0", "--note", "{note}"]   # no --reason there: it goes into the note
        self.assertEqual(ui.fill(q, {"reason": "unfinished", "note": "half"})[-1], "unfinished: half")
        b = ["ccx", "q", "budget", "{usd}"]
        self.assertEqual(ui.fill(b, {"usd": "7.5"})[-1], "7.50")
        for bad in (None, "", "abc", "0", "-3", "1e9", "nan"):
            with self.assertRaises(ValueError):
                ui.fill(b, {"usd": bad})

    def test_buttons_on_the_page_say_whether_they_run(self):
        put_run(self.hub, "r-done", self.work)
        put_run(self.hub, "r-rf", self.work, kind="review_failed",
                review={"verdict": "issues", "issues": ["[must] x"], "by": "claude:haiku:low"})
        put_run(self.hub, "r-run", self.work, state="running", result=None, ok=False, ts=time.time() - 30, attempts=[])
        wq.add(self.work, "part", "do it")
        wq.update(self.work, "q1", status="failed", summary="broke")
        data = ui.collect(self.p)
        by = {pc["id"]: pc for pc in pieces(data)}
        rv = by["r-done"]["act"]["buttons"]
        self.assertEqual([(b["label"], b["run"]) for b in rv], [("b_ok", True), ("b_bad", True), ("b_see_change", False)])
        self.assertEqual(rv[0]["cmd"], "ccx verify r-done --ok 1")
        self.assertFalse(rv[0]["spends"])
        fix = by["r-rf"]["act"]["buttons"][1]
        self.assertEqual((fix["label"], fix["run"], fix["spends"]), ("b_one_more", True, True))
        self.assertEqual(by["r-run"]["act"], None)
        self.assertEqual([(b["label"], b["argv"]) for b in by["r-run"]["ctl"]], [("b_stop", ["ccx", "stop", "r-run"])])
        _, qt = task_of(data, "queue")
        self.assertEqual(qt["ctl"][0]["argv"], ["ccx", "q", "budget", "{usd}", "--cwd", str(self.work.resolve())])
        qr = by["q1"]["act"]["buttons"][1]
        self.assertEqual(qr["argv"], ["ccx", "q", "--cwd", str(self.work.resolve()), "resume"])   # --cwd before resume
        self.assertTrue(qr["spends"])


def post(srv, path, body, token=None, origin="same", ctype="application/json"):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    h = {"Host": f"127.0.0.1:{srv.port}", "X-CCX-Token": srv.token if token is None else token, "Content-Type": ctype}
    if origin:
        h["Origin"] = f"http://127.0.0.1:{srv.port}" if origin == "same" else origin
    c.request("POST", path, body=json.dumps(body), headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


class TestActServer(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()
        put_run(self.hub, "r1", self.work)
        put_run(self.hub, "r-rf", self.work, kind="review_failed",
                review={"verdict": "issues", "issues": ["[must] x"], "by": "claude:haiku:low"})
        self.srv = ui.UI(self.p, idle_s=30)
        self.t = threading.Thread(target=self.srv.serve, daemon=True)
        self.t.start()
        data = ui.collect(self.p)
        pr = data["projects"][0]
        self.where = {"project": pr["id"], "task": pr["tasks"][0]["id"]}
        self.task = {t["id"]: t for t in pr["tasks"]}

    def tearDown(self):
        self.srv.stop()
        self.t.join(5)
        super().tearDown()

    def want(self, piece, btn, **fill):
        task = next(t["id"] for t in self.task.values() if any(pc["id"] == piece for pc in ui._walk(t["pieces"])))
        return {"project": self.where["project"], "task": task, "piece": piece, "btn": btn, "fill": fill}

    def test_prepare_then_confirm_runs_once(self):
        calls = []
        with mock.patch.object(ui, "execute", lambda p, argv, background: calls.append((argv, background)) or
                               {"exit": 0, "ok": True, "out": "{}"}):
            code, prep = post(self.srv, "/api/act/prepare", self.want("r1", "a0"))
            self.assertEqual(code, 200, prep)
            self.assertEqual(prep["cmd"], "ccx verify r1 --ok 1")
            self.assertFalse(prep["spends"])
            self.assertEqual(calls, [])                                         # nothing runs before the confirm
            code, out = post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})
            self.assertEqual((code, out["ok"]), (200, True))
            self.assertEqual(calls, [(["ccx", "verify", "r1", "--ok", "1"], False)])
            self.assertEqual(post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})[0], 409)    # once
            self.assertEqual(post(self.srv, "/api/act/run", {"nonce": "made-up"})[0], 409)
            code, prep = post(self.srv, "/api/act/prepare", self.want("r-rf", "a1"))           # one more fix round
            self.assertTrue(prep["spends"])
            with mock.patch.object(ui.time, "time", return_value=time.time() + ui.ACT_TTL_S + 5):
                self.assertEqual(post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})[0], 409)   # too late
            code, prep = post(self.srv, "/api/act/prepare", self.want("r-rf", "a1"))
            post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})
            self.assertEqual(calls[-1][1], True)                                 # a sub-agent: in the background
            self.assertEqual(len(calls), 2)

    def test_cross_site_and_unknown_buttons_are_refused(self):
        with mock.patch.object(ui, "execute", side_effect=AssertionError("must not run")):
            w = self.want("r1", "a0")
            self.assertEqual(post(self.srv, "/api/act/prepare", w, origin=None)[0], 403)
            self.assertEqual(post(self.srv, "/api/act/prepare", w, origin="http://evil.example")[0], 403)
            self.assertEqual(post(self.srv, "/api/act/prepare", w, token="wrong")[0], 403)
            self.assertEqual(post(self.srv, "/api/act/prepare", w, ctype="text/plain")[0], 415)
            self.assertEqual(post(self.srv, "/api/act/run", {"nonce": "x"}, origin="http://evil.example")[0], 403)
            self.assertEqual(post(self.srv, "/api/act/prepare", self.want("r1", "a2"))[0], 409)   # 'see the change'
            self.assertEqual(post(self.srv, "/api/act/prepare", self.want("r1", "a9"))[0], 409)
            self.assertEqual(post(self.srv, "/api/act/prepare", self.want("r1", "x0"))[0], 400)
            self.assertEqual(post(self.srv, "/api/act/prepare", {**w, "piece": "nope"})[0], 409)
            self.assertEqual(post(self.srv, "/api/act/prepare", {**w, "cmd": "ccx sync --apply"})[1]["cmd"],
                             "ccx verify r1 --ok 1")                             # a command in the body is ignored

    def test_a_verdict_from_the_page_reaches_the_ledger(self):
        """End to end: the real ccx verify runs (this copy of ccx, no model) and records the verdict."""
        code, prep = post(self.srv, "/api/act/prepare", self.want("r1", "a1", reason="wrong", note="off by one"))
        self.assertEqual(prep["cmd"], 'ccx verify r1 --ok 0 --reason wrong --note "off by one"')
        code, out = post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})
        self.assertEqual((code, out["exit"]), (200, 0), out)
        rows = [r for r in ledger.rows(self.p) if r.get("type") == "verify"]
        self.assertEqual([(r["run_id"], r["ok"], r.get("reason")) for r in rows], [("r1", False, "wrong")])
        log = (self.p.state / "ui-actions.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(log[-1])["argv"][:2], ["verify", "r1"])
        data = json.loads(http_get(self.srv, "/api/data"))
        self.assertIsNone(next(pc for pc in pieces(data) if pc["id"] == "r1")["act"])        # no longer waits


def http_get(srv, path):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{srv.port}", "X-CCX-Token": srv.token})
    return c.getresponse().read().decode("utf-8")


class TestAcrossProjects(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        self.a, self.b, self.c = (self.work.parent / n for n in ("alpha", "beta", "gamma"))
        for d in (self.a, self.b, self.c):
            (d / ".git").mkdir(parents=True)
        (self.b / "AGENTS.md").write_text("# beta\nStage 2 needs written approval before it runs.\n", encoding="utf-8")
        cat = {"roots": [str(self.work.parent)], "scanned_at": time.time(), "projects": [
            {"name": "alpha-app", "path": str(self.a), "summary": "the first", "last_active": time.time() - 60,
             "rules": []},
            {"name": "beta-lab", "path": str(self.b), "summary": "the second", "last_active": time.time() - 3600,
             "rules": [str(self.b / "AGENTS.md")]},
            {"name": "gamma", "path": str(self.c), "summary": "quiet one", "last_active": time.time() - 86400,
             "rules": []}]}
        self.p.state.mkdir(parents=True, exist_ok=True)
        (self.p.state / "projects.json").write_text(json.dumps(cat), encoding="utf-8")

    def test_catalog_queue_shows_without_a_run_and_quiet_ones_are_listed(self):
        put_run(self.hub, "r1", self.a)
        wq.add(self.b, "Collect the data", "do it")                 # beta: a queue, no run of this hub
        data = ui.collect(self.p)
        names = {pr["name"]: pr for pr in data["projects"]}
        self.assertEqual(set(names), {"alpha-app", "beta-lab"})       # the catalog's names
        self.assertEqual(names["beta-lab"]["tasks"][0]["kind"], "queue")
        self.assertEqual([r["text"] for r in names["beta-lab"]["rules"]], ["Stage 2 needs written approval before it runs."])
        self.assertEqual([o["name"] for o in data["others"]], ["gamma"])
        self.assertEqual(data["others_total"], 1)
        only = ui.collect(self.p, project=self.a)
        self.assertEqual(([pr["name"] for pr in only["projects"]], only["others"]), (["alpha-app"], []))

    def test_optional_level_and_inbox_show_only_when_there(self):
        put_run(self.hub, "r1", self.a)
        with mock.patch.dict(sys.modules, {"ccx.autonomy": None, "ccx.intake": None}):    # not installed
            data = ui.collect(self.p)
        self.assertIsNone(data["projects"][0]["level"])
        self.assertIsNone(data["inbox"])
        auto = types.ModuleType("ccx.autonomy")
        seen = []
        auto.level_for = lambda e, p=None: seen.append((e["name"], p)) or {"level": "L1", "source": "config"}
        intake = types.ModuleType("ccx.intake")
        intake.pending = lambda p: 2                                    # K5: a count (a list would do too)
        with mock.patch.dict(sys.modules, {"ccx.autonomy": auto, "ccx.intake": intake}):
            data = ui.collect(self.p)
        self.assertEqual((data["projects"][0]["level"], data["inbox"]), ("L1", 2))
        self.assertEqual(seen, [("alpha-app", self.p)])                 # the catalog entry and this hub
        auto.level_for = lambda e, p=None: "<b>bold</b>"                # anything else is not shown
        with mock.patch.dict(sys.modules, {"ccx.autonomy": auto}):
            self.assertIsNone(ui.collect(self.p)["projects"][0]["level"])
        try:                                                            # K4's own module, once it is in
            from ccx import autonomy  # noqa: F401
        except ImportError:
            return
        self.assertIn(ui.collect(self.p)["projects"][0]["level"], ("L0", "L1", "L2"))


class TestMonth(Env):
    def test_this_months_saving_is_report_s_and_says_which_kind(self):
        p = Paths(self.hub)
        m = ui.collect(p)["month"]
        self.assertEqual((m["runs"], m["saving"], m["kind"]), (0, None, "model"))
        self.assertEqual(m["since"], ui.month_start(time.time()))
        t = time.localtime(ui.month_start(time.time()))
        self.assertEqual((t.tm_mday, t.tm_hour, t.tm_min), (1, 0, 0))
        fake = {"totals": {"sub_ae": 1.5, "runs": 12, "saving": 3.25, "saving_kind": "measured",
                           "saving_ci95": [1.0, 5.0], "saving_n": 10}}
        with mock.patch("ccx.report.summarize", return_value=fake):
            m = ui.month_view(ui.Reader(p))
        self.assertEqual((m["sub_usd"], m["saving"], m["kind"], m["ci95"], m["n"]), (1.5, 3.25, "measured", [1.0, 5.0], 10))

    def test_the_server_reads_it_in_the_background(self):
        p = Paths(self.hub)
        rd = ui.Reader(p)
        gate = threading.Event()

        def slow(*a, **k):
            gate.wait(5)
            return {"totals": {"sub_ae": 0, "runs": 0, "saving": None, "saving_kind": "model", "saving_ci95": None,
                               "saving_n": 0}}
        with mock.patch("ccx.report.summarize", side_effect=slow):
            self.assertIsNone(ui.month_view(rd, wait=False))           # the page doesn't wait for the ledger
            gate.set()
            for _ in range(50):
                if rd._timed.get("month"):
                    break
                time.sleep(0.05)
        self.assertEqual(ui.month_view(rd, wait=False)["runs"], 0)
