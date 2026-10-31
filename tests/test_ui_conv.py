"""U2 / I1: `ccx ui` shows the agents' conversation (each project's board) and lets the person reply from the page:
the same two steps as a button (prepare, then a nonce), a length cap, written as the person via ui, never run.
Fake hub and boards only; no CLI is called."""
import http.client
import json
import re
import sys
import threading
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import board, ui  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_ui import put_run  # noqa: E402

STATIC = Path(ui.__file__).resolve().parent / "ui_static"
EVIL = ('x"; rm -rf / & del /q *.* | `whoami` $(id) %PATH% ^& >out.txt\n<script>alert(1)</script>\n'
        '<img src=x onerror=alert(2)>\r\n\t‮end')


def machine_six(root: Path, thread: str = "fn") -> None:
    """Six machine messages in a row in one thread: the board's cap (board.MAX_MACHINE)."""
    for i in range(board.MAX_MACHINE):
        frm, to = ("claude", "codex") if i % 2 == 0 else ("codex", "claude")
        board.post(root, frm, to, f"step {i + 1}", thread=thread)


def conv_of(data: dict) -> dict:
    assert len(data["conversations"]) == 1, data["conversations"]
    return data["conversations"][0]


def get(srv, path, token=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{srv.port}",
                                    "X-CCX-Token": srv.token if token is None else token})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}"), r.getheader("Content-Type")


