"""r6a's namecheck arm (scripts/eval/r5.py `ccx2nc`): ccx2 in a unit hub whose tiers.toml sets namecheck = "fail",
and `<arm>@auto` tokens that schedule a per-task lead model beside the fixed one in one invocation. Fake CLIs only."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import pytest  # noqa: E402
import r5  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"
BAD = "def f():\n    return helper_never_imported()\n"


def _fake_env(tmp_path, hub):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CCX_", "CODEX_", "CLAUDE", "FAKE_")) and k != "DSH_SESSION_ID"}
    for var, sub in (("CODEX_HOME", "codex-home"), ("CLAUDE_CONFIG_DIR", "claude-home"), ("DSH_HOME", "dsh")):
        (tmp_path / sub).mkdir(exist_ok=True)
        env[var] = str(tmp_path / sub)
    env.update({"CCX_CODEX_BIN": str(FAKES / "fake_codex.py"), "CCX_CLAUDE_BIN": str(FAKES / "fake_claude.py"),
                "FAKE_LOG": str(tmp_path / "calls.jsonl"), "CCX_AB_RATE": "0", "CCX_NO_BENCH_REFRESH": "1",
                "CCX_NO_QUOTA_PROBE": "1", "CCX_CONFIG": str(tmp_path / "user-config.toml"),
                "PYTHONIOENCODING": "utf-8", "CCX_HUB": str(hub)})
    return env


def _git_repo(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    (d / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run([*g, "add", "a.py"], cwd=d, check=True)
    subprocess.run([*g, "commit", "-qm", "init"], cwd=d, check=True)


def _ccx_write(repo: Path, env: dict) -> str:
    """What a ccx2 lead does, reduced: one write run through ccx with no --namecheck flag (the hub decides)."""
    r = subprocess.run([sys.executable, str(r5.ROOT / "ccx.py"), "run", "--to", "codex", "--model", "gpt-6-luna",
                        "--effort", "low", "--mode", "write", "--no-fallback", "--review", "off", "--no-ab",
                        "add f to a.py"], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                       env={**env, "FAKE_WRITE": f"{repo / 'a.py'}={BAD}"}, timeout=180)
    assert r.returncode in (0, 2), r.stdout + r.stderr
    return json.loads(r.stdout)["run_id"]


def test_the_arm_is_opt_in_and_ccx2_otherwise():
    assert r5.NAMECHECK_ARMS == {"ccx2nc": "fail"}
    assert "ccx2nc" in r5.OPT_IN_ARMS and "ccx2nc" not in r5.ARMS
    assert r5.ARMS == ("self", "builtin", "ccx", "direct")                      # the default schedule stays
    assert "ccx2nc" in r5.CCX_ARMS and "ccx2nc" in r5.PF.CODEX_ARMS
    assert r5.lead_how("ccx2nc", "L") == r5.lead_how("ccx2", "L")              # the same lead, word for word
    assert r5.lead_flags_arm("ccx2nc") == r5.lead_flags_arm("ccx2") == "ccx"
    assert r5.unit_models({"arm": "ccx2nc"}, {})["namecheck"] == "fail"
    assert "namecheck" not in r5.unit_models({"arm": "ccx2"}, {})
    assert r5.arm_of({"arm": "ccx2nc"}) == "ccx2nc" and r5.unit_key({"round": 1, "task": "t", "arm": "ccx2nc"}) \
        == "1-t-ccx2nc"
    # ccx's own default is untouched
    import tomllib
    with open(r5.ROOT / "config" / "tiers.toml", "rb") as f:
        assert tomllib.load(f)["defaults"]["namecheck"] == "warn"


def test_set_namecheck_writes_the_hub_tiers_and_asserts_it(tmp_path):
    hub = tmp_path / "hub"
    r5.r2.make_hub(hub)
    assert r5.hub_namecheck(hub) == "warn"                                       # as shipped
    assert r5.set_namecheck(hub, "fail") == "fail" and r5.hub_namecheck(hub) == "fail"
    assert r5.set_namecheck(hub, "fail") == "fail"                               # again: still one key
    import tomllib
    text = (hub / "ccx" / "tiers.toml").read_text(encoding="utf-8")
    d = tomllib.loads(text)["defaults"]
    assert d["namecheck"] == "fail" and d["ab_self_rate"] == 0.0 and d["max_parallel"] == 10   # the rest kept
    bare = tmp_path / "bare"
    assert r5.set_namecheck(bare, "fail") == "fail"                              # no tiers.toml yet: written
    (bare / "ccx" / "settings.toml").write_text('[defaults]\nnamecheck = "off"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="runs namecheck 'off'"):              # anything overriding it: refused
        r5.set_namecheck(bare, "fail")


def test_a_ccx2nc_unit_runs_ccx_with_namecheck_fail(tmp_path, monkeypatch):
    """run_unit end to end with fakes: the unit hub is set before the lead starts, ccx's run in it (no flag) fails
    on the undefined name, and the row records the hub's mode and the run's own; a ccx2 unit runs warn."""
    seen = {}

    def lead(u, a, work, repo, hub, iso=None, env=None, job=None):
        seen[u["arm"]] = r5.hub_namecheck(hub)                                   # what the lead's ccx would get
        rid = _ccx_write(repo, _fake_env(tmp_path, hub))
        return {"rc": 0, "wall_s": 1.0, "usd": 0.0, "ccx_run_ids": [rid]}

    monkeypatch.setattr(r5, "by_id", lambda i: {"id": i, "brief": "add f"})
    monkeypatch.setattr(r5, "make_repo", lambda task, repo, **kw: _git_repo(repo))
    monkeypatch.setattr(r5.r3, "make_hub", lambda hub: r5.r2.make_hub(hub))
    monkeypatch.setattr(r5, "lead_unit", lead)
    monkeypatch.setattr(r5, "score", lambda *a, **k: {"ok": True, "pytest": "1 passed"})
    monkeypatch.setattr(r5, "ccx_verify", lambda *a, **k: None)
    monkeypatch.setattr(r5, "archive_hub", lambda *a, **k: [])
    monkeypatch.setattr(r5, "must_telemetry", lambda *a, **k: None)
    monkeypatch.setattr(r5.PF, "snapshot", lambda: None)
    monkeypatch.setattr(r5.PF, "prepare", lambda iso: {})
    monkeypatch.setattr(r5.PF, "audit", lambda iso, text: {"clean": True, "session_ids": []})
    monkeypatch.setattr(r5.PF, "after_unit", lambda *a, **k: {})

    class A:
        claude_isolation, codex_home, dsh_home = "flags", None, "unit"
    work = tmp_path / "work"
    work.mkdir()
    rows = {arm: r5.run_unit({"round": 1, "task": "t", "arm": arm, "label": "l"}, A, work)
            for arm in ("ccx2nc", "ccx2")}
    assert "error" not in rows["ccx2nc"] and "error" not in rows["ccx2"], rows
    assert seen == {"ccx2nc": "fail", "ccx2": "warn"}
    nc, base = rows["ccx2nc"], rows["ccx2"]
    assert nc["namecheck_mode"] == nc["hub"]["namecheck"] == "fail"
    assert base["namecheck_mode"] == base["hub"]["namecheck"] == "warn"
    assert [(x["mode"], x["hits"]) for x in nc["ccx_namecheck"]] == [("fail", 1)]
    assert [(x["mode"], x["hits"]) for x in base["ccx_namecheck"]] == [("warn", 1)]
    assert nc["ccx_check_passed"] is False and not base.get("ccx_check_passed")   # fail: the hit failed the run
    rec = r5.r2.record(work / "h-1-t-ccx2nc", nc["ccx_run_ids"][0])
    assert rec["kind"] == "check_failed" and rec["check"]["reason"] == "namecheck"


def test_r6a_schedules_all_three_arms_interleaved_in_one_invocation(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(r5, "auto_lead", lambda task: {"lead_model": "opus", "lead_pick": "auto", "lead_b": 5.0,
                                                       "lead_band": "hard", "lead_b_from": "ref band large"})
    f = tmp_path / "res.jsonl"
    a = r5.parser().parse_args(["run", "--rounds", "1", "--arms", "ccx2,ccx2nc,ccx2@auto", "--tag", "r6a",
                                "--out", str(f), "--dry-run", "--workdir", str(tmp_path / "w")])
    assert r5.cmd_run(a) == 0
    out = capsys.readouterr().out
    assert f"units: {3 * len(r5.IDS)}" in out
    labels = [ln.split()[1] for ln in out.splitlines() if ln.startswith("[dry] eval-r5:r6a:")]
    arms = [x.rsplit(":", 1)[1] for x in labels]
    assert sorted(set(arms)) == ["ccx2", "ccx2@auto-medium", "ccx2nc"]
    # interleaved: each task's three arms one after another, in a shuffled order that is not always the same
    tasks = [x.split(":")[3] for x in labels]
    assert all(len(set(tasks[i:i + 3])) == 1 and len(set(arms[i:i + 3])) == 3 for i in range(0, len(arms), 3))
    assert len({tuple(arms[i:i + 3]) for i in range(0, len(arms), 3)}) > 1
    assert "lead auto picks: opus x10" in out
    # its units are done-keyed as before: a row of each arm counts as done in the next invocation
    from common import append_jsonl
    t0 = r5.IDS[0]
    append_jsonl(f, {"tag": "r6a", "round": 1, "task": t0, "arm": "ccx2nc", "lead_model": "sonnet",
                     "lead_effort": "medium"})
    append_jsonl(f, {"tag": "r6a", "round": 1, "task": t0, "arm": "ccx2", "lead_model": "opus",
                     "lead_effort": "medium", "lead_pick": "auto"})
    assert r5.cmd_run(a) == 0
    out = capsys.readouterr().out
    assert f"units: {3 * len(r5.IDS) - 2}" in out
    assert f":{t0}:ccx2nc " not in out and f":{t0}:ccx2@auto-medium " not in out and f":{t0}:ccx2 " in out


def test_arm_tokens_are_checked():
    assert r5.arm_tokens(["ccx2", "ccx2nc", "ccx2@auto"]) == ["ccx2", "ccx2nc"]
    for bad, msg in ((["ccx2@opus"], "unknown arm"), (["nope"], "unknown arm"), (["direct@auto"], "no lead"),
                     (["ccx2", "ccx2"], "named twice")):
        with pytest.raises(SystemExit, match=msg):
            r5.arm_tokens(bad)
    with pytest.raises(SystemExit, match="already auto"):
        r5.arm_tokens(["ccx2@auto"], "auto")


def test_old_rows_keep_their_arms_and_keys():
    old = {"tag": "r5h", "round": 1, "task": "x", "arm": "ccx2"}
    assert r5.arm_of(old) == "ccx2" and r5.done_key(old) == ("r5h", 1, "x", "ccx2", "sonnet", "medium")
    auto = {**old, "lead_model": "opus", "lead_effort": "medium", "lead_pick": "auto"}
    assert r5.arm_of(auto) == "ccx2@auto-medium"
    s = r5.summarize([{**old, "ok": True, "usd": 0.1, "wall_s": 10, "env_clean": True},
                      {**old, "arm": "ccx2nc", "ok": True, "usd": 0.1, "wall_s": 10, "env_clean": True,
                       "namecheck_mode": "fail"}])
    assert s["arms"]["ccx2"]["n"] == 1 and s["arms"]["ccx2nc"]["n"] == 1 and "ccx2 vs ccx2nc" in s["paired"]


def test_the_summary_counts_namecheck_per_arm():
    rows = [{"tag": "r6a", "round": 1, "task": "a", "arm": "ccx2nc", "ok": False, "usd": 0.1, "wall_s": 10,
             "env_clean": True, "namecheck_mode": "fail", "ccx_namecheck": [{"mode": "fail", "hits": 2},
                                                                           {"mode": "fail", "hits": 0}]},
            {"tag": "r6a", "round": 1, "task": "a", "arm": "ccx2", "ok": True, "usd": 0.1, "wall_s": 10,
             "env_clean": True, "namecheck_mode": "warn", "ccx_namecheck": [{"mode": "warn", "hits": 1}]},
            {"tag": "r5h", "round": 1, "task": "a", "arm": "ccx", "ok": True, "usd": 0.1, "wall_s": 10,
             "env_clean": True}]
    s = r5.summarize(rows)["arms"]
    assert s["ccx2nc"]["namecheck"] == {"modes": {"fail": 1}, "runs": 2, "runs_with_hits": 1, "runs_failed_by_it": 1}
    assert s["ccx2"]["namecheck"] == {"modes": {"warn": 1}, "runs": 1, "runs_with_hits": 1, "runs_failed_by_it": 0}
    assert "namecheck" not in s["ccx"]                                           # an old row: nothing to say
