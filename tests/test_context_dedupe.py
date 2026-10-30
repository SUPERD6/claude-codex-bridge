"""[shared_context] dedupe (B3 item 9, off by default): a "Settled" sentence already standing whole in an ask shown
above it is not repeated; nothing else is cut. The run records est_tokens (and, with the switch, what was left out).
Fake transcripts only."""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccx import context_share as cs  # noqa: E402
from test_adapters import AdapterEnv  # noqa: E402
from test_context_share import SID, _w, claude_lead  # noqa: E402

ASK = "We decided: an empty list returns None, never raise."
SETTLED_ONLY = "Going with None for empty input."          # the lead's own words: not in any ask


def _text(tmp: Path, **kw) -> tuple[str, dict]:
    f = _w(tmp / "lead.jsonl", claude_lead())
    stats: dict = {}
    return cs.summary(cs.events_claude(f), "claude", "s", tmp, "t", stats=stats, **kw), stats


def _settled(text: str) -> str:
    return text.split("Settled in that conversation")[1].split("\n\n")[0] if "Settled in" in text else ""


def test_off_by_default_repeats_as_before(tmp_path):
    text, stats = _text(tmp_path)
    assert ASK in _settled(text) and stats == {}


def test_on_drops_only_sentences_already_asked(tmp_path):
    before, _ = _text(tmp_path)
    text, stats = _text(tmp_path, dedupe=True)
    assert ASK not in _settled(text)                      # it is in "The person asked" above
    assert ASK in text.split("Settled in")[0]
    assert SETTLED_ONLY in _settled(before) and SETTLED_ONLY in _settled(text)   # the lead's own decision stays
    assert stats["deduped"] >= 1 and stats["deduped_chars"] >= len(ASK)
    assert len(text) < len(before)
    # everything but the Settled block is the same text
    assert before.split("Settled in")[0] == text.split("Settled in")[0]


def test_every_ab_task_keeps_its_settled_point_with_dedupe(tmp_path):
    """scripts/eval/shared_context_ab.py: whatever was settled must still be in the block (in the asks or in
    Settled), after the option the person reversed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))
    import shared_context_ab as ab
    for t in ab.TASKS:
        f = _w(tmp_path / f"{t['id']}.jsonl", ab.lead_transcript(t, time.time()))
        text = cs.summary(cs.events_claude(f), "claude", "s", tmp_path, "t", dedupe=True)
        assert t["settle"][:30] in text, t["id"]
        if t["reversed"]:
            assert text.index(t["reversed"][:20]) < text.rindex(t["settle"][:30]), t["id"]


class TestRunRecord(AdapterEnv):
    LEAD = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": SID}

    def lead(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / f"{SID}.jsonl", claude_lead())

    def _go(self):
        self.lead()
        out = self.j("run", "--from", "claude", "--to", "codex", "--tier", "T2", "--mode", "write", "fix calc.py",
                     env=self.LEAD)
        return self.calls()[-1]["prompt"], self.rec(out["run_id"])["shared_context"]

    def test_est_tokens_always_and_dedupe_counts_only_when_on(self):
        prompt, meta = self._go()
        assert meta["est_tokens"] > 0 and "deduped" not in meta
        assert prompt.count(ASK) == 2                        # asked, then settled
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        (self.hub / "ccx" / "tiers.toml").write_text("[shared_context]\ndedupe = true\n", encoding="utf-8")
        prompt, meta = self._go()
        assert prompt.count(ASK) == 1 and meta["deduped"] >= 1