def post(srv, path, body, origin="same", raw=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    h = {"Host": f"127.0.0.1:{srv.port}", "X-CCX-Token": srv.token, "Content-Type": "application/json"}
    if origin:
        h["Origin"] = f"http://127.0.0.1:{srv.port}" if origin == "same" else origin
    c.request("POST", path, body=raw if raw is not None else json.dumps(body).encode("utf-8"), headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


class TestConversationData(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()
        put_run(self.hub, "r1", self.work)                        # the project is on the page

    def test_six_machine_messages_make_a_stuck_todo(self):
        machine_six(self.work)
        with self.assertRaises(board.LoopLimit):                  # the board's own rule: the 7th is refused
            board.post(self.work, "claude", "codex", "7", thread="fn")
        c = conv_of(ui.collect(self.p))
        self.assertEqual((c["threads"], c["messages"]), (1, 6))
        self.assertEqual([(x["kind"], x["thread"], x["run"], x["id"]) for x in c["todos"]], [("stuck", "fn", 6, 6)])
        self.assertEqual(c["todos"][0]["text"], "step 6")
        board.human_turn(self.work, "codex:x1")                     # a person typed in a session in the thread
        self.assertEqual(conv_of(ui.collect(self.p))["todos"], [])

    def test_a_message_that_asks_the_person_makes_a_todo(self):
        board.post(self.work, "claude", "all", "plain note for the others", thread="a")
        board.post(self.work, "codex", "claude", "write to me@example.com about it", thread="a")    # an address
        e = board.post(self.work, "codex", "all", "@person: Postgres or SQLite?", thread="db")
        todos = conv_of(ui.collect(self.p))["todos"]
        self.assertEqual([(x["kind"], x["thread"], x["id"], x["from"]) for x in todos], [("asks", "db", e["id"], "codex")])
        board.post(self.work, "user", "all", "SQLite", thread="db", via="user")
        self.assertEqual(conv_of(ui.collect(self.p))["todos"], [])  # the person answered in that thread
        self.assertTrue(board.asks_person({"from": "claude", "to": "user", "text": "x"}))    # a record addressed so
        self.assertFalse(board.asks_person({"from": "user", "to": "all", "text": "@person me"}))
        for yes in ("@user, which one?", "hey @Human!", "please answer, @person."):
            self.assertTrue(board.asks_person({"from": "codex", "to": "all", "text": yes}), yes)
        for code in ("fix the @user.setter decorator", "put `@person` in the message", "see @user.com",
                     "ping @user-agent header", "pip install @human/pkg", "```\n@person\n```"):
            self.assertFalse(board.asks_person({"from": "codex", "to": "all", "text": code}), code)

    def test_a_board_only_in_the_catalog_shows_and_scratch_is_test(self):
        other = self.work.parent / "lab"
        (other / ".git").mkdir(parents=True)
        self.p.state.mkdir(parents=True, exist_ok=True)
        (self.p.state / "projects.json").write_text(json.dumps({"projects": [
            {"name": "the-lab", "path": str(other), "last_active": time.time()}]}), encoding="utf-8")
        board.post(other, "codex", "all", "@human look", thread="q")
        data = ui.collect(self.p)
        self.assertEqual([(c["name"], [x["kind"] for x in c["todos"]]) for c in data["conversations"]],
                         [("the-lab", ["asks"])])
        self.assertFalse(data["conversations"][0]["test"])          # the hub is in the temp folder: nothing apart

    def test_reading_writes_nothing_and_old_messages_leave_the_todo_list(self):
        machine_six(self.work)
        f = self.work / ".ccx" / "board.jsonl"
        before = sorted(x.name for x in (self.work / ".ccx").iterdir()), f.read_bytes()
        rd = ui.Reader(self.p)
        ui.collect(self.p, rd=rd)
        ui.conversation(rd, self.work, {}, ui._pid(self.work), "w")
        self.assertEqual((sorted(x.name for x in (self.work / ".ccx").iterdir()), f.read_bytes()), before)
        later = time.time() + 30 * 86400                          # a month later: the thread shows, no to-do
        self.assertEqual(conv_of(ui.collect(self.p, project=self.work, now=later))["todos"], [])

    def test_caps_on_what_goes_to_the_page(self):
        board.post(self.work, "claude", "codex", "a" * (ui.CONV_MSG_CHARS + 1000), thread="big")
        cv = ui.conversation(ui.Reader(self.p), self.work, {}, "p0", "w")
        m = cv["threads"][0]["messages"][0]
        self.assertEqual((len(m["text"]), m["cut"], m["chars"]), (ui.CONV_MSG_CHARS, True, ui.CONV_MSG_CHARS + 1000))
        with mock.patch.object(ui, "CONV_MSGS_MAX", 2):
            for i in range(4):
                board.post(self.work, "codex" if i % 2 else "claude", "all", f"m{i}", thread="t")
            board.human_turn(self.work, "claude")
            th = ui.conversation(ui.Reader(self.p), self.work, {}, "p0", "w")["threads"][0]
        self.assertEqual((th["thread"], th["n"], th["more"], [m["text"] for m in th["messages"]]),
                         ("t", 4, 2, ["m2", "m3"]))                 # newest thread first, its latest messages


class TestConversationServer(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()
        put_run(self.hub, "r1", self.work)
        machine_six(self.work)
        self.srv = ui.UI(self.p, idle_s=30)
        self.t = threading.Thread(target=self.srv.serve, daemon=True)
        self.t.start()
        code, data, _ = get(self.srv, "/api/data")
        self.assertEqual(code, 200)
        self.pid = conv_of(data)["id"]

    def tearDown(self):
        self.srv.stop()
        self.t.join(5)
        super().tearDown()

    def say(self, text, thread="fn", **kw):
        return post(self.srv, "/api/say/prepare", {"project": self.pid, "thread": thread, "text": text, **kw})

    def test_reply_needs_the_nonce_and_unsticks_the_thread(self):
        never = mock.patch.object(ui, "execute", side_effect=AssertionError("a reply is never run"))
        with never, mock.patch("subprocess.Popen", side_effect=AssertionError("no process")):
            code, prep = self.say("go on with the SQLite version")
            self.assertEqual(code, 200, prep)
            self.assertEqual((prep["to"], prep["reply_to"], prep["thread"], prep["cmd"]), ("codex", 6, "fn", "ccx reply 6"))
            self.assertEqual(len(board.entries(self.work)), 6)           # nothing written before the confirm
            self.assertEqual(post(self.srv, "/api/act/run", {"nonce": prep["nonce"]})[0], 409)   # not a button's
            code, out = post(self.srv, "/api/say/run", {"nonce": prep["nonce"]})
            self.assertEqual((code, out["ok"]), (200, True), out)
            self.assertEqual(post(self.srv, "/api/say/run", {"nonce": prep["nonce"]})[0], 409)   # once
            self.assertEqual(post(self.srv, "/api/say/run", {"nonce": "made-up"})[0], 409)
        e = board.entries(self.work)[-1]
        self.assertEqual((e["id"], e["from"], e["via"], e["to"], e["thread"], e["reply_to"], e["text"]),
                         (7, "user", "ui", "codex", "fn", 6, "go on with the SQLite version"))
        code, data, _ = get(self.srv, "/api/data")
        self.assertEqual(conv_of(data)["todos"], [])                   # the person spoke: no longer stuck
        board.post(self.work, "codex", "claude", "ok, continuing", thread="fn")    # the thread may go on
        log = (self.p.state / "ui-actions.jsonl").read_text(encoding="utf-8").splitlines()
        row = json.loads(log[-1])
        self.assertEqual((row["via"], row["say"]["id"], row["say"]["chars"]), ("ui", 7, 29))
        self.assertNotIn("SQLite", log[-1])                             # the text stays on the board only

    def test_hostile_text_is_one_message_verbatim_and_over_the_cap_is_refused(self):
        code, prep = self.say(EVIL)
        self.assertEqual(code, 200, prep)
        self.assertEqual(post(self.srv, "/api/say/run", {"nonce": prep["nonce"]})[0], 200)
        es = board.entries(self.work)
        self.assertEqual(len(es), 7)
        self.assertEqual(es[-1]["text"], EVIL)                         # verbatim, one message, newlines kept
        self.assertFalse((self.work / "out.txt").exists())
        code, cv, ctype = get(self.srv, f"/api/conv/{self.pid}")
        self.assertTrue(ctype.startswith("application/json"))
        self.assertEqual(cv["threads"][0]["messages"][-1]["text"], EVIL)   # data; the page escapes it
        at_cap = "z" * ui.SAY_MAX
        self.assertEqual(self.say(at_cap)[0], 200)
        code, out = self.say(at_cap + "z")
        self.assertEqual(code, 400)
        self.assertIn(str(ui.SAY_MAX), out["error"])
        for bad in ("", "  \n ", None, 5, ["x"]):
            self.assertEqual(self.say(bad)[0], 400, bad)
        self.assertEqual(self.say("hi", thread="nope")[0], 409)
        self.assertEqual(self.say("hi", reply_to=999)[0], 409)
        self.assertEqual(self.say("hi", reply_to="6")[0], 400)
        self.assertEqual(post(self.srv, "/api/say/prepare", {"project": "p0123456789", "thread": "fn", "text": "x"})[0],
                         409)
        self.assertEqual(post(self.srv, "/api/say/prepare", {"project": "../../etc", "thread": "fn", "text": "x"})[0],
                         400)
        w = {"project": self.pid, "thread": "fn", "text": "x"}
        self.assertEqual(post(self.srv, "/api/say/prepare", w, origin=None)[0], 403)
        self.assertEqual(post(self.srv, "/api/say/prepare", w, origin="http://evil.example")[0], 403)
        self.assertEqual(post(self.srv, "/api/say/prepare", w, raw=b"x" * (ui.SAY_BODY_MAX + 1))[0], 400)
        self.assertEqual(len(board.entries(self.work)), 7)               # nothing more was written

    def test_a_long_thread_name_is_shown_cut_but_answered_by_its_exact_key(self):
        long = "n" * (ui.CONV_FIELD + 30)
        machine_six(self.work, thread=long)
        code, data, _ = get(self.srv, "/api/data")
        todo = next(x for x in conv_of(data)["todos"] if x["key"] == long)
        self.assertNotEqual(todo["thread"], long)                       # the label is cut
        code, cv, _ = get(self.srv, f"/api/conv/{self.pid}")
        th = cv["threads"][0]
        self.assertEqual((th["key"], len(th["thread"]) < len(long)), (long, True))
        code, prep = self.say("go on", thread=th["key"])                # what the page sends
        self.assertEqual((code, prep["thread"]), (200, long), prep)
        self.assertEqual(post(self.srv, "/api/say/run", {"nonce": prep["nonce"]})[0], 200)
        self.assertEqual(board.entries(self.work)[-1]["thread"], long)
        code, data, _ = get(self.srv, "/api/data")
        self.assertFalse([x for x in conv_of(data)["todos"] if x["key"] == long])   # unstuck

    def test_a_new_message_shows_on_the_next_read_of_the_endpoint(self):
        # the server side of a poll only: the page's poll() / loadConv path was checked in a browser, not here
        code, cv, _ = get(self.srv, f"/api/conv/{self.pid}")
        self.assertEqual(code, 200)
        th = cv["threads"][0]
        self.assertEqual((th["thread"], th["n"], th["stuck"], th["run"], th["reply"]), ("fn", 6, True, 6,
                                                                                     {"id": 6, "to": "codex"}))
        self.assertEqual([m["who"] for m in th["messages"][:2]], ["claude", "codex"])
        board.post(self.work, "deepseek", "all", "@person a new thread", thread="new")   # as `ccx say` writes it
        code, cv, _ = get(self.srv, f"/api/conv/{self.pid}")
        self.assertEqual([t["thread"] for t in cv["threads"]], ["new", "fn"])        # newest first, no restart
        self.assertEqual(cv["threads"][0]["messages"][0]["asks"], True)
        code, data, _ = get(self.srv, "/api/data")
        self.assertEqual(sorted(x["kind"] for x in conv_of(data)["todos"]), ["asks", "stuck"])
        self.assertEqual(get(self.srv, "/api/conv/p0123456789")[0], 404)
        self.assertEqual(get(self.srv, "/api/conv/..%2F..%2Fetc")[0], 404)
        self.assertEqual(get(self.srv, f"/api/conv/{self.pid}", token="wrong")[0], 403)
        self.assertFalse((self.work / ".ccx" / "board.cursors.json").exists())       # reading moved no cursor


class TestConversationPage(Env):
    def test_the_conversation_code_inserts_no_raw_field_and_has_its_words(self):
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        sec = js[js.index("function convTodos"):js.index("function drawConv")]   # the page's conversation code
        raw = re.findall(r"\$\{\s*([A-Za-z_]\w*(?:\.\w+)+)\s*\}", sec)          # `${x.text}`: not through esc()/t()
        self.assertEqual([r for r in raw if not r.endswith(".length")], [])     # a count is a number
        for key in ("x.key", "z.key === th", "z.key === thread"):                  # links and replies use the exact name
            self.assertIn(key, js)
        for need in ("esc(m.text)", "esc(SAY.text)", "esc(x.text)", "esc(x.thread)", "/api/say/prepare",
                     "/api/say/run", "/api/conv/"):
            self.assertIn(need, js)
        strings = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))
        self.assertNotEqual(strings["en"]["conv_title"].lower(), "board")   # not the manager's board (K6)
