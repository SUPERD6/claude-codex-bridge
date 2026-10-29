"""PR-C, `ccx ui` judgement: the decision card's evidence from ccx's own snapshots (U1), a hidden tab that keeps the
server (U3), the "running now" strip (U4), and keyboard-reachable to-do chips with one live region (U5).
Real git in a temporary repo for the snapshots; fake records otherwise; no CLI is ever called."""
import http.client
import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import queue as wq  # noqa: E402
from ccx import ui, workspace  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_ui import get, pieces, put_run  # noqa: E402

STATIC = Path(ui.__file__).resolve().parent / "ui_static"
EVIL_NAME = "<img src=x onerror=alert(1)>.py"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class RepoEnv(Env):
    """A repo with a.py committed and old.txt untracked before the run; the run edits a.py and adds new.py."""

    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        git(self.work, "init", "-q")
        git(self.work, "config", "user.email", "t@example.com")
        git(self.work, "config", "user.name", "t")
        (self.work / "a.py").write_text("a = 1\n", encoding="utf-8")
        git(self.work, "add", "a.py")
        git(self.work, "commit", "-qm", "init")
        (self.work / "old.txt").write_text("there before\n", encoding="utf-8")

    def run_with_snapshots(self, run_id="r1", end=True, files=("a.py", "ghost.py"), **kw):
        put_run(self.hub, run_id, self.work, result={"status": "done", "summary": "changed a", "files_changed": list(files),
                                                     "verification": "ran pytest -k a: 3 passed"},
                check={"cmd": "pytest -q", "exit": 0, "passed": True, "tail": "3 passed in 0.1s"}, **kw)
        run_dir = self.hub / "ccx" / "runs" / run_id
        (run_dir / "undo.json").write_text(json.dumps(workspace.undo_snapshot(self.work)), encoding="utf-8")
        (self.work / "a.py").write_text("a = 2\n", encoding="utf-8")
        (self.work / "new.py").write_text("print('new')\n", encoding="utf-8")
        (self.work / "old.txt").write_text("edited too\n", encoding="utf-8")
        workspace.mark_run_end(run_dir, self.work)
        if end:
            workspace.write_end_tree(run_dir, self.work)
        return run_dir


