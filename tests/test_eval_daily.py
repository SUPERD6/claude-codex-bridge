"""The daily-config arms of scripts/eval/r5.py (B3 item 2): a per-unit Codex home built from the person's memories,
AGENTS.md and skills with the eval home's login, never their auth, credentials, config, sessions or logs. Fake homes
only; nothing is started."""
import argparse
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import pytest  # noqa: E402
import daily_home as DH  # noqa: E402
import preflight as PF  # noqa: E402
import r5  # noqa: E402

SECRET = "PERSON-SECRET-7731"


@pytest.fixture
def homes(tmp_path):
    """A person's ~/.codex and ~/.agents full of decoys, and an eval Codex home with its own login."""
    me = tmp_path / "me"
    codex, agents, ev = me / ".codex", me / ".agents", tmp_path / "eval-codex"
    files = {
        codex / "auth.json": SECRET, codex / ".credentials.json": SECRET,
        codex / "config.toml": ('model = "x"\n[features]\nmemories = true\nhooks = true\n[memories]\n'
                                'use_memories = true\ngenerate_memories = false\n[hooks]\nSessionStart = "' + SECRET
                                + '"\n[projects."C:/secret"]\ntrust_level = "trusted"\n'),
        codex / "sessions" / "2026" / "rollout-1.jsonl": SECRET, codex / "archived_sessions" / "a.jsonl": SECRET,
        codex / "log" / "codex-tui.log": SECRET, codex / "history.jsonl": SECRET, codex / "state.sqlite": SECRET,
        codex / "rules" / "default.rules": SECRET, codex / "plugins" / "p.json": SECRET,
        codex / "memories" / "notes.md": "remember: tabs", codex / "memories" / "auth.json": SECRET,
        codex / "memories" / "run.log": SECRET,
        codex / "AGENTS.md": "# my rules\nanswer in Chinese\n",
        codex / "skills" / "mine" / "SKILL.md": "---\nname: mine\n---\n", codex / "skills" / "mine" / "token.json": SECRET,
        codex / "skills" / ".system" / "x" / "SKILL.md": "system",
        agents / "skills" / "shared" / "SKILL.md": "---\nname: shared\n---\n", agents / ".credentials.json": SECRET,
        agents / "skills" / "shared" / ".env": SECRET,
        ev / "auth.json": "EVAL-LOGIN", ev / "config.toml": "[features]\napps = false\n",
    }
    for f, text in files.items():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return {"codex": codex, "agents": agents, "eval": ev, "tmp": tmp_path}


def build(homes, dest=None):
    return DH.build(dest or homes["tmp"] / "x-unit", homes["eval"], homes["codex"], homes["agents"],
                    kept=PF.codex_kept_toml(homes["codex"]), features_off=PF.CODEX_FEATURES_OFF)


