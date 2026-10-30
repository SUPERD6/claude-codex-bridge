"""B1, `ccx ui` "Measured & where tokens go": the published numbers (ccx/data/measured.json, checked against
docs/measured.md), the person's own numbers, one ledger across Claude and Codex with each run's own child sessions,
and the lead conversations parsed with the functions behind `ccx lead --breakdown` / `--cache`. Fake ledger, run
records and session files only; no CLI is ever called."""
import json
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import leadcost, ledger, tokenflow, ui  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_ui import get, put_run  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
STATIC = Path(ui.__file__).resolve().parent / "ui_static"
EVIL = "<script>alert(1)</script><img src=x onerror=alert(2)>"


def run(hub: Path, p: Paths, run_id: str, cwd: Path, agent: str = "codex", usage=None, ae=0.01, ts=None,
        session=None, **kw) -> dict:
    """A run record (run.json) and its ledger row, as delegate.py writes them."""
    rung = {"codex": "codex:gpt-6-luna:low", "claude": "claude:sonnet:medium"}[agent]
    att = {"agent": agent, "rung": rung, "model": rung.split(":")[1], "seconds": 10.0, "session_id": session,
           "usage": usage or {"input_tokens": 100, "output_tokens": 10}, "ae_usd": ae}
    rec = put_run(hub, run_id, cwd, to=agent, attempts=[att], ts=ts or time.time() - 100, **kw)
    ledger.append(p, rec)
    return rec


def jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def asst(mid: str, ts: str, fresh: int, write: int, read: int, out: int, sid: str, side: bool = False) -> dict:
    return {"type": "assistant", "timestamp": ts, "sessionId": sid, "isSidechain": side,
            "message": {"id": mid, "model": "claude-sonnet-5-5",
                        "usage": {"input_tokens": fresh, "cache_creation_input_tokens": write,
                                  "cache_read_input_tokens": read, "output_tokens": out}}}