class TestJudge(RepoEnv):
    def test_real_change_from_snapshots_with_new_files(self):
        self.run_with_snapshots()
        j = ui.judge(self.p, "r1")
        self.assertEqual(j["source"], "end")
        self.assertEqual({(c["path"], c["status"]) for c in j["changed"]}, {("a.py", "M"), ("new.py", "A")})
        self.assertIn("+print('new')", j["diff"])                     # the new untracked file's content is there
        self.assertIn("+a = 2", j["diff"])
        self.assertNotIn("old.txt", j["diff"])                         # untracked before the run: left out, said so
        self.assertEqual(j["untracked_before"], ["old.txt"])
        self.assertEqual(j["mismatch"], {"said_not_changed": ["ghost.py"], "changed_not_said": ["new.py"]})
        self.assertFalse(j["truncated"])
        self.assertEqual(j["says"]["verification"], "ran pytest -k a: 3 passed")
        self.assertEqual((j["ran"]["cmd"], j["ran"]["exit"], j["ran"]["tail"]), ("pytest -q", 0, "3 passed in 0.1s"))

    def test_without_end_json_new_files_by_name(self):
        self.run_with_snapshots(end=False, files=("a.py", "new.py"))
        j = ui.judge(self.p, "r1")
        self.assertEqual(j["source"], "after")
        self.assertEqual({(c["path"], c["status"]) for c in j["changed"]}, {("a.py", "M"), ("new.py", "?")})
        self.assertEqual(j["note"], "j_untracked_names")
        self.assertIsNone(j["mismatch"])                                # names agree: no red box
        self.assertNotIn("new.py", j["diff"])

    def test_matching_names_from_a_subfolder_and_backslashes(self):
        sub = self.work / "pkg"
        sub.mkdir()
        (sub / "m.py").write_text("x = 1\n", encoding="utf-8")
        git(self.work, "add", "pkg/m.py")
        git(self.work, "commit", "-qm", "pkg")
        put_run(self.hub, "r2", sub, result={"status": "done", "files_changed": [".\\m.py"]})
        run_dir = self.hub / "ccx" / "runs" / "r2"
        (run_dir / "undo.json").write_text(json.dumps(workspace.undo_snapshot(sub)), encoding="utf-8")
        (sub / "m.py").write_text("x = 2\n", encoding="utf-8")
        workspace.mark_run_end(run_dir, sub)
        j = ui.judge(self.p, "r2")
        self.assertEqual([c["path"] for c in j["changed"]], ["pkg/m.py"])
        self.assertIsNone(j["mismatch"])

    def test_hostile_names_are_data_and_never_opened(self):
        outside = self.work.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        self.run_with_snapshots(files=(EVIL_NAME, "../outside.txt", "a.py", "new.py"))
        opened = []
        real_open = Path.read_text

        def spy(self_, *a, **k):
            opened.append(str(self_))
            return real_open(self_, *a, **k)
        with mock.patch.object(Path, "read_text", spy):
            j = ui.judge(self.p, "r1")
        run_dir = (self.hub / "ccx" / "runs" / "r1").resolve()
        self.assertTrue(opened and all(Path(f).resolve().parent == run_dir for f in opened), opened)
        self.assertEqual(j["mismatch"]["said_not_changed"], [EVIL_NAME, "../outside.txt"])   # plain strings
        self.assertNotIn("secret", json.dumps(j))

    def test_old_runs_running_runs_and_read_runs_fall_back_with_a_note(self):
        put_run(self.hub, "old", self.work)
        put_run(self.hub, "live", self.work, state="running", result=None)
        put_run(self.hub, "ro", self.work, mode="read")
        for rid, note in (("old", "j_no_snapshot"), ("live", "j_running"), ("ro", "j_read_only")):
            j = ui.judge(self.p, rid)
            self.assertEqual((j["note"], j["diff"], j["changed"]), (note, None, None), rid)
        self.assertEqual(ui.judge(self.p, "old")["says"]["files"], ["a.py"])       # today's view: its own list
        with self.assertRaises(ValueError):
            ui.judge(self.p, "../x")
        with self.assertRaises(FileNotFoundError):
            ui.judge(self.p, "nope")

    def test_bad_object_ids_in_a_record_never_reach_git(self):
        run_dir = self.run_with_snapshots()
        snap = json.loads((run_dir / "undo.json").read_text(encoding="utf-8"))
        snap["base"] = "--output=x"
        (run_dir / "undo.json").write_text(json.dumps(snap), encoding="utf-8")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("git must not run")):
            self.assertEqual(ui.judge(self.p, "r1")["note"], "j_repo_gone")
        self.assertFalse((self.work / "x").exists())

    def test_diff_is_capped_and_says_truncated(self):
        self.run_with_snapshots()
        with mock.patch.object(ui, "JUDGE_DIFF_MAX", 40):
            j = ui.judge(self.p, "r1")
        self.assertTrue(j["truncated"])
        self.assertLessEqual(len(j["diff"].encode("utf-8")), 40)
        self.assertEqual(len(j["changed"]), 2)                          # the file list is still whole

    def test_read_only_git_diff_only_and_nothing_changes(self):
        run_dir = self.run_with_snapshots()
        index = self.work / ".git" / "index"
        before = (git(self.work, "rev-parse", "HEAD"), index.read_bytes(), git(self.work, "status", "--porcelain"),
                  {f.name: f.read_bytes() for f in run_dir.iterdir()})
        calls = []
        real = subprocess.Popen

        def spy(argv, *a, **k):
            calls.append(list(argv))
            return real(argv, *a, **k)
        with mock.patch("subprocess.Popen", spy):
            ui.judge(self.p, "r1")
        self.assertTrue(calls)
        for argv in calls:
            self.assertEqual(argv[:2] + argv[3:7], ["git", "-C", "-c", "core.quotepath=off", "--no-pager", "diff"], argv)
            self.assertFalse(any(x.startswith("--output") for x in argv))
        after = (git(self.work, "rev-parse", "HEAD"), index.read_bytes(), git(self.work, "status", "--porcelain"),
                 {f.name: f.read_bytes() for f in run_dir.iterdir()})
        self.assertEqual(before, after)

    def test_piece_carries_verification_and_check_output(self):
        self.run_with_snapshots()
        pc = pieces(ui.collect(self.p, quota_wait=False))[0]
        self.assertEqual(pc["verification"], "ran pytest -k a: 3 passed")
        self.assertEqual(pc["check"], {"cmd": "pytest -q", "passed": True, "exit": 0, "tail": "3 passed in 0.1s",
                                       "broken": None, "weak": None, "unchanged_tree": False, "reason": None})
        long = "x" * 5000
        put_run(self.hub, "r9", self.work, check={"cmd": "c", "exit": 1, "passed": False, "tail": long})
        by = {p["run_id"]: p for p in pieces(ui.collect(self.p, quota_wait=False))}
        self.assertEqual(len(by["r9"]["check"]["tail"]), ui.TAIL_MAX)


