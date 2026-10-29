"""U6 `ccx demo` and U7 the switch-lead panel of `ccx ui`. The demo hub doubles as a headless smoke fixture: built
from ccx's own fake data in a temporary folder, served by the real server, every data endpoint read back. No agent
CLI is ever started (the one command run is `ccx handoff`, which only writes into the demo project)."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import demo, ui  # noqa: E402
from ccx.config import Paths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HAS_GIT = shutil.which("git") is not None


def get(srv, path):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{srv.port}", "X-CCX-Token": srv.token})
    r = c.getresponse()
    body = r.read().decode("utf-8")
    return r.status, dict(r.getheaders()), body


def post(srv, path, body):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=120)
    c.request("POST", path, body=json.dumps(body).encode("utf-8"),
              headers={"Host": f"127.0.0.1:{srv.port}", "X-CCX-Token": srv.token, "Content-Type": "application/json",
                       "Origin": f"http://127.0.0.1:{srv.port}"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


HOMES = ("CCX_HUB", "CLAUDE_CONFIG_DIR", "CODEX_HOME", "DSH_HOME")


def listing(env):
    return {k: sorted(str(f) for f in Path(env[k]).rglob("*")) for k in HOMES}


@pytest.fixture
def built(monkeypatch):
    """The demo in a new folder of the temporary folder (as `ccx demo` makes it: a short path, as Claude Code's own
    session folders need), built while this process still points at the test's own hub and tool homes (build()
    scopes its environment itself), then pointed at the demo. The own homes are kept to check nothing was written."""
    monkeypatch.setattr(ui, "_dsh_ready", lambda: False)        # whether this machine has dsh is no input
    own = {k: os.environ[k] for k in HOMES}
    before, env_before = listing(own), dict(os.environ)
    base = demo.new_base()
    try:
        p = demo.build(base)
        assert dict(os.environ) == env_before and listing(own) == before
        with mock.patch.dict(os.environ, demo.env(base)):
            yield base, p, own
    finally:
        assert demo.remove(base)
        assert not base.exists()


@pytest.fixture
def server(built):
    base, p, _ = built
    srv = ui.UI(p, idle_s=60)
    t = threading.Thread(target=srv.serve, daemon=True)
    t.start()
    yield srv, base, p
    srv.stop()
    t.join(5)


def walk(pieces):
    for pc in pieces:
        yield pc
        yield from walk(pc.get("children") or [])


def project(data, name):
    return next(pr for pr in data["projects"] if pr["name"] == name)


def test_demo_hub_is_marked_and_stays_in_its_folder(built):
    base, p, own = built
    assert demo.is_demo(p) and p.hub == base / "hub"
    assert list(Path(own["CCX_HUB"]).iterdir()) == []            # the hub the process had before: untouched
    assert sorted(x.name for x in base.iterdir()) == sorted(demo.DEMO_DIRS)
    assert "DEMO" in (p.hub / "README-DEMO.txt").read_text(encoding="utf-8")


def test_every_endpoint_returns_the_demo(server):
    srv, base, p = server
    stop = time.time() + 30
    while True:                                   # the month is read in the background: on a later poll
        code, headers, body = get(srv, "/api/data")
        d = json.loads(body)
        if d["month"] or time.time() > stop:
            break
        time.sleep(0.2)
    assert code == 200 and headers["X-Content-Type-Options"] == "nosniff"
    assert d["demo"] is True
    assert {pr["name"] for pr in d["projects"]} == {demo.SHOP, demo.DOCS}
    assert [o["name"] for o in d["others"]] == [demo.QUIET]
    assert len(d["running"]) == 1 and d["running"][0]["btn"]                 # the running strip, with its stop
    assert d["leads"] and d["leads"][0]["agent"] == "claude"                  # the fake lead conversation
    assert d["month"]["sub_usd"] > 0 and d["month"]["saving"] is not None     # a month of costs, and the estimate
    shop = project(d, demo.SHOP)
    whats = {pc["run_id"]: (pc["status"], (pc.get("act") or {}).get("what")) for t in shop["tasks"]
             for pc in walk(t["pieces"])}
    assert whats == {"demo-r-ok": ("done", None), "demo-r-review": ("decide", "a_review_failed"),
                     "demo-r-running": ("run", None), "demo-r-env": ("decide", "a_failed")}
    docs = project(d, demo.DOCS)
    q = next(t for t in docs["tasks"] if t["kind"] == "queue")
    assert [pc["status"] for pc in q["pieces"]] == ["done", "review", "queued"]   # one piece not merged yet
    assert "ccx q done q2 --ok 1" in q["pieces"][1]["act"]["buttons"][0]["cmd"]
    conv = next(c for c in d["conversations"] if c["name"] == demo.SHOP)
    assert sorted(x["kind"] for x in conv["todos"]) == ["asks", "stuck"]
    # each page's own data endpoint
    code, _, body = get(srv, f"/api/conv/{conv['id']}")
    threads = json.loads(body)["threads"]
    assert code == 200 and {x["key"] for x in threads} == {"discount-errors", "release-0.4"}
    stuck = next(x for x in threads if x["key"] == "discount-errors")
    assert stuck["stuck"] and any("<OrderForm>" in m["text"] for m in stuck["messages"])   # data, the page escapes
    for rid in whats:
        code, _, body = get(srv, f"/api/run/{rid}")
        assert code == 200 and json.loads(body)["run_id"] == rid
    code, _, body = get(srv, "/api/judge/demo-r-review")
    j = json.loads(body)
    assert code == 200 and j["says"]["verification"] and j["ran"]["cmd"] == "pytest -q"
    if HAS_GIT:                                                   # the snapshots need git; the card's two columns
        assert {c["path"] for c in j["changed"]} == {"orders.py", "discounts.py", "checkout.py"}
        assert j["mismatch"] == {"said_not_changed": ["tests/test_discounts.py"], "changed_not_said": ["checkout.py"]}
        assert "+def is_expired" in j["diff"]
    for name in ("index.html", "app.js", "app.css", "strings.json"):
        assert get(srv, "/" + name)[0] == 200


def test_snapshot_keeps_board_text_as_escaped_data(built, tmp_path):
    _, p, _ = built
    out = ui.export(p, tmp_path / "snap.html")
    html = out.read_text(encoding="utf-8")
    assert "\\u003cOrderForm\\u003e" in html and "<OrderForm>" not in html
    assert '"demo": true' in html


def test_same_records_every_time(tmp_path):
    now = time.time()

    def shape(base):
        with mock.patch.dict(os.environ, demo.env(base)):
            p = demo.build(base, now=now)
            d = ui.collect(p, now=now)
        rows = [{k: v for k, v in r.items() if k != "cwd"} for r in
                (json.loads(x) for x in p.ledger.read_text(encoding="utf-8").splitlines())]
        pieces = sorted((pc["title"], pc["status"]) for pr in d["projects"] for t in pr["tasks"] for pc in walk(t["pieces"]))
        return rows, pieces, d["month"]["sub_usd"]

    assert shape(tmp_path / "a") == shape(tmp_path / "b")


def test_rebuild_in_the_same_folder_starts_again(built):
    base, p, _ = built
    with mock.patch.dict(os.environ, demo.env(base)):
        demo.build(base)                                         # no doubled queue or board (it would hit the cap)
        d = ui.collect(Paths(base / "hub"))
    q = next(t for t in project(d, demo.DOCS)["tasks"] if t["kind"] == "queue")
    assert len(q["pieces"]) == 3


def test_not_a_demo_hub_is_refused(tmp_path):
    (tmp_path / "x" / "hub").mkdir(parents=True)
    with pytest.raises(ValueError):
        demo.build(tmp_path / "x")


def test_a_folder_with_other_files_is_refused_and_kept(tmp_path):
    mine = tmp_path / "x" / "projects" / "mine" / "keep.txt"
    mine.parent.mkdir(parents=True)
    mine.write_text("mine", encoding="utf-8")
    for _ in range(2):                                           # a first build and a "rebuild" both refuse
        with pytest.raises(ValueError):
            demo.build(tmp_path / "x")
    assert mine.read_text(encoding="utf-8") == "mine" and not (tmp_path / "x" / "hub").exists()
    assert not demo.remove(tmp_path / "x") and mine.exists()    # not a demo: remove() leaves it
    (tmp_path / "empty").mkdir()
    with mock.patch.dict(os.environ, demo.env(tmp_path / "empty")):
        assert demo.is_demo(demo.build(tmp_path / "empty"))      # an empty folder is fine


@pytest.mark.skipif(os.name != "nt", reason="the 260-character limit is Windows'")
def test_remove_deletes_a_demo_past_260_characters(tmp_path):
    base = tmp_path / ("d" * max(10, 140 - len(str(tmp_path))))
    with mock.patch.dict(os.environ, demo.env(base)):
        demo.build(base)
    assert demo.remove(base) and not base.exists()


def test_switch_lead_panel_and_timeline(server):
    srv, base, p = server
    d = json.loads(get(srv, "/api/data")[2])
    shop = project(d, demo.SHOP)
    sw = shop["lead_switch"]
    assert sw["current"] == "claude"
    assert [x["agent"] for x in sw["periods"]] == ["codex", "claude"]           # from the handoff record
    assert [b["label"] for b in sw["ctl"]] == ["b_cont_codex"]                   # dsh: patched as not installed
    assert "handoff --to codex --by claude --cwd" in sw["ctl"][0]["cmd"] and sw["ctl"][0]["run"]
    lead_task = next(t for t in shop["tasks"] if t["kind"] == "lead")
    assert any(h["k"] == "h_lead_at" and h["p"]["w"] == "claude" for h in lead_task["hist"])
    assert project(d, demo.DOCS)["lead_switch"]["current"] == "codex"            # the queue's lead


def test_hand_over_from_the_page(server):
    srv, base, p = server
    d = json.loads(get(srv, "/api/data")[2])
    shop = project(d, demo.SHOP)
    code, prep = post(srv, "/api/act/prepare", {"project": shop["id"], "task": "_lead", "piece": None, "btn": "c0"})
    assert code == 200 and prep["nonce"] and not prep["spends"]
    assert "--from-transcript claude --no-model --cwd" in prep["cmd"]          # the Claude conversation file is there
    assert prep["transcript"].endswith(f"{demo.LEAD_SESSION}.jsonl")
    code, out = post(srv, "/api/act/run", {"nonce": prep["nonce"]})
    assert code == 200 and out["ok"], out
    h = out["handoff"]
    f = Path(h["file"])
    assert f.is_file() and base in f.parents and h["to"] == "codex"
    assert h["paste"].startswith("Continue the work described in the handoff at .ccx/handoffs/")
    assert h["blank"] is False and h["shown_at_start"] is True
    assert "from=claude to=codex" in f.read_text(encoding="utf-8")
    assert post(srv, "/api/act/run", {"nonce": prep["nonce"]})[0] == 409          # once
    d = json.loads(get(srv, "/api/data")[2])
    sw = project(d, demo.SHOP)["lead_switch"]
    assert sw["current"] == "codex" and [b["label"] for b in sw["ctl"]] == ["b_cont_claude"]
    lead_task = next(t for t in project(d, demo.SHOP)["tasks"] if t["kind"] == "lead")
    assert any(x["k"] == "h_lead_switch" and (x["p"]["w"], x["p"]["w2"]) == ("claude", "codex") for x in lead_task["hist"])


def test_demo_shows_but_never_runs_a_command_that_starts_an_agent(server):
    srv, base, p = server
    d = json.loads(get(srv, "/api/data")[2])
    shop = project(d, demo.SHOP)
    t = next(t for t in shop["tasks"] if any(pc["run_id"] == "demo-r-env" for pc in walk(t["pieces"])))
    pc = next(pc for pc in walk(t["pieces"]) if pc["run_id"] == "demo-r-env")
    i = next(i for i, b in enumerate(pc["act"]["buttons"]) if b["label"] == "b_retry")
    code, prep = post(srv, "/api/act/prepare", {"project": shop["id"], "task": t["id"], "piece": pc["id"], "btn": f"a{i}"})
    assert code == 200 and prep["demo"] and prep["nonce"] is None and "ccx resume demo-r-env" in prep["cmd"]
    assert len(list(p.runs.iterdir())) == 6                                       # nothing was started


def test_demo_server_refuses_a_spending_job_even_if_prepared(server):
    srv, base, p = server
    srv.pending["forged"] = {"argv": ["ccx", "resume", "demo-r-env"], "spends": True, "until": time.time() + 60}
    code, out = post(srv, "/api/act/run", {"nonce": "forged"})
    assert code == 409 and "demo" in json.dumps(out)
    assert len(list(p.runs.iterdir())) == 6


def test_handoff_without_a_conversation_file_says_it_is_blank(server):
    """docs-site is led by Codex and the demo seeds no Codex session file: the handoff is the blank template, and the
    page is told so before (no transcript) and after (blank)."""
    srv, base, p = server
    d = json.loads(get(srv, "/api/data")[2])
    docs = project(d, demo.DOCS)
    i = next(i for i, b in enumerate(docs["lead_switch"]["ctl"]) if b["label"] == "b_cont_claude")
    code, prep = post(srv, "/api/act/prepare", {"project": docs["id"], "task": "_lead", "piece": None, "btn": f"c{i}"})
    assert code == 200 and "transcript" in prep and prep["transcript"] is None
    code, out = post(srv, "/api/act/run", {"nonce": prep["nonce"]})
    assert code == 200 and out["ok"], out
    assert out["handoff"]["blank"] is True


@pytest.mark.parametrize("to,shown", [("claude", True), ("codex", True), ("any", True), ("dsh", False),
                                      ("gemini", False)])
def test_paste_line_matches_what_the_tool_reads_at_start(to, shown):
    from ccx.commands.memory import paste_line
    line = paste_line(to, ".ccx/handoffs/x.md")
    assert ".ccx/handoffs/x.md" in line and ("shown at start-up" in line) is shown
    r = ui.handoff_result(["ccx", "handoff", "--to", to, "--by", "claude", "--cwd", "."],
                          json.dumps({"handoff": "x.md", "paste": line}))
    assert r["shown_at_start"] is shown and r["blank"] is False


def test_lead_periods_follow_a_task_led_after_the_last_handoff(tmp_path):
    rd = ui.Reader(Paths(tmp_path / "hub"))
    from ccx import project as proj
    proj.handoff(tmp_path, "claude", "codex", "done: x")
    t_handoff = ui.handoff_history(rd, tmp_path)[-1]["ts"]
    sw = ui.lead_switch(rd, tmp_path, [{"last": t_handoff + 3600, "lead": {"agent": "claude"}}])
    assert sw["current"] == "claude"
    assert [(x["agent"], x["until"] is None) for x in sw["periods"]] == [("claude", False), ("codex", False),
                                                                         ("claude", True)]


def test_lead_switch_without_a_known_lead_offers_nothing(tmp_path):
    rd = ui.Reader(Paths(tmp_path / "hub"))
    sw = ui.lead_switch(rd, tmp_path, [])
    assert sw == {"current": None, "ctl": [], "periods": [], "switches": []}


def test_deepseek_is_offered_when_dsh_is_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("CCX_DSH_BIN", str(tmp_path / "dsh"))
    rd = ui.Reader(Paths(tmp_path / "hub"))
    sw = ui.lead_switch(rd, tmp_path, [{"last": time.time(), "lead": {"agent": "claude"}}])
    assert [b["label"] for b in sw["ctl"]] == ["b_cont_codex", "b_cont_dsh"]
    assert sw["ctl"][1]["argv"][:4] == ["ccx", "handoff", "--to", "dsh"]


def test_cli_demo_export_writes_only_the_demo(tmp_path):
    own_hub = Path(os.environ["CCX_HUB"])
    out = tmp_path / "demo.html"
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), "demo", "--dir", str(tmp_path / "d"), "--export", str(out)],
                       capture_output=True, text=True, encoding="utf-8", timeout=180, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    assert '"demo": true' in out.read_text(encoding="utf-8")
    assert demo.is_demo(Paths(tmp_path / "d" / "hub"))
    assert list(own_hub.iterdir()) == []
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), "handoff", "-h"], capture_output=True, text=True,
                       encoding="utf-8", timeout=60, stdin=subprocess.DEVNULL)
    assert "--cwd" in r.stdout


def test_cli_demo_export_without_dir_leaves_no_folder(tmp_path):
    tmp = tmp_path / "t"
    tmp.mkdir()
    env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp)}
    out = tmp_path / "demo.html"
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), "demo", "--export", str(out)], capture_output=True,
                       text=True, encoding="utf-8", timeout=180, stdin=subprocess.DEVNULL, env=env)
    assert r.returncode == 0, r.stderr
    assert '"demo": true' in out.read_text(encoding="utf-8")
    assert not list(tmp.glob("ccx-demo-*"))                      # the export needs no folder afterwards
