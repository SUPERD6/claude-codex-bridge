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


def test_a_decision_the_lead_restated_after_a_reopened_question_stays(tmp_path):
    evs: list[dict] = []
    t = time.time() - 100
    cs._said(t, "person", "We decided to store config as JSON.", evs)
    cs._said(t + 10, "person", "Hmm, maybe switch to YAML instead?", evs)
    cs._said(t + 20, "claude", "We decided to store config as JSON. YAML adds a dependency.", evs)
    cs._said(t + 25, "person", "Nobody said we must keep the v1 API. Drop it.", evs)
    cs._said(t + 30, "claude", "We must keep the v1 API for now.", evs)
    stats: dict = {}
    text = cs.summary(evs, "claude", "s", tmp_path, "t", dedupe=True, stats=stats)
    settled = _settled(text)
    assert "[" in settled and "claude] We decided to store config as JSON." in settled   # the lead's word stays
    assert "We must keep the v1 API for now." in settled
    assert "person] Nobody said" not in settled      # the person's own sentence: shown in the ask above
    assert stats["deduped"] >= 1


def test_dedupe_does_not_change_how_many_items_are_shown(tmp_path):
    evs: list[dict] = []
    t0 = time.time() - 500
    for k in range(6):
        cs._said(t0 + k, "person", f"Ask {k}: we decided rule {k} holds for module_{k}. " + "detail " * 40, evs)
    cs._said(t0 + 50, "claude", "Done with the rules.", evs)
    full = cs.summary(evs, "claude", "s", tmp_path, "t")
    for limit in range(800, len(full) + 200, 150):
        a = cs.summary(evs, "claude", "s", tmp_path, "t", limit)
        b = cs.summary(evs, "claude", "s", tmp_path, "t", limit, dedupe=True)
        assert a.split("Settled in")[0] == b.split("Settled in")[0], limit      # same asks, same everything else
        assert a.count("\n- [") >= b.count("\n- [") >= a.count("\n- [") - 8   # only Settled lines go
        assert ("(trimmed)" in b) <= ("(trimmed)" in a)          # a shorter block is cut less, never more


def test_a_sentence_only_in_the_cut_off_part_of_an_ask_is_kept(tmp_path):
    evs: list[dict] = []
    t0 = time.time() - 100
    long_ask = "We never raised errors here before. " + "x" * 470 + ". From now on we decided: never raise."
    cs._said(t0, "person", long_ask, evs)
    cs._said(t0 + 5, "person", "Please fix it.", evs)            # the long one is an older ask: cut at 500
    stats: dict = {}
    text = cs.summary(evs, "claude", "s", tmp_path, "t", dedupe=True, stats=stats)
    assert "From now on we decided: never raise." in _settled(text)          # not shown above: kept


def test_codex_lead_asks_and_their_decisions_share_a_time(tmp_path):
    from test_context_share import codex_session
    f = _w(tmp_path / "rollout.jsonl", codex_session(str(tmp_path)))
    evs = cs.events_codex(f)
    evs.append(dict(next(e for e in evs if e["kind"] == "ask"), kind="decision", text="Rename parse() to parse_rows()."))
    stats: dict = {}
    cs.summary(evs, "codex", "s", tmp_path, "t", dedupe=True, stats=stats)
    assert stats["deduped"] == 1


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
