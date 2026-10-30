"""B3 ruler (ccx/reqstats.py): requests a sub-agent attempt made and the input of each (its prefix), read from the
tools' own logs (shapes copied from real runs of 2026-10-29/30, numbers made small), recorded per attempt, summed in
the ledger row and shown by `ccx ui`'s token page. No CLI is called; nothing here changes a sub-agent's behaviour."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccx import ledger, reqstats, tokenflow  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_ui import put_run  # noqa: E402


def _asst(mid, fresh, write, read, side=False, model="claude-sonnet-5-5", parent=None):
    # the stream (stream-json stdout) marks an Agent-tool helper with parent_tool_use_id; a transcript, isSidechain
    return json.dumps({"type": "assistant", "isSidechain": side, "parent_tool_use_id": parent, "message": {
        "id": mid, "model": model, "usage": {"input_tokens": fresh, "cache_creation_input_tokens": write,
                                             "cache_read_input_tokens": read, "output_tokens": 5}}})


def test_claude_requests_are_messages_once_each_main_conversation_only():
    lines = [json.dumps({"type": "system", "subtype": "init", "session_id": "s"}),
             _asst("m1", 2, 15693, 0), _asst("m1", 2, 15693, 0),            # one reply, two content blocks
             _asst("m2", 2, 522, 15693),
             _asst("m3", 2, 177, 16215), _asst("m3", 2, 177, 16215),
             _asst("h1", 9, 9, 9, side=True),                                 # transcript-style helper
             _asst("h2", 10924, 0, 0, parent="toolu_01abc"),                  # stream-style helper (real run b8a0)
             _asst("x", 1, 1, 1, model="<synthetic>"),                        # Claude Code's own synthetic line
             "not json at all", json.dumps({"type": "result", "usage": {"input_tokens": 2}})]
    got = reqstats.claude_inputs(lines)
    assert got == [15695, 16217, 16394]
    assert reqstats.fields(got) == {"requests": 3, "prefix_tokens": 16217, "input_per_request": 16102,
                                    "request_inputs": got, "first_input": 15695}
    assert "first_input" not in reqstats.fields(got, fresh_session=False)    # a resumed session carries history
    assert reqstats.fields([]) == {}


def _rollout(home: Path, sid: str, rows: list[tuple[float, int]]) -> Path:
    d = home / "sessions" / "2026" / "10" / "30"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-2026-10-30T10-00-00-{sid}.jsonl"
    lines = [json.dumps({"type": "session_meta", "payload": {"id": sid}})]
    for t, n in rows:
        lines.append(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
                                 "type": "token_usage_record", "payload": {"thread_id": sid, "usage": {
                                     "input_tokens": n, "cached_input_tokens": n // 2, "output_tokens": 100}}}))
        lines.append(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
                                 "type": "event_msg", "payload": {"type": "token_count", "info": {}}}))
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def test_codex_requests_come_from_the_rollout_since_the_attempt_began(tmp_path):
    t0 = time.time() - 100
    _rollout(tmp_path, "cx-1", [(t0 - 50, 30000), (t0 + 1, 19245), (t0 + 20, 25000), (t0 + 40, 25600)])
    _rollout(tmp_path, "cx-other", [(t0 + 5, 99999)])                      # another session: not this attempt's
    assert reqstats.codex_inputs("cx-1", t0, home=tmp_path) == [19245, 25000, 25600]   # the earlier request is not
    assert reqstats.codex_inputs(None, t0, home=tmp_path) == []
    assert reqstats.codex_inputs("cx-missing", t0, home=tmp_path) == []
    assert reqstats.attempt_inputs("codex", "", "cx-1", t0, home=tmp_path) == [19245, 25000, 25600]
    assert reqstats.attempt_inputs("gemini", "anything", "g", t0) == []


def test_run_fields_sum_requests_and_weigh_the_mean_input_by_requests():
    atts = [{"requests": 3, "input_per_request": 20, "first_input": 10, "request_inputs": [10, 20, 30]},
            {"usage": {}},                                                  # an attempt that recorded nothing
            {"requests": 2, "request_inputs": [40, 50]}]                    # no mean stored: computed from the list
    assert reqstats.run_fields(atts) == {"requests": 5, "prefix_tokens": 30, "first_input": 10}
    assert reqstats.run_fields([{"usage": {}}]) == {}
    # malformed attempts are skipped, never an error: ledger.append must not fail a run
    bad = [{"requests": "x"}, {"requests": 2, "request_inputs": [None, 3]}, {"requests": 1, "input_per_request": 7}]
    assert reqstats.run_fields(bad) == {"requests": 1, "prefix_tokens": 7, "first_input": None}


class TestLedgerAndPage(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()

    def _run(self, run_id: str, agent: str, atts: list[dict], **kw):
        rec = put_run(self.hub, run_id, self.work, to=agent, attempts=atts, **kw)
        ledger.append(self.p, rec)
        return rec

    def test_ledger_row_and_token_page_carry_them_and_old_rows_show_null(self):
        base = {"rung": "codex:gpt-6-luna:low", "model": "gpt-6-luna", "effort": "low", "seconds": 5.0,
                "usage": {"input_tokens": 1000, "cached_input_tokens": 4000, "output_tokens": 50}, "ae_usd": 0.01}
        self._run("rNew", "codex", [{"agent": "codex", **base, "requests": 4, "prefix_tokens": 18400,
                                     "request_inputs": [12000, 18000, 18800, 26000]}], label="x")
        self._run("rTwo", "codex", [{"agent": "codex", **base, "requests": 2, "prefix_tokens": 20000,
                                     "request_inputs": [19000, 21000]}], label="y")
        self._run("rOld", "codex", [{"agent": "codex", **base}], label="z")               # before this ruler existed
        self._run("rCl", "claude", [{"agent": "claude", **base, "rung": "claude:sonnet:medium", "model": "sonnet",
                                     "requests": 5, "prefix_tokens": 14000, "request_inputs": [14000] * 5}])
        rows = {r["run_id"]: r for r in ledger.rows(self.p) if not r.get("type")}
        assert (rows["rNew"]["requests"], rows["rNew"]["prefix_tokens"]) == (4, 18700)     # mean of the four
        assert "requests" not in rows["rOld"] and "prefix_tokens" not in rows["rOld"]
        d = tokenflow.Flow(self.p).tokens(ledger.rows(self.p), period="all")
        items = {r["run_id"]: r for g in d["tasks"] for r in g["runs"]}
        assert (items["rNew"]["requests"], items["rNew"]["prefix_tokens"]) == (4, 18700)
        assert (items["rOld"]["requests"], items["rOld"]["prefix_tokens"]) == (None, None)
        cx = d["totals"]["by_agent"]["codex"]
        # over the codex runs that recorded it: (4 + 2) / 2 requests a run; the median of the runs' means
        assert (cx["measured_runs"], cx["requests_per_run"], cx["prefix_median"]) == (2, 3.0, 19350)
        assert "requests_per_run" not in d["totals"]["by_agent"].get("?", {})
        assert (d["totals"]["measured_runs"], d["totals"]["requests_per_run"]) == (3, 3.7)
        # the page's strings for both lines exist in both languages (app.js uses t("tok_req") / t("tok_req_avg"))
        s = json.loads((Path(tokenflow.__file__).resolve().parent / "ui_static" / "strings.json").read_text(
            encoding="utf-8"))
        for lg in ("zh", "en"):
            assert "{n}" in s[lg]["tok_req"] and "{f}" in s[lg]["tok_req_first"] and "{k}" in s[lg]["tok_req_each"]
            assert all(x in s[lg]["tok_req_avg"] for x in ("{n}", "{m}"))
            assert "{f}" in s[lg]["tok_req_first_med"] and "{k}" in s[lg]["tok_req_each_med"]
        assert "{n}" not in s["en"]["tok_req_1"]

    def test_nothing_measured_adds_no_keys(self):
        self._run("rOld", "codex", [{"agent": "codex", "rung": "codex:gpt-6-luna:low", "model": "gpt-6-luna",
                                     "effort": "low", "seconds": 1.0, "usage": {"input_tokens": 10}, "ae_usd": 0.0}])
        d = tokenflow.Flow(self.p).tokens(ledger.rows(self.p), period="all")
        assert "requests_per_run" not in d["totals"] and "requests_per_run" not in d["totals"]["by_agent"]["codex"]


class TestEndToEnd(Env):
    def test_a_codex_attempt_records_its_requests_from_the_rollout(self):
        # fake codex in "hang" mode writes a token_usage_record per request (as codex-cli 0.164), then times out
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        (self.hub / "ccx" / "tiers.toml").write_text("[defaults]\ntimeout_sec = 3\n", encoding="utf-8")
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low",
                     "--no-fallback", "x", env={"FAKE_STATUS": "hang", "FAKE_HANG_S": "60", "FAKE_RECORDS": "1"})
        out = json.loads(r.stdout)
        rec = json.loads((self.hub / "ccx" / "runs" / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        a = rec["attempts"][-1]
        assert a["requests"] >= 1 and a["prefix_tokens"] == 19245 and a["first_input"] == 19245
        row = next(x for x in ledger.rows(Paths(self.hub)) if x.get("run_id") == out["run_id"])
        assert (row["requests"], row["prefix_tokens"], row["first_input"]) == (a["requests"], 19245, 19245)

    def test_a_run_without_records_adds_nothing(self):
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--tier", "T1", "--mode", "read", "x")
        out = json.loads(r.stdout)
        rec = json.loads((self.hub / "ccx" / "runs" / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        assert "requests" not in rec["attempts"][-1]
        row = next(x for x in ledger.rows(Paths(self.hub)) if x.get("run_id") == out["run_id"])
        assert "requests" not in row
