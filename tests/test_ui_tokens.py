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


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


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
        now = time.time()
        jsonl(proj / "cl-sub-1.jsonl", [asst("main1", iso(now - 60), 100, 2000, 8000, 900, "cl-sub-1")])
        jsonl(proj / "cl-sub-1" / "subagents" / "agent-a1.jsonl", [
            asst("k1", iso(now - 59), 10, 500, 1500, 190, "cl-sub-1", True),
            asst("k1", iso(now - 59), 10, 500, 1500, 190, "cl-sub-1", True),     # same message, 2 lines
            asst("k2", iso(now - 58), 5, 0, 1000, 95, "cl-sub-1", True)])
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

    def kids_of(self, d: dict) -> dict:
        return {r["run_id"]: r for g in d["tasks"] for r in g["runs"]}

    def test_resumed_run_shows_only_child_growth(self):
        run(self.hub, self.p, "r1", self.work, task="t", codex_children={"k": {"input": 100, "cached": 0, "output": 10}},
            ts=time.time() - 300)
        run(self.hub, self.p, "r2", self.work, task="t", codex_children={"k": {"input": 150, "cached": 0, "output": 10}},
            ts=time.time() - 200, resumed_from="r1", resume_chain=1)
        runs = self.kids_of(self.data())
        self.assertEqual(runs["r1"]["children_tokens"]["total"], 110)
        self.assertEqual(runs["r2"]["children_tokens"]["total"], 50)

    def test_codex_growth_does_not_depend_on_group_or_filter(self):
        # (a) a resume with no task or label: it sits with its chain, and shows only its growth
        run(self.hub, self.p, "r1", self.work, codex_children={"k": {"input": 100, "cached": 0, "output": 10}},
            ts=time.time() - 10 * 86400, usage={"input_tokens": 200, "output_tokens": 20})
        run(self.hub, self.p, "r2", self.work, codex_children={"k": {"input": 150, "cached": 0, "output": 10}},
            ts=time.time() - 200, resumed_from="r1", resume_chain=1)
        d = self.data(period="all")
        self.assertEqual([[r["run_id"] for r in g["runs"]] for g in d["tasks"]], [["r2", "r1"]])
        self.assertEqual(self.kids_of(d)["r2"]["children_tokens"]["total"], 50)
        self.assertEqual(d["children_shown"]["total"], 160)
        # (b) the earlier run is outside the period: still only the growth
        d = self.data(period="7d")
        self.assertEqual(self.kids_of(d)["r2"]["children_tokens"]["total"], 50)
        self.assertEqual(d["children_shown"]["total"], 50)

    def test_auto_continue_with_a_new_label_does_not_count_children_again(self):
        run(self.hub, self.p, "c1", self.work, label="first job", ts=time.time() - 300,
            usage={"input_tokens": 9000, "output_tokens": 600},
            codex_children={"k": {"input": 5000, "cached": 0, "output": 500}})
        run(self.hub, self.p, "c2", self.work, label="second job", ts=time.time() - 200, resumed_from="c1",
            continued=True, continue_depth=1, usage={"input_tokens": 2300, "output_tokens": 50},
            codex_children={"k": {"input": 5000, "cached": 0, "output": 500}})
        d = self.data()
        runs = self.kids_of(d)
        self.assertEqual(runs["c1"]["children_tokens"]["total"], 5500)
        self.assertEqual(runs["c2"]["children"], [])             # carried over, nothing new
        self.assertIsNone(runs["c2"]["children_share"])
        self.assertEqual(d["children_shown"]["total"], 5500)

    def claude_session(self, sid: str, files: dict[str, list[dict]]):
        proj = self.home_claude / "projects" / "some-project"
        jsonl(proj / f"{sid}.jsonl", [asst("main-" + sid, iso(time.time() - 1000), 1, 0, 0, 1, sid)])
        for name, rows in files.items():
            jsonl(proj / sid / "subagents" / f"{name}.jsonl", rows)

    def test_claude_session_counted_once_per_run(self):
        # two attempts of one run on the same session (a retry resumes it): its helper file is listed once
        now = time.time()
        rec = put_run(self.hub, "rr", self.work, to="claude", ts=now - 300, attempts=[
            {"agent": "claude", "rung": "claude:sonnet:medium", "session_id": "s1", "seconds": 5.0, "usage": {"input_tokens": 3000,
             "output_tokens": 100}, "ae_usd": 0.01},
            {"agent": "claude", "rung": "claude:sonnet:medium", "session_id": "s1", "seconds": 5.0, "usage": {"input_tokens": 1000,
             "output_tokens": 100}, "ae_usd": 0.01}])
        ledger.append(self.p, rec)
        self.claude_session("s1", {"agent-a": [asst("h1", iso(now - 250), 100, 0, 900, 100, "s1", True)]})
        r = self.kids_of(self.data())["rr"]
        self.assertEqual([c["id"] for c in r["children"]], ["agent-a"])
        self.assertEqual(r["children_tokens"]["total"], 1100)
        self.assertEqual(r["children_share"], round(1100 / 4200, 3))

    def test_resumed_claude_run_takes_only_its_own_helper_turns(self):
        now = time.time()
        run(self.hub, self.p, "cl1", self.work, "claude", task="t", session="cl-s", ts=now - 300,
            usage={"input_tokens": 5000, "output_tokens": 200})
        run(self.hub, self.p, "cl2", self.work, "claude", task="t", session="cl-s", ts=now - 200, resumed_from="cl1",
            resume_chain=1, usage={"input_tokens": 600, "output_tokens": 10})
        self.claude_session("cl-s", {
            "agent-old": [asst("o1", iso(now - 280), 100, 0, 2000, 100, "cl-s", True)],     # during cl1
            "agent-new": [asst("n1", iso(now - 150), 10, 0, 300, 10, "cl-s", True)]})      # during cl2
        d = self.data()
        runs = self.kids_of(d)
        self.assertEqual([c["id"] for c in runs["cl1"]["children"]], ["agent-old"])
        self.assertEqual([c["id"] for c in runs["cl2"]["children"]], ["agent-new"])
        self.assertEqual(d["children_shown"]["total"], 2200 + 320)
        self.assertLessEqual(runs["cl2"]["children_share"], 1)
        # the earlier run's window ends where the later one starts, also when only the later one is in the period
        d = self.data(period="all")
        self.assertEqual(d["children_shown"]["total"], 2520)

    def test_share_is_not_capped(self):
        # counts that disagree (children above the run's own total) are shown as they are, and the page says so
        run(self.hub, self.p, "big", self.work, usage={"input_tokens": 100, "output_tokens": 0},
            codex_children={"k": {"input": 400, "cached": 0, "output": 0}})
        self.assertEqual(self.kids_of(self.data())["big"]["children_share"], 4.0)
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('t("tok_kids_over")', js)

    def test_period_project_and_caps(self):
        other = self.work.parent / "other"
        (other / ".git").mkdir(parents=True)
        # one fixed "now" for the records and the queries, and "new" inside today even just after midnight
        # (time.time() - 60 at 00:00:56 fell on yesterday and failed CI)
        now = time.time()
        today = tokenflow.since_of("today", now)
        now = max(now, today + 2)
        run(self.hub, self.p, "old", self.work, ts=now - 10 * 86400)
        run(self.hub, self.p, "mid", self.work, ts=now - 3 * 86400)
        run(self.hub, self.p, "new", other, ts=max(now - 60, today + 1))
        self.assertEqual(self.data(period="all")["totals"]["runs"], 3)
        self.assertEqual(self.data(period="7d", now=now)["totals"]["runs"], 2)
        self.assertEqual(self.data(period="today", now=now)["totals"]["runs"], 1)
        d = self.data(period="all")
        pid = next(x["id"] for x in d["projects"] if x["name"] == "other")
        self.assertEqual([t["runs"][0]["run_id"] for t in self.data(period="all", project=pid)["tasks"]], ["new"])
        with mock.patch.object(tokenflow, "TASKS_MAX", 2):
            d = self.data(period="all")
        self.assertEqual(len(d["tasks"]), 2)
        self.assertEqual(d["cut"], {"tasks": 1, "runs": 1, "tokens": 110, "usd": 0.01})   # what was cut, in size
        self.assertEqual(d["totals"]["runs"], 3)                         # the totals still count what was cut

    def test_by_agent_biggest_first(self):
        run(self.hub, self.p, "a", self.work, "codex", usage={"input_tokens": 10, "output_tokens": 0})
        run(self.hub, self.p, "b", self.work, "claude", usage={"input_tokens": 5000, "output_tokens": 0})
        self.assertEqual(list(self.data()["totals"]["by_agent"]), ["claude", "codex"])

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
        self.assertEqual(raw_fields(block), [])
        # the check itself finds a raw field in either form
        self.assertEqual(len(raw_fields('h += `<td>${x.why}</td>` + "<b>" + r.label;')), 2)


