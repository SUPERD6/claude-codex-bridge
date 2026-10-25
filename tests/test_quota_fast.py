"""Codex quota is read from the ends of its newest session files (not a full scan), cached by (path, mtime, size),
and agrees with the full scan. Synthetic session files only."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ccx import quota, usage
from ccx.config import Paths


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def tc(t, used, reset, filler=0):
    """One token_count line, as codex-cli 0.164 writes it (filler: a long tool output in between)."""
    rows = []
    if filler:
        rows.append({"timestamp": iso(t), "type": "response_item", "payload": {"type": "function_call_output",
                                                                               "output": "x" * filler}})
    rows.append({"timestamp": iso(t), "type": "event_msg", "payload": {
        "type": "token_count", "info": {"total_token_usage": {"input_tokens": 1, "cached_input_tokens": 0,
                                                              "output_tokens": 1}},
        "rate_limits": {"primary": {"used_percent": used, "window_minutes": 10080, "resets_at": reset}}}})
    return "".join(json.dumps(r) + "\n" for r in rows)


class TestCodexQuotaFast(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.p = t / "codex", Paths(t / "hub")
        self.day = self.home / "sessions" / "2026" / "10" / "25"
        self.day.mkdir(parents=True)
        self.now = time.time()
        self.reset = int(self.now + 5 * 86400)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, mtime):
        f = self.day / f"rollout-{name}.jsonl"
        f.write_text(text, encoding="utf-8")
        os.utime(f, (mtime, mtime))
        return f

    def test_a_big_long_session_keeps_its_earlier_readings_and_agrees_with_the_full_scan(self):
        # 30 hours of readings, 40 KB of tool output between them: ~2 MB, the early ones far from the end
        text = "".join(tc(self.now - h * 3600, 10 + (30 - h), self.reset, filler=40_000) for h in range(30, -1, -1))
        self.write("long", text, self.now)
        fast = quota.pace(quota.codex_readings(p=self.p, home=self.home, now=self.now), now=self.now)
        _, s = usage.codex_events(self.now - 8 * 86400, set(), home=self.home)
        full = quota.pace([{"ts": x["ts"], "window": x["window"], "used": x["used_percent"] / 100,
                            "resets_at": x.get("resets_at")} for x in s], now=self.now)
        self.assertIn("per_day", fast["primary"])                  # enough history to project
        self.assertAlmostEqual(fast["primary"]["projected"], full["primary"]["projected"], delta=0.05)
        self.assertEqual(fast["primary"]["used"], full["primary"]["used"])
        self.assertIn("read_at", fast["primary"])                   # when the reading was taken

    def test_newest_file_without_quota_lines_looks_further_back(self):
        self.write("old", tc(self.now - 3 * 86400, 33, self.reset), self.now - 3 * 86400)
        self.write("new", '{"type": "session_meta", "payload": {"id": "x"}}\n', self.now)
        rs = quota.codex_readings(p=self.p, home=self.home, now=self.now)
        self.assertEqual([r["used"] for r in rs], [0.33])
        pc = quota.pace(rs, now=self.now)["primary"]
        self.assertEqual(pc["reading_age_min"], 3 * 24 * 60)        # an old reading says how old it is

    def test_cached_by_path_mtime_and_size(self):
        f = self.write("a", tc(self.now - 60, 20, self.reset), self.now - 60)
        self.assertEqual([r["used"] for r in quota.codex_readings(p=self.p, home=self.home, now=self.now)], [0.2])
        cache = json.loads((self.p.state / "codex-quota-cache.json").read_text(encoding="utf-8"))
        self.assertEqual(list(cache), [str(f)])
        # same mtime and size: the cached readings are used, the file is not read again
        f.write_text(tc(self.now - 60, 99, self.reset), encoding="utf-8")
        os.utime(f, (self.now - 60, self.now - 60))
        self.assertEqual([r["used"] for r in quota.codex_readings(p=self.p, home=self.home, now=self.now)], [0.2])
        # it grew: read again
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(tc(self.now - 30, 21, self.reset))
        os.utime(f, (self.now - 30, self.now - 30))
        self.assertEqual(sorted(r["used"] for r in quota.codex_readings(p=self.p, home=self.home, now=self.now)),
                         [0.21, 0.99])

    def test_only_recent_files_are_opened(self):
        for k in range(60):                  # older than the pace window: never opened once a recent one answers
            self.write(f"old{k}", tc(self.now - 4 * 86400, 50, self.reset), self.now - 4 * 86400 - k)
        self.write("new", tc(self.now - 10, 12, self.reset), self.now - 10)
        rs = quota.codex_readings(p=self.p, home=self.home, now=self.now)
        self.assertEqual([r["used"] for r in rs], [0.12])


if __name__ == "__main__":
    unittest.main()
