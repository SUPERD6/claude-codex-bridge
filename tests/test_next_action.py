"""For every kind that asks the lead (or the person) to act, the run's hint (compact), `ccx ui`'s decide card and the
agent-delegate skill name the same first action. Plan #4: on review_failed the hint said "or `ccx resume`", the ui's
primary button was resume, and the skill said not to resume."""
import json
import re
import time
from pathlib import Path

import pytest

from ccx import ui
from ccx.delegate import compact

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "agent-delegate" / "SKILL.md").read_text(encoding="utf-8")
SKILL_ZH = (ROOT / "skills" / "agent-delegate" / "README.zh.md").read_text(encoding="utf-8")
STRINGS = json.loads((ROOT / "ccx" / "ui_static" / "strings.json").read_text(encoding="utf-8"))

# the first of these a text names is the action it asks for first
MARKERS = [("lead_fixes", r"fix\s+the\s+real\s+ones\s+yourself|属实的自己修"), ("rerun_write", r"--mode write"),
           ("resume", r"\bresume\b")]


def first_action(text: str) -> str | None:
    hits = [(m.start(), name) for name, pat in MARKERS for m in [re.search(pat, text)] if m]
    return min(hits)[1] if hits else None


def record(kind: str) -> dict:
    rec = {"run_id": "20991231-100000-aaaa", "to": "codex", "tier": "T2", "cwd": "", "ok": True, "kind": kind,
           "state": "finished", "error": None, "ts": time.time(), "session_id": "s1",
           "result": {"status": "done", "summary": "did it", "files_changed": ["a.py"]},
           "attempts": [{"rung": "codex:gpt-6-luna:low", "model": "gpt-6-luna", "effort": "low", "usage": {}}]}
    if kind in ("check_failed", "check_broken"):
        rec["check"] = {"cmd": "pytest -q", "passed": False, "exit": 1 if kind == "check_failed" else 5,
                        **({"broken": "pytest collected no tests"} if kind == "check_broken" else {})}
    if kind == "review_failed":
        rec["review"] = {"verdict": "issues", "issues": ["[must] a.py:1 - off by one"], "by": "claude:haiku:low"}
    if kind in ("quota", "timeout", "over_budget"):
        rec.update(ok=False, error="stopped over the sub-agent spending cap" if kind == "over_budget" else kind)
    if kind == "needs_write":
        rec["result"]["status"] = "blocked"
    return rec


def skill_bullet(text: str, kind: str) -> str:
    """The skill's bullet for this kind: from "- `kind`" to the next bullet or blank line."""
    m = re.search(rf"^\s*- `{kind}`.*?(?=^\s*- |^\s*$|\Z)", text, re.S | re.M)
    assert m, f"the skill has no bullet for {kind}"
    return m.group(0)


# kind, the first action all three ask for, whether the skill has a bullet for the kind
TABLE = [
    ("review_failed", "lead_fixes", True),
    ("no_changes", "resume", True),
    ("check_broken", "resume", True),
    ("check_failed", "resume", False),
    ("needs_write", "rerun_write", False),
    ("quota", "resume", False),
    ("timeout", "resume", False),
    ("over_budget", "resume", False),
]


@pytest.mark.parametrize("kind,action,in_skill", TABLE)
def test_hint_ui_and_skill_agree_on_the_first_action(kind, action, in_skill):
    rec = record(kind)
    hint = compact(rec).get("hint") or ""
    assert first_action(hint) == action, hint
    card = ui._act(rec, None, time.time(), None)
    assert card and card["kind"] == "decide", card
    primary = [b for b in card["buttons"] if b["style"] == "primary"]
    assert len(primary) == 1, card["buttons"]
    assert first_action(primary[0]["cmd"]) == action, primary[0]
    if in_skill:
        for text in (SKILL, SKILL_ZH):
            bullet = skill_bullet(text, kind)
            assert first_action(bullet) == action, bullet


def test_review_failed_keeps_one_more_round_as_a_secondary_choice_that_costs_a_run():
    card = ui._act(record("review_failed"), None, time.time(), None)
    more = [b for b in card["buttons"] if b["label"] == "b_one_more"]
    assert more and more[0]["style"] != "primary" and more[0]["argv"][:2] == ["ccx", "resume"]
    assert more[0]["spends"]                                     # the page asks before it spends
    assert "costs a run" in STRINGS["en"]["b_one_more"] and "多花一次运行" in STRINGS["zh"]["b_one_more"]
    hint = compact(record("review_failed"))["hint"]
    assert "costs a run" in hint and "only when the person asks" in hint
    assert "costs a run" in skill_bullet(SKILL, "review_failed")
    assert "多花一次运行" in skill_bullet(SKILL_ZH, "review_failed")