def all_text(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*") if p.is_file())


def test_daily_home_has_memories_agents_skills_and_the_eval_login_only(homes):
    info = build(homes)
    codex, home = Path(info["codex_home"]), Path(info["agent_home"])
    assert (codex / "auth.json").read_text(encoding="utf-8") == "EVAL-LOGIN"
    assert (codex / "memories" / "notes.md").exists() and (codex / "AGENTS.md").exists()
    assert (codex / "skills" / "mine" / "SKILL.md").exists() and (home / ".agents" / "skills" / "shared" / "SKILL.md").exists()
    names = {p.relative_to(codex).as_posix() for p in codex.rglob("*")}
    for gone in ("sessions", "archived_sessions", "log", "history.jsonl", "state.sqlite", "rules", "plugins",
                 ".credentials.json", "memories/auth.json", "memories/run.log", "skills/mine/token.json"):
        assert gone not in names
    assert not (home / ".agents" / ".credentials.json").exists()
    assert SECRET not in all_text(codex) + all_text(home)          # nothing of the person's auth, hooks or trust
    assert info["copied"] == ["codex:memories", "codex:AGENTS.md", "codex:skills", "agents:skills"]
    assert info["auth"] == "eval-codex-home"


def test_daily_config_keeps_only_memory_settings_and_turns_connectors_off(homes):
    info = build(homes)
    cfg = tomllib.loads((Path(info["codex_home"]) / "config.toml").read_text(encoding="utf-8"))
    assert cfg["features"] == {"apps": False, "plugins": False, "remote_plugin": False, "memories": True}
    assert cfg["memories"] == {"use_memories": True, "generate_memories": False}
    assert set(cfg) == {"features", "memories"}                   # no model, hooks, projects (trust) or anything else
    assert info["memory_settings"] == {"features.memories": True, "memories.use_memories": True,
                                       "memories.generate_memories": False}


def test_daily_home_needs_the_eval_login(homes):
    (homes["eval"] / "auth.json").unlink()
    with pytest.raises(RuntimeError, match="no login"):
        build(homes)


def test_daily_home_without_person_files_is_just_the_login(homes, tmp_path):
    empty = tmp_path / "nobody"
    empty.mkdir()
    info = DH.build(tmp_path / "x2", homes["eval"], empty / ".codex", empty / ".agents")
    assert info["copied"] == [] and info["files"] == 2          # auth.json + config.toml
    assert info["memory_settings"] == {}


def test_links_are_not_followed(homes, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "auth.json").write_text(SECRET, encoding="utf-8")
    try:
        (homes["codex"] / "skills" / "link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    info = build(homes)
    assert not (Path(info["codex_home"]) / "skills" / "link").exists()
    assert SECRET not in all_text(Path(info["codex_home"]))


def test_unit_env_drops_isolation_and_points_at_the_daily_home(homes):
    info = build(homes)
    env = {"CCX_CODEX_ISOLATE": "1", "CCX_CLAUDE_NO_SKILLS": "1", "CCX_CLAUDE_SETTING_SOURCES": "project,local",
           "CCX_CLAUDE_SETTINGS": "s.json", "CODEX_HOME": "eval", "CCX_AGENT_HOME": "empty"}
    out = DH.unit_env(env, info)
    assert "CCX_CODEX_ISOLATE" not in out and "CCX_CLAUDE_NO_SKILLS" not in out
    assert out["CODEX_HOME"] == out["CODEX_SQLITE_HOME"] == info["codex_home"]
    assert out["CCX_AGENT_HOME"] == info["agent_home"] and out["CCX_CLAUDE_SETTING_SOURCES"] == "user,project,local"
    assert out["CCX_CLAUDE_SETTINGS"] == "s.json"                 # hooks off, auto-memory off, deny rules stay
    assert env["CCX_CODEX_ISOLATE"] == "1"                        # the clean-room env itself is not changed


def _unit(homes, hub):
    return PF.Unit(key="1-t-ccx2daily", work=homes["tmp"], repo=homes["tmp"] / "repo", hub=hub,
                   codex_home=homes["eval"])


@pytest.mark.parametrize("arm", sorted(r5.DAILY_ARMS))
def test_set_daily_writes_the_overlay_and_reads_it_back(homes, arm):
    from ccx.config import SUBAGENT_SWITCHES
    hub = homes["tmp"] / f"h-{arm}"
    r5.r3.make_hub(hub)
    a = argparse.Namespace(daily_codex_source=str(homes["codex"]), daily_agents_source=str(homes["agents"]))
    info, env = r5.set_daily(_unit(homes, hub), hub, {"CCX_CODEX_ISOLATE": "1"}, arm, a)
    assert info["switches"] == {**SUBAGENT_SWITCHES, **r5.DAILY_ARMS[arm]}
    assert env["CODEX_HOME"] == info["codex_home"] and "CCX_CODEX_ISOLATE" not in env
    tiers = r5.r2.Paths(hub).user_tiers
    text = tiers.read_text(encoding="utf-8") if tiers.exists() else ""
    assert ("[subagent]" in text) == bool(r5.DAILY_ARMS[arm])


def test_set_daily_needs_an_eval_codex_home(homes):
    hub = homes["tmp"] / "h"
    r5.r3.make_hub(hub)
    u = _unit(homes, hub)
    u.codex_home = None
    with pytest.raises(RuntimeError, match="--codex-home"):
        r5.set_daily(u, hub, {}, "ccx2daily", argparse.Namespace())


def test_daily_arms_are_additive():
    assert r5.ARMS == ("self", "builtin", "ccx", "direct")
    assert r5.OPT_IN_ARMS[:len(r5.OPT_IN_ARMS) - len(r5.DAILY_ARMS)] == (
        "ccx2", "builtin2", "builtin2r", *r5.TIER_ARMS, *r5.SKILL_ARMS, *r5.NAMECHECK_ARMS)
    for arm in r5.DAILY_ARMS:
        assert arm in r5.OPT_IN_ARMS and arm in r5.CCX_ARMS and arm in PF.CODEX_ARMS
        assert r5.lead_how(arm, "L") == r5.lead_how("ccx2", "L") and r5.lead_flags_arm(arm) == "ccx"
    assert r5.DAILY_ARMS == {"ccx2daily": {}, "ccx2daily_nomem": {"codex_memories": False},
                             "ccx2daily_clean": {"clean": True}, "ccx2daily_leantools": {"codex_lean_tools": True}}


def test_existing_arms_keep_their_models_fingerprint_fields():
    u = {"arm": "ccx2", "task": r5.IDS[0], "lead_model": "sonnet", "lead_effort": "medium"}
    assert "daily" not in r5.unit_models(u, {})
    d = r5.unit_models({**u, "arm": "ccx2daily_clean"}, {})
    assert d["daily"] == {"subagent": {"clean": True}, "claude_setting_sources": "user,project,local"}


def test_dry_run_lists_the_daily_arms_and_copies_nothing(homes, tmp_path, capsys):
    rc = r5.main(["run", "--dry-run", "--rounds", "1", "--tasks", r5.IDS[0], "--arms", "ccx2daily,ccx2daily_nomem",
                  "--out", str(tmp_path / "r.jsonl"), "--workdir", str(tmp_path / "w"),
                  "--daily-codex-source", str(homes["codex"]), "--daily-agents-source", str(homes["agents"])])
    out = capsys.readouterr().out
    assert rc == 0 and "daily arms copy memories, AGENTS.md, skills" in out
    assert "ccx2daily_nomem: [subagent] {'codex_memories': False}" in out and "daily baseline" in out
    assert "need --codex-home" in out
    assert not (tmp_path / "w").exists() or not any((tmp_path / "w").rglob(DH.CODEX_DIR))


def test_daily_check_builds_lists_and_removes(homes, capsys):
    rc = r5.main(["daily-check", "--codex-home", str(homes["eval"]), "--daily-codex-source", str(homes["codex"]),
                  "--daily-agents-source", str(homes["agents"])])
    out = capsys.readouterr().out
    assert rc == 0 and "daily-check: ok" in out and SECRET not in out and '"auth": "eval-codex-home"' in out
    assert r5.main(["daily-check", "--codex-home", ""]) == 2
