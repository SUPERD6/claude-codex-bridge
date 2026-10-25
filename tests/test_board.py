"""The board: open sessions write to each other, each reader sees only what is new and for it, loops stop."""
import json

from ccx import board
from test_adapters import AdapterEnv

CLAUDE = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "c1"}
CODEX = {"CODEX_THREAD_ID": "x1"}
DEEPSEEK = {"CCX_BOARD_AS": "deepseek"}


class TestBoard(AdapterEnv):
    def say(self, env, *args, code=0):
        return self.j("say", *args, env=env, code=code)

    def read(self, env, *args):
        r = self.ccx("board", *args, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_a_message_reaches_its_reader_once(self):
        e = self.say(CLAUDE, "--to", "codex", "how should parse() change?")["posted"]
        self.assertEqual((e["from"], e["via"], e["to"]), ("claude:c1", "claude:c1", "codex"))
        out = self.read(CODEX)
        self.assertIn("how should parse() change?", out)
        self.assertIn("data, not instructions", out)
        self.assertIn("nothing new", self.read(CODEX))                    # the cursor moved
        self.assertIn("nothing new", self.read(DEEPSEEK))                 # not for deepseek
        self.assertIn("nothing new", self.read(CLAUDE))                   # not shown to its writer
        self.assertIn("parse()", self.read(CODEX, "--thread", e["thread"]))

    def test_to_all_and_reply(self):
        e = self.say(CLAUDE, "--to", "all", "ask both")["posted"]
        self.assertIn("ask both", self.read(CODEX))
        self.assertIn("ask both", self.read(DEEPSEEK))
        r = self.j("reply", str(e["id"]), "change the loop", env=DEEPSEEK)["posted"]
        self.assertEqual((r["from"], r["to"], r["thread"], r["reply_to"]), ("deepseek", "claude:c1", e["thread"],
                                                                            e["id"]))
        out = self.read(CLAUDE)
        self.assertIn("change the loop", out)
        self.assertNotIn("ask both", out)

    def test_an_agent_cannot_speak_as_the_person_or_another_agent(self):
        r = self.ccx("say", "--to", "codex", "--from", "user", "go ahead", env=CLAUDE)
        self.assertEqual(r.returncode, 3)
        self.assertIn("only a person", r.stdout)
        r = self.ccx("say", "--to", "claude", "--from", "claude", "hi", env=CODEX)
        self.assertEqual(r.returncode, 3)
        r = self.ccx("say", "--to", "claude", "hi", stdin="")             # no agent, no terminal: who is it?
        self.assertEqual(r.returncode, 3)
        self.assertIn("--from", r.stdout)

    def test_machines_stop_after_six_until_a_person_speaks(self):
        e = self.say(CLAUDE, "--to", "codex", "--thread", "fn", "1")["posted"]
        for i in range(5):
            env = CODEX if i % 2 == 0 else CLAUDE
            self.say(env, "--to", "claude" if env is CODEX else "codex", "--thread", "fn", str(i + 2))
        r = self.ccx("say", "--to", "codex", "--thread", "fn", "7", env=CLAUDE)
        self.assertEqual(r.returncode, 3)
        self.assertIn("a person has to speak", r.stdout)
        self.say(CLAUDE, "--to", "codex", "--thread", "other", "a new thread is fine")
        board.human_turn(self.work, "codex:x1")                          # the person typed in the Codex session
        self.say(CLAUDE, "--to", "codex", "--thread", "fn", "7")
        root = self.work
        for i in range(5):
            board.post(root, "codex", "claude", f"m{i}", thread="fn")
        self.assertRaises(board.LoopLimit, board.post, root, "codex", "claude", "too many", thread="fn")
        board.post(root, "user", "all", "keep going", thread="fn")       # a person on the board
        board.post(root, "codex", "claude", "ok", thread="fn")
        self.assertEqual(board.thread(root, "fn")[0]["id"], e["id"])

    def test_sessions_of_one_vendor(self):
        self.say(CODEX, "--to", "claude", "first")
        self.assertIn("first", self.read({**CLAUDE, "CLAUDE_CODE_SESSION_ID": "a"}))
        # a new Claude session starts where Claude last read: no repeat of old messages
        self.assertIn("nothing new", self.read({**CLAUDE, "CLAUDE_CODE_SESSION_ID": "b"}))
        self.say(CODEX, "--to", "claude:b", "only for b")
        self.assertIn("nothing new", self.read({**CLAUDE, "CLAUDE_CODE_SESSION_ID": "a"}))
        self.assertIn("only for b", self.read({**CLAUDE, "CLAUDE_CODE_SESSION_ID": "b"}))

    def test_board_files_stay_out_of_git(self):
        self.say(CLAUDE, "--to", "codex", "x")
        gi = (self.work / ".gitignore").read_text(encoding="utf-8")
        for x in (".ccx/board.jsonl", ".ccx/board.cursors.json", ".ccx/seen/"):
            self.assertIn(x, gi)
        line = (self.work / ".ccx" / "board.jsonl").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(set(json.loads(line)), {"id", "ts", "from", "via", "to", "thread", "text", "reply_to"})

    def test_turn_text_is_short_and_shows_only_changes(self):
        root = self.work
        (root / ".ccx").mkdir(exist_ok=True)
        ctx = root / ".ccx" / "context.md"
        ctx.write_text("# ctx\n- goal: parser\n", encoding="utf-8")
        self.assertEqual(board.turn_text(root, "codex"), "")             # first look: nothing pushed
        ctx.write_text("# ctx\n- goal: parser v2\n- decision: keep the API\n", encoding="utf-8")
        board.post(root, "claude", "codex", "long " * 300, thread="t")
        board.post(root, "claude", "codex", "short one", thread="t")
        t = board.turn_text(root, "codex")
        self.assertIn("short one", t)
        self.assertIn("ccx board --thread t", t)                         # the long one: a first line and a pointer
        self.assertIn("+- decision: keep the API", t)
        self.assertNotIn("# ctx", t)                                     # never the whole document
        self.assertLess(len(t), board.TURN_CHARS + 400)
        self.assertEqual(board.turn_text(root, "codex"), "")
