"""[subagents] fork_turns (B3 item 7, ccx/subagents.py): with "none", a `--parallel` Codex piece is asked to start its
own sub-agents without its history (spawn_agent's fork_turns, codex-cli 0.164.0). Default "all": nothing changes.
Fakes only."""
import json

from test_ccx import Env

from ccx import subagents

BRIEF = "Fix three modules:\n- a.py\n- b.py\n- c.py"


class TestForkTurns(Env):
    def tiers(self, text: str) -> None:
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        (self.hub / "ccx" / "tiers.toml").write_text(text, encoding="utf-8")

    def go(self, to: str, *flags) -> tuple[dict, dict]:
        r = self.ccx("run", "--from", "claude", "--to", to, "--tier", "T1", "--new", *flags, BRIEF)
        out = json.loads(r.stdout)
        rec = json.loads((self.hub / "ccx" / "runs" / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        return self.calls()[-1], rec

    def test_default_all_adds_nothing(self):
        call, rec = self.go("codex", "--parallel")
        assert "explicitly asked to use sub-agents" in call["prompt"]
        assert "fork_turns" not in call["prompt"]
        assert "parallel_fork_turns" not in rec

    def test_none_tells_a_parallel_codex_piece_and_records_it(self):
        self.tiers('[subagents]\nfork_turns = "none"\n')
        call, rec = self.go("codex", "--parallel")
        assert subagents.FORK_NONE.strip() in call["prompt"]
        assert call["prompt"].index("explicitly asked to use sub-agents") < call["prompt"].index('fork_turns="none"')
        assert rec["parallel_fork_turns"] == "none"

    def test_none_needs_parallel_and_codex(self):
        self.tiers('[subagents]\nfork_turns = "none"\n')
        call, rec = self.go("codex")                                     # no --parallel: no sub-agent request at all
        assert "fork_turns" not in call["prompt"] and "parallel_fork_turns" not in rec
        call, rec = self.go("claude", "--parallel")                      # Claude's Agent tool has no such parameter
        assert "explicitly asked to use sub-agents" in call["prompt"]
        assert "fork_turns" not in call["prompt"] and "parallel_fork_turns" not in rec
        call, rec = self.go("codex", "--parallel", "--subagents", "off")  # sub-agents off: nothing to fork
        assert "fork_turns" not in call["prompt"]


def test_setting_values():
    assert subagents.fork_turns({}) == "all"
    assert subagents.fork_turns({"subagents": {"fork_turns": " NONE "}}) == "none"
    assert subagents.fork_turns({"subagents": {"fork_turns": "some"}}) == "all"
    assert subagents.fork_turns({"subagents": {"fork_turns": None}}) == "all"
