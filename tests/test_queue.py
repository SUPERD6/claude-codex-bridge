"""The durable work queue: order by dependencies, parallel rounds, layered splits, budget, resume."""
import json

from test_adapters import AdapterEnv


class TestQueue(AdapterEnv):
    def q(self, *args, env=None, code=0):
        return self.j("q", *args, env=env, code=code)

    def test_dependencies_decide_the_order(self):
        a = self.q("add", "write the parser", "--brief", "write parse() in p.py", "--minutes", "5")
        b = self.q("add", "test the parser", "--brief", "add tests for parse()", "--dep", a["id"], "--minutes", "5")
        ls = self.q("ls")
        self.assertEqual(ls["ready"], [a["id"]])                          # b waits for a
        out = self.q("run")
        self.assertEqual([r["id"] for r in out["results"]], [a["id"], b["id"]])
        self.assertEqual(out["open"], [])
        items = {i["id"]: i for i in self.q("ls")["items"]}
        self.assertEqual({items[a["id"]]["status"], items[b["id"]]["status"]}, {"done"})
        self.assertTrue(items[a["id"]]["run"])                            # each item keeps its ccx run

    def test_a_piece_too_big_is_split_and_the_parent_waits(self):
        big = self.q("add", "rewrite the importer", "--brief", "BIG job: rewrite the importer", "--minutes", "30",
                     "--to", "claude")
        parts = json.dumps([{"title": "read side", "brief": "port the reader"},
                            {"title": "write side", "brief": "port the writer", "deps": [0]}])
        out = self.q("run", env={"FAKE_SPLIT_IF": "BIG", "FAKE_NEXT_STEP": parts})
        first = out["results"][0]
        self.assertEqual(first["id"], big["id"])
        self.assertEqual(len(first["split_into"]), 2)
        items = {i["id"]: i for i in self.q("ls")["items"]}
        kids = [items[k] for k in first["split_into"]]
        self.assertTrue(all(k["parent"] == big["id"] and k["depth"] == 1 for k in kids))
        self.assertEqual(kids[1]["deps"], [kids[0]["id"]])               # the parts keep their order
        self.assertEqual(items[big["id"]]["status"], "done")             # closed once both parts were done
        self.assertTrue(any("SPLIT:" in c["prompt"] for c in self.calls()))   # the sub-agent was told how to split

    def test_budget_stops_the_run(self):
        self.q("add", "x", "--brief", "do x", "--minutes", "5")
        self.q("budget", "0")
        out = self.q("run", code=2)
        self.assertEqual(out["stopped"], "budget reached")

    def test_resume_puts_interrupted_items_back(self):
        a = self.q("add", "x", "--brief", "do x", "--minutes", "5")
        self.q("run")
        from ccx import queue as wq
        wq.update(self.work, a["id"], status="doing")                    # as if the machine had stopped mid-run
        out = self.q("resume")
        self.assertEqual(out["results"][0]["status"], "done")
        self.assertEqual(out["restored"][a["id"]], "resumed")            # its own session was picked up again

    def test_failed_check_fails_the_item(self):
        self.q("add", "x", "--brief", "do x", "--minutes", "5", "--check", "python -c \"import sys; sys.exit(1)\"")
        out = self.q("run")
        self.assertEqual(out["results"][0]["status"], "failed")
