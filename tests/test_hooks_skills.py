"""L4 hook time limit, L7 `ccx skills stats`, L6 setup's notes from recent sessions. Session files are made up here."""
import json
import os
import re
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ccx import hooktimeout, memory, memsuggest, setup, skillstats  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TestHookTimeout(Env):
    def test_which_commands_are_hooks(self):
        self.assertEqual(hooktimeout.hook_name(["turn", "--as", "claude"]), "turn")
        self.assertEqual(hooktimeout.hook_name(["mem", "delta", "--as", "codex"]), "mem delta")
        self.assertEqual(hooktimeout.hook_name(["lead", "--hint"]), "lead --hint")
        self.assertIsNone(hooktimeout.hook_name(["mem", "search", "x"]))
        self.assertIsNone(hooktimeout.hook_name(["lead"]))

    def test_a_slow_read_prints_nothing_exits_0_and_logs_one_line(self):
        # the hook's JSON never arrives on stdin: `ccx turn` sits in its read, as on a stuck pipe or slow disk
        e = {**self.env, "CCX_HOOK_TIMEOUT_S": "1"}
        t0 = time.monotonic()
        proc = subprocess.Popen([sys.executable, str(ROOT / "ccx.py"), "turn", "--as", "claude"], cwd=self.work,
                                env=e, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.wait(timeout=30)                  # stdin stays open: only the time limit can end it
        finally:
            proc.stdin.close()
            proc.kill()
        out, err = proc.stdout.read(), proc.stderr.read()
        self.assertLess(time.monotonic() - t0, 25)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out, b"")
        self.assertEqual(err, b"")
        lines = (self.hub / "ccx" / "hook-timeouts.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["cmd"], "turn")
        self.assertGreaterEqual(rec["elapsed_s"], 1)
        self.assertIn("cmd_turn", rec["step"])
        state, detail = hooktimeout.doctor_row(Paths(self.hub))
        self.assertEqual(state, "WARN")
        self.assertIn("1 in 7 days (turn 1)", detail)

    def test_a_normal_hook_prints_the_same(self):
        for args, stdin in ((("turn", "--as", "claude"), "{}"), (("mem", "delta", "--as", "codex", "--peek"), "")):
            memory.add(Paths(self.hub), "keep PR text short", "user", "preference")
            without = self.ccx(*args, stdin=stdin, env={"CCX_HOOK_TIMEOUT_S": "0"})
            within = self.ccx(*args, stdin=stdin, env={"CCX_HOOK_TIMEOUT_S": "20"})
            self.assertEqual((within.returncode, within.stdout), (without.returncode, without.stdout))
        self.assertFalse((self.hub / "ccx" / "hook-timeouts.jsonl").exists())
        self.assertEqual(hooktimeout.doctor_row(Paths(self.hub))[0], "ok")

    def test_limit_from_settings(self):
        os.environ.pop("CCX_HOOK_TIMEOUT_S", None)
        p = Paths(self.hub)
        self.assertEqual(hooktimeout.limit(p), 2.0)
        r = self.ccx("config", "set", "hooks.timeout_s", "5", env={"CCX_HOOK_TIMEOUT_S": ""})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(hooktimeout.limit(p), 5.0)

    def test_old_lines_drop_out_of_the_count(self):
        p = Paths(self.hub)
        f = hooktimeout.log_file(p)
        f.parent.mkdir(parents=True, exist_ok=True)
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        f.write_text(json.dumps({"at": old, "cmd": "mem delta", "elapsed_s": 3, "step": "x"}) + "\nnot json\n",
                     encoding="utf-8")
        self.assertEqual(hooktimeout.recent(p), [])


def claude_records(now: datetime) -> list[dict]:
    old = now - timedelta(days=40)
    return [
        {"type": "assistant", "timestamp": iso(now), "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "relayline:agent-delegate"}}]}},
        {"type": "assistant", "timestamp": iso(old), "message": {"content": [          # outside --days
            {"type": "tool_use", "id": "t2", "name": "Skill", "input": {"skill": "task-split"}}]}},
        {"type": "user", "timestamp": iso(now), "message": {"content": "<command-name>/task-routing</command-name>"}},
        {"type": "user", "timestamp": iso(now), "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "<command-name>/task-split</command-name>"}]}},
    ]


def codex_records(now: datetime) -> list[dict]:
    return [
        {"timestamp": iso(now), "type": "session_meta", "payload": {"id": "s1", "cwd": "/work"}},
        {"timestamp": iso(now), "type": "response_item", "payload": {"type": "message", "role": "developer",
         "content": [{"type": "input_text", "text": "- task-split: ... (file: skills/task-split/SKILL.md)"}]}},
        {"timestamp": iso(now), "type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
         "input": "text(await tools.exec_command({cmd:\"Get-Content 'C:\\\\h\\\\skills\\\\task-split\\\\SKILL.md'\"}))"}},
        {"timestamp": iso(now), "type": "response_item", "payload": {"type": "function_call", "name": "shell",
         "arguments": json.dumps({"command": ["cat", "/h/.codex/skills/agent-delegate/SKILL.md"]})}},
    ]


def write_jsonl(f: Path, recs: list[dict]) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


class TestSkillStats(Env):
    def setUp(self):
        super().setUp()
        now = datetime.now(timezone.utc)
        write_jsonl(self.home_claude / "projects" / "-work" / "abc.jsonl", claude_records(now))
        write_jsonl(self.home_codex / "sessions" / "2026" / "10" / "25" / "rollout-x.jsonl", codex_records(now))
        sk = self.hub / "skills" / "never-used"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: never-used\ndescription: >\n  A skill nobody loads, with a long "
                                     "description.\n---\nbody\n", encoding="utf-8")

    def test_counts_unused_and_estimate(self):
        s = skillstats.stats([self.hub / "skills", ROOT / "skills"], self.home_claude, self.home_codex, days=7)
        by = {r["skill"]: r for r in s["used"]}
        self.assertEqual((by["agent-delegate"]["claude"], by["agent-delegate"]["codex"]), (1, 1))
        self.assertEqual((by["task-split"]["claude"], by["task-split"]["codex"]), (0, 1))   # prompt list, tool output
        self.assertEqual(by["task-routing"]["claude"], 1)
        unused = {r["skill"]: r for r in s["unused"]}
        self.assertIn("never-used", unused)
        self.assertIn("project-manager", unused)
        self.assertEqual(unused["never-used"]["listing_tokens_est"],
                         skillstats.est_tokens("- never-used: A skill nobody loads, with a long description."))
        self.assertEqual(s["unused_listing_tokens_est"], sum(r["listing_tokens_est"] for r in s["unused"]))
        self.assertIn("estimate", s["note"])

    def test_cli_json_and_text(self):
        r = self.ccx("skills", "stats", "--days", "7", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = json.loads(r.stdout)
        self.assertIn("never-used", [x["skill"] for x in s["unused"]])
        r = self.ccx("skills", "stats", "--days", "60")
        self.assertIn("Never loaded", r.stdout)
        self.assertIn("ccx deletes nothing", r.stdout)
        self.assertTrue((self.hub / "skills" / "never-used" / "SKILL.md").exists())

    def test_cjk_estimate(self):
        self.assertEqual(skillstats.est_tokens("abcd"), 1)
        self.assertEqual(skillstats.est_tokens("技能说明"), 4)


class FakeWizard(setup.Wizard):
    def __init__(self, answers):
        super().__init__(False, True)
        self.answers, self.said = list(answers), []

    def say(self, text=""):
        self.said.append(text)

    def ask(self, question, default=False):
        if not self.answers:
            self.interactive = False
            return False
        return self.answers.pop(0)


class TestColdStart(Env):
    def setUp(self):
        super().setUp()
        recs = [{"type": "user", "message": {"content": "From now on keep the PR text in Chinese."}},
                {"type": "user", "message": {"content": "以后不要提交 two-way-test-log.txt。"}}]
        write_jsonl(self.home_claude / "projects" / "-work" / "abc.jsonl", recs)
        old = self.home_claude / "projects" / "-work" / "old.jsonl"
        write_jsonl(old, [{"type": "user", "message": {"content": "Always use tabs in the old project."}}])
        t = time.time() - 30 * 86400
        os.utime(old, (t, t))

    def test_only_a_yes_writes_a_note(self):
        p = Paths(self.hub)
        w = FakeWizard([True, True, False])                    # scan: yes; first: keep; second: no
        setup.cold_start(w, p)
        notes = [e["text"] for e in memory.entries(p)]
        self.assertEqual(len(notes), 1)
        self.assertFalse(any("tabs" in n for n in notes))      # older than the window: not read
        st = {i["status"] for i in memsuggest.load(p)}
        self.assertEqual(st, {"accepted", "rejected"})
        self.assertTrue(any("kept 1" in s for s in w.said))

    def test_no_on_the_scan_reads_nothing(self):
        p = Paths(self.hub)
        setup.cold_start(FakeWizard([False]), p)
        self.assertEqual(memsuggest.load(p), [])

    def test_skipped_when_not_on_a_terminal(self):
        p = Paths(self.hub)
        w = setup.Wizard(False, False)
        setup.cold_start(w, p)
        self.assertEqual(memsuggest.load(p), [])
        w = setup.Wizard(True, False)                          # --yes cannot answer each note
        setup.cold_start(w, p)
        self.assertEqual(memsuggest.load(p), [])

    def test_input_ends_the_rest_wait(self):
        p = Paths(self.hub)
        setup.cold_start(FakeWizard([True]), p)                # scan: yes; then input ends
        self.assertEqual([i["status"] for i in memsuggest.load(p)], ["pending", "pending"])
        self.assertEqual(memory.entries(p), [])


if __name__ == "__main__":
    unittest.main()
