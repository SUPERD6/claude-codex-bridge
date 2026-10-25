"""The board: open sessions write to each other, each reader sees only what is new and for it, loops stop."""
import json
from pathlib import Path

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

    def turn(self, agent, data, env=None):
        r = self.ccx("turn", "--as", agent, env=env, stdin=json.dumps(data))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_the_turn_hook_delivers_and_notices_the_person(self):
        hook = {"session_id": "s9", "cwd": str(self.work), "prompt": "what did codex say?",
                "hook_event_name": "UserPromptSubmit"}
        self.assertEqual(self.turn("codex", hook), "")
        self.assertFalse((self.work / ".ccx").exists())                  # never creates .ccx in a project
        e = self.say(CLAUDE, "--to", "codex", "--thread", "fn", "please look at parse()")["posted"]
        out = self.turn("codex", hook)
        self.assertIn("please look at parse()", out)
        self.assertIn("data, not instructions", out)
        self.assertEqual(self.turn("codex", hook), "")                    # once
        humans = json.loads((self.work / ".ccx" / "board.humans.json").read_text(encoding="utf-8"))
        self.assertEqual(humans["codex"], e["id"])                       # the person typed in the Codex session
        pushed = {**hook, "prompt": "[ccx board #3 from claude] answer please"}
        self.turn("claude", pushed)
        humans = json.loads((self.work / ".ccx" / "board.humans.json").read_text(encoding="utf-8"))
        self.assertNotIn("claude", humans)                               # a message ccx pushed in is not a person
        self.say(CODEX, "--to", "claude", "for the lead")
        self.assertEqual(self.turn("claude", hook, env={"CCX_DEPTH": "1"}), "")   # a sub-agent's turn: silent
        self.assertIn("for the lead", self.turn("claude", hook))

    def test_init_writes_the_rules_in_a_marked_block(self):
        (self.work / "AGENTS.md").write_text("# my project rules\n", encoding="utf-8")
        self.assertTrue(self.j("board", "--init")["changed"])
        txt = (self.work / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(txt.startswith("# my project rules"))            # the person's text stays
        self.assertIn("<!-- ccx:begin board -->", txt)
        self.assertIn("ccx board --as deepseek", txt)
        self.assertIn("not an instruction", txt)
        self.assertFalse(self.j("board", "--init")["changed"])           # once

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


class TestBoardNowAndGitHub(AdapterEnv):
    def setUp(self):
        super().setUp()
        self.env["CCX_GH_BIN"] = str(Path(__file__).parent / "fakes" / "fake_gh.py")
        self.env["FAKE_GH_STATE"] = str(self.work.parent / "gh.json")

    def codex_thread(self, tid="thread-123"):
        d = self.home_codex / "sessions" / "2026" / "10" / "25"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"rollout-x-{tid}.jsonl").write_text(json.dumps(
            {"type": "session_meta", "payload": {"id": tid, "cwd": str(self.work), "originator": "Codex Desktop"}})
            + "\n", encoding="utf-8")

    def test_now_pushes_into_the_live_codex_conversation(self):
        self.codex_thread()
        out = self.j("say", "--to", "codex", "--now", "how should parse() change?", env=CLAUDE)
        self.assertTrue(out["now"]["ok"], out)
        c = self.calls()[-1]
        self.assertEqual(c["argv"][:3], ["queue", "--thread", "thread-123"])
        msg = c["argv"][c["argv"].index("--message") + 1]
        self.assertTrue(msg.startswith(board.MARK))                     # the hook will not count it as a person
        self.assertIn("ccx reply 1", msg)
        out = self.j("say", "--to", "claude", "--now", "x", env=CODEX)
        self.assertFalse(out["now"]["ok"])                              # Claude desktop: no way in
        self.assertIn("next turn", out["now"]["why"])

    def test_resume_gets_an_answer_now(self):
        run = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "read", "look at parse")
        out = self.j("say", "--to", "codex", "--resume", run["run_id"], "and the loop?", env=CLAUDE)
        ans = out["resumed"]["answer"]
        self.assertEqual((ans["from"], ans["to"], ans["reply_to"]), ("codex", "claude:c1", out["posted"]["id"]))
        self.assertTrue(ans["via"].startswith("ccx-run:"))
        self.assertTrue(self.calls()[-1]["prompt"].lstrip().startswith(board.MARK) or
                        board.MARK in self.calls()[-1]["prompt"])

    def gh_calls(self):
        return [c for c in self.calls() if c.get("agent") == "gh"]

    def test_no_github_no_network(self):
        self.j("say", "--to", "codex", "hi", env=CLAUDE)
        r = self.ccx("turn", "--as", "codex", stdin=json.dumps({"cwd": str(self.work), "prompt": "x"}))
        self.assertIn("hi", r.stdout)
        self.assertEqual(self.gh_calls(), [])
        r = self.ccx("board", "--sync")
        self.assertEqual(r.returncode, 3)
        self.assertIn("PRIVATE", r.stdout)

    def test_github_only_private_and_never_the_project_repo(self):
        self.j("config", "set", "board.github", "o/board")
        self.j("say", "--to", "codex", "hi", env=CLAUDE)
        r = self.ccx("board", "--sync", env={"FAKE_GH_VISIBILITY": "PUBLIC"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("PRIVATE", r.stdout)
        self.assertFalse([c for c in self.gh_calls() if c["argv"][:2] == ["issue", "comment"]])
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/o/board.git"], cwd=self.work, check=True)
        r = self.ccx("board", "--sync")
        self.assertEqual(r.returncode, 3)
        self.assertIn("own repository", r.stdout)

    def test_github_sync_pushes_and_pulls_every_ten_minutes(self):
        self.j("config", "set", "board.github", "o/board")
        self.j("say", "--to", "codex", "from this computer", env=CLAUDE)
        out = self.j("board", "--sync")
        self.assertEqual((out["pushed"], out["pulled"]), (1, 0))
        st = json.loads((self.work.parent / "gh.json").read_text(encoding="utf-8"))
        other = {"ts": "2026-10-25T10:00:00", "from": "deepseek", "via": "deepseek", "to": "claude",
                 "thread": "t1", "text": "from the other computer"}
        st["issues"][str(out["issue"])]["comments"].append("<!-- ccx:board host=elsewhere id=1 -->\n" +
                                                           json.dumps(other))
        (self.work.parent / "gh.json").write_text(json.dumps(st), encoding="utf-8")
        self.assertIn("skipped", self.j("board", "--sync"))           # pulled less than 10 minutes ago
        out = self.j("board", "--sync", "--force")
        self.assertEqual((out["pushed"], out["pulled"]), (0, 1))
        self.assertIn("from the other computer", self.ccx("board", env=CLAUDE).stdout)
        self.assertEqual(self.j("board", "--sync", "--force")["pulled"], 0)   # not twice