def raw_fields(block: str) -> list[str]:
    """Data fields put into HTML as they are: a template part that is only `obj.field`, or a string joined with
    `+ obj.field` (not counting a plain `const key = a.b + "|" + a.c;`, which is escaped where it is used).
    Everything from data goes through esc() / t() / tok() / pct() / money() / who() / ... instead (a `+x.n` right
    after `${`, `(` or `,` is a number, not text)."""
    out = [m.group(0) for m in re.finditer(r"\$\{\s*[A-Za-z_]+(?:\.[A-Za-z_]+)+\s*\}", block)]
    html = "\n".join(x for x in block.splitlines() if not re.match(r"\s*(?:const|let) \w+ = [^`<]*$", x))
    out += [m.group(0) for m in re.finditer(r"[\"'`)]\s*\+\s*[A-Za-z]{1,2}\.[A-Za-z_]+(?![\w(.])", html)]
    return out


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

    def test_project_all_overrides_the_ui_project(self):
        other = self.work.parent / "other"
        (other / ".git").mkdir(parents=True)
        run(self.hub, self.p, "elsewhere", other)
        pinned = ui.UI(self.p, project=self.work)
        mine = pinned.token_flow("all")                                   # no parameter: the ui's own project
        self.assertIsNotNone(mine["project"])
        self.assertNotIn("elsewhere", {r["run_id"] for g in mine["tasks"] for r in g["runs"]})
        every = pinned.token_flow("all", "all")                           # "All projects" really is all of them
        self.assertIsNone(every["project"])
        self.assertIn("elsewhere", {r["run_id"] for g in every["tasks"] for r in g["runs"]})
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('<option value="all"', js)


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

    # where each table is in the two docs, and the names of its rows there
    HEAD = {"hc1": ("### Hold-out set", "### 留出集"), "r5": ("### Round 5, dev set", "### 第 5 轮，开发集")}
    ROW = {"en": {"right": "Right", "usd": "Cost per success", "wall": "Wall time, median", "runs": "Runs counted",
                  "ext": "External repositories only (5 tasks)"},
           "zh": {"right": "做对", "usd": "每次成功的花费", "wall": "用时中位数", "runs": "算进来的轮次",
                  "ext": "只看外部仓库（5 个任务）"}}
    COL = {"self": 0, "builtin": 1, "builtin2": 1, "ccx": 2}

    @staticmethod
    def table(doc: str, heading: str) -> dict[str, list[str]]:
        """The first markdown table after `heading`: row name -> its cells (one per arm column)."""
        lines = doc.splitlines()
        i = next(n for n, x in enumerate(lines) if x.startswith(heading))
        while not lines[i].startswith("|"):
            i += 1
        out = {}
        while i < len(lines) and lines[i].startswith("|"):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            out[cells[0]] = cells[1:]
            i += 1
        return out

    @staticmethod
    def items(cell: str) -> list[str]:
        return [x.strip() for x in re.split(r",\s*|、", cell)]

    @staticmethod
    def money(x: str):
        x = x.replace("*", "").strip()
        return None if x in ("–", "-") else x.lstrip("$")

    def check_table(self, tb: dict, lang: str, doc: str):
        rows = self.table(doc, self.HEAD[tb["id"]][lang == "zh"])
        name = self.ROW[lang]
        pos: dict[int, int] = {}
        for r in tb["rows"]:                              # the k-th row of an arm column is the k-th list item there
            col = self.COL[r["arm"]]
            k = pos[col] = pos.get(col, -1) + 1
            right_cell = rows[name["right"]][col]
            if "/" in right_cell.split("(")[0].split("（")[0] and not re.search(r"\d+\s*[,、]", right_cell):
                self.assertEqual(re.match(r"\d+/\d+", right_cell).group(0), r["right"], (lang, tb["id"], r))
            else:                                        # "19, 17, 17 of 20" / "19、17、17（满分 20）"
                m = re.match(r"(.*?)\s*(?:of (\d+)|（满分 (\d+)）)$", right_cell)
                got = self.items(m.group(1))[k] + "/" + (m.group(2) or m.group(3))
                self.assertEqual(got, r["right"], (lang, tb["id"], r))
            self.assertEqual(self.money(self.items(rows[name["usd"]][col])[k]), r["usd_per_success"],
                             (lang, tb["id"], r))
            wall = re.sub(r"\s*(?:s|秒)$", "", rows[name["wall"]][col])
            got = self.items(wall)[k]
            self.assertEqual(None if got in ("–", "-") else got, r["wall_median_s"], (lang, tb["id"], r))
            if r.get("run"):
                got = re.match(r"r\d+[a-z]?", self.items(rows[name["runs"]][col])[k]).group(0)
                self.assertEqual(got, r["run"], (lang, tb["id"], r))
            if r.get("note"):
                self.assertIn(r["note"][lang], right_cell)
        for r in (tb.get("ext") or {}).get("rows") or []:
            right, usd = self.items(rows[name["ext"]][self.COL[r["arm"]]])
            self.assertEqual((right, self.money(usd)), (r["right"], r["usd_per_success"]), (lang, "ext", r))
        if tb.get("ext"):
            self.assertEqual(tb["ext"]["title"][lang], name["ext"])

    def test_table_cells_match(self):
        """Each cell, by arm and run, equals the cell in the docs' tables (EN and ZH), not just "somewhere"."""
        for tb in self.m["tables"]:
            self.check_table(tb, "en", self.en)
            self.check_table(tb, "zh", self.zh)
        self.assertIn(self.m["tests"]["en"].split(" (")[0], self.en)

    def test_a_swapped_or_wrong_cell_is_caught(self):
        """The drift that matters for a cost comparison: two arms swapped, or one row changed to numbers that do
        appear elsewhere in the doc."""
        import copy
        bad = []
        m = copy.deepcopy(self.m)
        hc1 = m["tables"][0]["rows"]
        hc1[0]["usd_per_success"], hc1[2]["usd_per_success"] = hc1[2]["usd_per_success"], hc1[0]["usd_per_success"]
        bad.append(m["tables"][0])
        m = copy.deepcopy(self.m)
        r = next(x for x in m["tables"][1]["rows"] if x["arm"] == "builtin2")
        r.update(right="18/20", usd_per_success="0.116", wall_median_s="267")
        bad.append(m["tables"][1])
        m = copy.deepcopy(self.m)
        m["tables"][0]["ext"]["rows"][1]["usd_per_success"] = "0.036"
        bad.append(m["tables"][0])
        for tb in bad:
            with self.assertRaises(AssertionError):
                self.check_table(tb, "en", self.en)

    def test_shipped_in_the_package(self):
        py = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(py, r'"ccx" = \[[^\]]*"data/\*\.json"')
        self.assertEqual(tokenflow.measured(), self.m)


if __name__ == "__main__":
    unittest.main()