class TestJudgeEndpoint(RepoEnv):
    def setUp(self):
        super().setUp()
        self.run_with_snapshots(files=(EVIL_NAME,))
        self.srv = ui.UI(self.p, idle_s=30)
        self.t = threading.Thread(target=self.srv.serve, daemon=True)
        self.t.start()

    def tearDown(self):
        self.srv.stop()
        self.t.join(5)
        super().tearDown()

    def test_endpoint_token_read_only_and_paths(self):
        self.assertEqual(get(self.srv, "/api/judge/r1")[0], 403)                     # no token
        code, _, body = get(self.srv, "/api/judge/r1", token=self.srv.token)
        self.assertEqual(code, 200)
        j = json.loads(body)
        self.assertIn(EVIL_NAME, j["mismatch"]["said_not_changed"])                 # JSON data; the page escapes it
        self.assertEqual(get(self.srv, "/api/judge/..%2f..%2fx", token=self.srv.token)[0], 404)
        self.assertEqual(get(self.srv, "/api/judge/nope", token=self.srv.token)[0], 404)
        self.assertEqual(get(self.srv, "/api/judge/r1", token=self.srv.token, method="POST")[0], 404)   # no write path
        with mock.patch.object(ui, "judge", side_effect=AssertionError("cached")):
            self.assertEqual(get(self.srv, "/api/judge/r1", token=self.srv.token)[0], 200)      # same record: cached


class TestHiddenTab(Env):
    def make(self):
        srv = ui.UI(Paths(self.hub), idle_s=60, first_beat_s=120, hidden_idle_s=300)
        self.addCleanup(srv.httpd.server_close)
        return srv

    def test_hidden_ten_minutes_with_a_beat_a_minute_stays_up(self):
        srv, t0 = self.make(), 1_000_000.0
        srv.beat(t0)
        srv.beat(t0 + 5, hidden=True)                                    # the tab went to the background
        for s in range(5, 600):
            if s % 61 == 5:                                              # throttled: about one beat a minute
                srv.beat(t0 + s, hidden=True)
            self.assertFalse(srv.should_stop(t0 + s + 0.5), s)
        srv.beat(t0 + 600)                                               # shown again
        self.assertFalse(srv.should_stop(t0 + 650))
        self.assertTrue(srv.should_stop(t0 + 661))                       # visible: back to 60 s

    def test_no_beats_stops_as_before_and_a_closed_hidden_tab_still_ends_it(self):
        srv, t0 = self.make(), 1_000_000.0
        srv.beat(t0)
        self.assertFalse(srv.should_stop(t0 + 59))
        self.assertTrue(srv.should_stop(t0 + 61))                        # unchanged: 60 s
        srv.beat(t0 + 100, hidden=True)
        self.assertFalse(srv.should_stop(t0 + 100 + 299))
        self.assertTrue(srv.should_stop(t0 + 100 + 301))                 # hidden then closed: not forever

    def test_heartbeat_query_marks_hidden(self):
        srv = ui.UI(Paths(self.hub), idle_s=30)
        th = threading.Thread(target=srv.serve, daemon=True)
        th.start()
        try:
            self.assertEqual(get(srv, "/api/alive?hidden=1", token=srv.token, method="POST")[0], 200)
            self.assertTrue(srv.hidden)
            self.assertEqual(get(srv, "/api/alive", token=srv.token, method="POST")[0], 200)
            self.assertFalse(srv.hidden)
        finally:
            srv.stop()
            th.join(5)