class Hub(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()
        self.flow = tokenflow.Flow(self.p)

    def data(self, **kw):
        return self.flow.tokens(ledger.rows(self.p), **kw)

    def fixture(self):
        # a Codex run that started 3 child sessions with spawn_agent (input includes cached, as Codex reports it)
        run(self.hub, self.p, "rA", self.work, "codex", task="t1", lead_session="lead-claude-1", session="cx-parent",
            usage={"input_tokens": 1000, "cached_input_tokens": 4000, "output_tokens": 500},
            codex_children={"kid1": {"input": 1200, "cached": 1000, "output": 100},
                            "kid2": {"input": 300, "cached": 0, "output": 50},
                            "kid3": {"input": 500, "cached": 200, "output": 50}})
        # its independent review: goes with the run it reviewed
        run(self.hub, self.p, "rC", self.work, "claude", label="review:rA", ae=0.002)
        # a Claude sub-run whose own sub-agent (Agent tool) wrote <session>/subagents/agent-a1.jsonl
        run(self.hub, self.p, "rB", self.work, "claude", label="docs pass", session="cl-sub-1", ae=0.05,
            usage={"input_tokens": 100, "cache_write_tokens": 2000, "cached_input_tokens": 8000,
                   "output_tokens": 900})
        proj = self.home_claude / "projects" / "some-project"
        jsonl(proj / "cl-sub-1.jsonl", [asst("main1", "2026-10-30T10:00:00Z", 100, 2000, 8000, 900, "cl-sub-1")])
        jsonl(proj / "cl-sub-1" / "subagents" / "agent-a1.jsonl", [
            asst("k1", "2026-10-30T10:00:01Z", 10, 500, 1500, 190, "cl-sub-1", True),
            asst("k1", "2026-10-30T10:00:01Z", 10, 500, 1500, 190, "cl-sub-1", True),     # same message, 2 lines
            asst("k2", "2026-10-30T10:00:02Z", 5, 0, 1000, 95, "cl-sub-1", True)])
        # an evaluation run: hidden unless asked
        run(self.hub, self.p, "rE", self.work, "codex", label="eval-x")


class TestTree(Hub):
    def test_tree_sums_and_shares(self):
        self.fixture()
        d = self.data(period="7d")
        self.assertEqual(d["totals"]["runs"], 3)                         # the evaluation run is left out
        self.assertEqual(set(d["totals"]["by_agent"]), {"codex", "claude"})
        tasks = {t["key"]: t for t in d["tasks"]}
        self.assertEqual(set(tasks), {"task:t1", "label:docs pass"})
        t1 = tasks["task:t1"]
        self.assertEqual((t1["title"], t1["name"]), ("Add a parser", "t1"))   # what was asked, not the task id
        self.assertEqual([r["run_id"] for r in t1["runs"]], ["rC", "rA"])  # newest first; the review sits here
        self.assertTrue(t1["runs"][0]["review"])
        ra = t1["runs"][1]
        self.assertEqual(ra["tokens"], {"fresh": 1000, "cached": 4000, "cache_write": 0, "output": 500,
                                        "total": 5500})
        kids = {c["id"]: c["tokens"] for c in ra["children"]}
        self.assertEqual(kids["kid1"], {"fresh": 200, "cached": 1000, "cache_write": 0, "output": 100, "total": 1300})
        self.assertEqual(kids["kid2"]["total"], 350)
        self.assertEqual(ra["children_tokens"]["total"], 2200)
        self.assertEqual(ra["children_share"], 0.4)
        self.assertEqual(t1["tokens"]["total"], 5500 + 110)
        rb = tasks["label:docs pass"]["runs"][0]
        self.assertEqual(rb["tokens"]["total"], 11000)
        self.assertEqual([c["id"] for c in rb["children"]], ["agent-a1"])
        self.assertEqual(rb["children"][0]["tokens"], {"fresh": 15, "cached": 2500, "cache_write": 500,
                                                       "output": 285, "total": 3300})
        self.assertEqual(rb["children_share"], 0.3)
        self.assertEqual(d["children_shown"]["total"], 2200 + 3300)
        self.assertEqual([(x["agent"], x["session"], x["runs"]) for x in d["leads"]], [("claude", "lead-claude-1", 1)])
        mine = d["mine"]
        self.assertEqual((mine["runs"], mine["ok"]), (2, 2))               # reviews are not counted as runs here
        self.assertEqual(mine["usd_per_ok"], 0.03)
        self.assertEqual(set(mine["by_agent"]), {"codex", "claude"})
        self.assertEqual(self.data(period="7d", tests=True)["totals"]["runs"], 4)

    def test_resumed_run_shows_only_child_growth(self):
        run(self.hub, self.p, "r1", self.work, task="t", codex_children={"k": {"input": 100, "cached": 0, "output": 10}},
            ts=time.time() - 300)
        run(self.hub, self.p, "r2", self.work, task="t", codex_children={"k": {"input": 150, "cached": 0, "output": 10}},
            ts=time.time() - 200)
        runs = {r["run_id"]: r for r in self.data()["tasks"][0]["runs"]}
        self.assertEqual(runs["r1"]["children_tokens"]["total"], 110)
        self.assertEqual(runs["r2"]["children_tokens"]["total"], 50)

    def test_period_project_and_caps(self):
        other = self.work.parent / "other"
        (other / ".git").mkdir(parents=True)
        run(self.hub, self.p, "old", self.work, ts=time.time() - 10 * 86400)
        run(self.hub, self.p, "mid", self.work, ts=time.time() - 3 * 86400)
        run(self.hub, self.p, "new", other, ts=time.time() - 60)
        self.assertEqual(self.data(period="all")["totals"]["runs"], 3)
        self.assertEqual(self.data(period="7d")["totals"]["runs"], 2)
        self.assertEqual(self.data(period="today")["totals"]["runs"], 1)
        d = self.data(period="all")
        pid = next(x["id"] for x in d["projects"] if x["name"] == "other")
        self.assertEqual([t["runs"][0]["run_id"] for t in self.data(period="all", project=pid)["tasks"]], ["new"])
        with mock.patch.object(tokenflow, "TASKS_MAX", 2):
            d = self.data(period="all")
        self.assertEqual(len(d["tasks"]), 2)
        self.assertEqual(d["cut"], {"tasks": 1, "runs": 1})
        self.assertEqual(d["totals"]["runs"], 3)                         # the totals still count what was cut

    def test_empty_hub(self):
        d = self.data()
        self.assertEqual((d["totals"]["runs"], d["tasks"], d["leads"], d["mine"]["runs"]), (0, [], [], 0))
        self.assertTrue(d["measured"]["tables"])                         # the published numbers show anyway
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for k in ("tok_empty", "tok_mine_none", "tok_leads_none"):     # each empty section says what to do
            self.assertIn(f't("{k}"', js)

    def test_malicious_label_is_capped_and_escaped(self):
        run(self.hub, self.p, "rX", self.work, label=EVIL + "x" * 5000)
        d = self.data()
        g = d["tasks"][0]
        self.assertLessEqual(len(g["title"]), tokenflow.LABEL_MAX)
        self.assertLessEqual(len(g["runs"][0]["label"]), tokenflow.LABEL_MAX)
        self.assertLessEqual(len(g["key"]), 200)
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        for expr in ("esc(g.title)", "esc(r.run_id)", "esc(c.id)", "esc(x.part)", "esc(a)", "esc(g.key)",
                     "esc(p.name)", "esc(r.status)"):
            self.assertIn(expr, js)
        block = js[js.index("B1: measured results"):js.index("function drawTokens")]
        for raw_field in ("${g.title}", "${r.run_id}", "${x.part}", "${r.label}", "${g.session}", "${c.id}"):
            self.assertNotIn(raw_field, block)


class TestLeadCost(Hub):
    def lead_file(self):
        rows = [{"type": "attachment", "attachment": {"type": "instructions",
                                                      "files": [{"path": "/p/CLAUDE.md", "content": "rule " * 3000}]}},
                {"type": "attachment", "attachment": {"type": "skill_listing", "content": "- a: b\n" * 300}},
                asst("m0", "2026-10-30T10:00:00Z", 5, 30_000, 0, 50, "lead-claude-1"),
                asst("m1", "2026-10-30T10:01:00Z", 5, 1_000, 30_000, 50, "lead-claude-1"),
                asst("m2", "2026-10-30T10:40:00Z", 5, 31_000, 0, 50, "lead-claude-1")]       # idle 39 min
        return jsonl(self.home_claude / "projects" / "some-project" / "lead-claude-1.jsonl", rows)

    def test_uses_the_breakdown_and_cache_functions(self):
        self.fixture()
        f = self.lead_file()
        want_b = leadcost.breakdown(self.p, "claude", f)
        want_c = leadcost.cache_breaks(self.p, "claude", f)
        with mock.patch.object(leadcost, "breakdown", wraps=leadcost.breakdown) as b, \
                mock.patch.object(leadcost, "cache_breaks", wraps=leadcost.cache_breaks) as c:
            out = self.flow.leadcost(ledger.rows(self.p), "claude", "lead-claude-1")
            again = self.flow.leadcost(ledger.rows(self.p), "claude", "lead-claude-1")
        self.assertEqual((b.call_count, c.call_count), (1, 1))          # cached by the file's mtime and size
        self.assertIs(out, again)
        self.assertEqual([(x["part"], x["tokens"]) for x in out["parts"]],
                         [(x["part"], x["tokens"]) for x in want_b["parts"]])
        self.assertEqual(out["advice"], want_b["advice"])
        self.assertEqual(out["first_turn_tokens"], 30_005)
        self.assertEqual(out["breaks_total"], len(want_c["breaks"]))
        self.assertTrue(any("idle" in w for w in out["breaks"][0]["why"]))
        self.assertEqual(out["file"], "lead-claude-1.jsonl")             # the name only, not the path
        self.assertNotIn(str(self.home_claude), json.dumps(out))

    def test_only_sessions_the_ledger_names(self):
        self.fixture()
        self.lead_file()
        rows = ledger.rows(self.p)
        with self.assertRaises(FileNotFoundError):
            self.flow.leadcost(rows, "claude", "someone-else")
        for agent, sid in (("claude", "../../etc"), ("gemini", "lead-claude-1"), ("claude", "")):
            with self.assertRaises(ValueError):
                self.flow.leadcost(rows, agent, sid)
        self.assertEqual(self.flow.leadcost(rows, "codex", "lead-claude-1")["found"], False)


class TestServer(Hub):
    def setUp(self):
        super().setUp()
        self.fixture()
        self.srv = ui.UI(self.p, idle_s=30)
        self.t = threading.Thread(target=self.srv.serve, daemon=True)
        self.t.start()

    def tearDown(self):
        self.srv.stop()
        self.t.join(5)
        super().tearDown()

    def test_endpoints_read_only_and_token_checked(self):
        self.assertEqual(get(self.srv, "/api/tokens")[0], 403)
        self.assertEqual(get(self.srv, "/api/leadcost?agent=claude&session=lead-claude-1")[0], 403)
        code, _, body = get(self.srv, "/api/tokens?period=all", token=self.srv.token)
        self.assertEqual(code, 200)
        d = json.loads(body)
        self.assertEqual(d["totals"]["runs"], 3)
        self.assertEqual(json.loads(get(self.srv, "/api/tokens?tests=1", token=self.srv.token)[2])["totals"]["runs"], 4)
        self.assertEqual(get(self.srv, "/api/tokens?project=../x", token=self.srv.token)[0], 404)
        self.assertEqual(get(self.srv, "/api/leadcost?agent=claude&session=nope", token=self.srv.token)[0], 404)
        code, _, body = get(self.srv, "/api/leadcost?agent=claude&session=lead-claude-1", token=self.srv.token)
        self.assertEqual((code, json.loads(body)["found"]), (200, False))   # named, but no file on this machine
        self.assertEqual(get(self.srv, "/api/tokens", token=self.srv.token, method="POST")[0], 404)   # no write path


class TestMeasuredData(unittest.TestCase):
    """The published numbers on the page come from ccx/data/measured.json; each must appear in docs/measured.md
    (English text and table numbers) and docs/measured.zh.md (Chinese text), so they cannot drift apart."""

    def setUp(self):
        self.m = json.loads((REPO / "ccx" / "data" / "measured.json").read_text(encoding="utf-8"))
        self.en = (REPO / "docs" / "measured.md").read_text(encoding="utf-8")
        self.zh = (REPO / "docs" / "measured.zh.md").read_text(encoding="utf-8")

    @staticmethod
    def numbers(text: str) -> list[str]:
        return re.findall(r"\d+(?:\.\d+)?", text)

    def has(self, doc: str, num: str) -> bool:
        return re.search(r"(?<![\d.])" + re.escape(num) + r"(?![\d]|\.\d)", doc) is not None

    def test_every_number_appears_in_the_docs(self):
        checked = 0

        def walk(v, doc):
            nonlocal checked
            if isinstance(v, dict):
                for k, x in v.items():
                    if k in ("note", "source"):
                        continue
                    walk(x, self.zh if k == "zh" else self.en if k == "en" else doc)
            elif isinstance(v, list):
                for x in v:
                    walk(x, doc)
            elif isinstance(v, str):
                for n in self.numbers(v):
                    checked += 1
                    self.assertTrue(self.has(doc, n), f"{n!r} (from {v!r}) is not in the measured doc")
        walk(self.m, self.en)
        self.assertGreater(checked, 40)

    def test_table_cells_match(self):
        for tb in self.m["tables"]:
            for r in tb["rows"]:
                if r.get("usd_per_success"):
                    self.assertIn("$" + r["usd_per_success"], self.en)
                    self.assertIn("$" + r["usd_per_success"], self.zh)
        hc1 = next(t for t in self.m["tables"] if t["id"] == "hc1")
        line = next(x for x in self.en.splitlines() if x.startswith("| Right |"))
        for r in hc1["rows"]:
            self.assertIn(r["right"], line)
        self.assertIn(self.m["tests"]["en"].split(" (")[0], self.en)

    def test_shipped_in_the_package(self):
        py = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(py, r'"ccx" = \[[^\]]*"data/\*\.json"')
        self.assertEqual(tokenflow.measured(), self.m)


if __name__ == "__main__":
    unittest.main()