class TestRunningNow(Env):
    def setUp(self):
        super().setUp()
        self.p = Paths(self.hub)
        (self.work / ".git").mkdir()

    def test_each_run_state_listed_or_not(self):
        now = time.time()
        put_run(self.hub, "r-run", self.work, lead_session="L", state="running", result=None, ok=False, attempts=[],
                ts=now - 90, label="parser")
        put_run(self.hub, "r-stuck", self.work, lead_session="L", state="running", result=None, ok=False, attempts=[],
                ts=now - 3600)
        old = now - 30 * 60
        for f in (self.hub / "ccx" / "runs" / "r-stuck" / "run.json", self.hub / "ccx" / "runs" / "r-stuck"):
            os.utime(f, (old, old))
        put_run(self.hub, "r-done", self.work, lead_session="L")
        put_run(self.hub, "r-fail", self.work, lead_session="L", ok=False, result={"status": "failed", "summary": "x"})
        put_run(self.hub, "r-judged", self.work, lead_session="L", verdict={"ok": True})
        put_run(self.hub, "r-eval", self.work, state="running", result=None, ok=False, attempts=[],
                label="eval-7c:x", ts=now - 10)
        wq.add(self.work, "queued piece", "q")
        wq.update(self.work, "q1", status="doing")                       # doing, but no live run: not listed
        d = ui.collect(self.p, quota_wait=False)
        by = {r["run_id"]: r for r in d["running"]}
        self.assertEqual(set(by), {"r-run", "r-stuck", "r-eval"})
        self.assertEqual([r["run_id"] for r in d["running"]], ["r-stuck", "r-run", "r-eval"])      # oldest first
        run = by["r-run"]
        self.assertEqual((run["title"], run["worker"], run["btn"], run["stale"]), ("parser", "codex", "c0", False))
        self.assertGreaterEqual(run["secs"], 89)
        self.assertEqual(run["cmd"], "ccx stop r-run")
        self.assertIsNone(run["tokens"])                                 # unknown: not 0
        self.assertEqual((by["r-stuck"]["btn"], by["r-stuck"]["stale"]), ("a1", True))   # the stale card's stop
        self.assertTrue(by["r-eval"]["test"] and not run["test"])
        srv = ui.UI(self.p, idle_s=30)                                   # the strip's button is the piece's own
        self.addCleanup(srv.httpd.server_close)
        b = srv.find_button({"project": run["project"], "task": run["task"], "piece": run["piece"], "btn": run["btn"]})
        self.assertEqual((b["label"], b["argv"], b["spends"]), ("b_stop", ["ccx", "stop", "r-run"], False))

    def test_tokens_when_the_session_file_says(self):
        sid = "019a0000-0000-7000-8000-0000000000aa"
        put_run(self.hub, "r-live", self.work, state="running", result=None, ok=False, attempts=[], session_id=sid)
        d = self.home_codex / "sessions" / "2026" / "10" / "29"
        d.mkdir(parents=True)
        (d / f"rollout-2026-10-29T10-00-00-{sid}.jsonl").write_text(json.dumps(
            {"timestamp": "2026-10-29T10:00:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 400, "output_tokens": 20}}}}) + "\n", encoding="utf-8")
        self.assertEqual(ui.collect(self.p, quota_wait=False)["running"][0]["tokens"], 420)

    def test_task_without_a_title_takes_its_first_pieces(self):
        put_run(self.hub, "r-a", self.work, lead_session="L2", label="first piece", ts=time.time() - 50)
        put_run(self.hub, "r-b", self.work, lead_session="L2", label="second piece", ts=time.time() - 40)
        with mock.patch.object(ui, "_lead_of_session", return_value={"agent": "claude", "model": "", "title": ""}):
            tk = ui.collect(self.p, quota_wait=False)["projects"][0]["tasks"][0]
        self.assertEqual(len(tk["pieces"]), 2)
        self.assertEqual(tk["title"], "first piece")


class TestPageMarkup(unittest.TestCase):
    def setUp(self):
        self.js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.s = json.loads((STATIC / "strings.json").read_text(encoding="utf-8"))

    def fn(self, name: str) -> str:
        m = re.search(r"\n  function " + name + r"\(.*?\n  }\n", self.js, re.S)
        self.assertIsNotNone(m, name)
        return m.group(0)

    def test_todo_chips_are_buttons_and_no_hrefless_anchors(self):
        self.assertIn('<button type="button" data-sel=', self.js)
        self.assertIn('<button type="button" data-filt="mine"', self.js)
        for m in re.finditer(r"<a\b", self.js):                          # every anchor the page draws has an href
            tag = self.js[m.start():self.js.index("</a>", m.start())]
            self.assertIn("href=", tag, tag[:120])

    def test_one_persistent_live_region(self):
        self.assertEqual(len(re.findall(r'aria-live="polite"', self.html)), 1)
        region = re.search(r'<div id="announce"[^>]*>', self.html).group(0)
        self.assertIn('aria-live="polite"', region)
        self.assertLess(self.html.index('id="announce"'), self.html.index("<script"))
        self.assertGreater(self.html.index('id="announce"'), self.html.index('id="main"'))   # outside the redrawn part
        self.assertNotIn("aria-live", self.js)                          # never re-created by a redraw
        self.assertIn('$("announce")', self.fn("announce"))
        self.assertIn("textContent", self.fn("announce"))               # text, never markup

    def test_data_in_the_card_and_strip_is_escaped(self):
        data = re.compile(r"\b(path|tail|cmd|verification|summary|broken|weak|diff|title|said_not_changed|"
                          r"changed_not_said|chain_from|error)\b")
        for name in ("judgeHTML", "runningHTML", "fileList", "diffLines"):
            for expr in re.findall(r"\$\{([^{}]*)\}", self.fn(name)):
                if data.search(expr):
                    self.assertRegex(expr.strip(), r"^(esc|diffLines|t)\(", f"{name}: ${{{expr}}}")
        self.assertIn("esc(l)", self.fn("diffLines"))
        self.assertIn("esc(x)", self.fn("fileList"))

    def test_heartbeat_says_hidden_and_beats_on_show_and_focus(self):
        self.assertIn('"?hidden=1"', self.fn("alive"))
        self.assertIn('addEventListener("visibilitychange", alive)', self.js)
        self.assertIn('addEventListener("focus", alive)', self.js)

    def test_strip_stop_goes_through_prepare_and_confirm(self):
        self.assertIn("pressBtn(el.dataset.key, f.p, el.dataset.rbtn)", self.js)
        self.assertIn("data-rbtn", self.fn("runningHTML"))
        self.assertIn("data-actbox", self.fn("runningHTML"))            # the confirmation box shows the command

    def test_notes_and_new_words_exist_in_both_languages(self):
        py = Path(ui.__file__).read_text(encoding="utf-8")
        keys = set(re.findall(r'"(j_[a-z_]+)"', py)) | set(re.findall(r'"(j_[a-z_]+)"', self.js))
        self.assertIn("j_no_snapshot", keys)
        for k in sorted(keys | {"run_now", "run_for", "run_tokens", "run_stale", "todo_new"}):
            for lg in ("zh", "en"):
                self.assertIn(k, self.s[lg], f"{lg}: {k}")


if __name__ == "__main__":
    unittest.main()
