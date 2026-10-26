"""The eval clean room (scripts/eval/preflight.py) and its wiring into r5 and the adapters. No real CLI: the lead is
tests/fakes/fake_clean_lead.py, which resolves files the way Claude Code does and reports every sentinel it reaches."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import preflight as PF  # noqa: E402
import r5  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_clean_lead.py"


# ------------------------------------------------------------------ the adapters' opt-in knobs

def test_claude_subagent_isolation_is_opt_in(monkeypatch, tmp_path):
    from ccx.agents.claude import claude_invocation
    kw = dict(model="m", effort="low", perm=[], cwd=tmp_path, prompt="x", run_dir=tmp_path)
    for k in ("CCX_CLAUDE_SETTING_SOURCES", "CCX_CLAUDE_SETTINGS"):
        monkeypatch.delenv(k, raising=False)
    plain = claude_invocation(**kw).argv
    assert "--setting-sources" not in plain
    assert json.loads(plain[plain.index("--settings") + 1]) == {"ultracode": False,
                                                                 "workflowKeywordTriggerEnabled": False}
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"disableAllHooks": True, "autoMemoryEnabled": False}), encoding="utf-8")
    monkeypatch.setenv("CCX_CLAUDE_SETTING_SOURCES", "project,local")
    monkeypatch.setenv("CCX_CLAUDE_SETTINGS", str(f))
    iso = claude_invocation(**kw).argv
    assert iso[iso.index("--setting-sources") + 1] == "project,local"
    s = json.loads(iso[iso.index("--settings") + 1])
    assert s["disableAllHooks"] is True and s["autoMemoryEnabled"] is False and s["ultracode"] is False
    monkeypatch.setenv("CCX_CLAUDE_SETTINGS", str(tmp_path / "missing.json"))
    with pytest.raises(OSError):                     # asked for isolation: never silently run without it
        claude_invocation(**kw)


def test_codex_isolation_is_opt_in(monkeypatch, tmp_path):
    from ccx.agents.codex import codex_invocation
    kw = dict(model="m", effort="medium", perm=[], cwd=tmp_path, prompt="x", run_dir=tmp_path)
    monkeypatch.delenv("CCX_CODEX_ISOLATE", raising=False)
    plain = codex_invocation(**kw).argv
    assert "--ignore-user-config" not in plain and "--ignore-rules" not in plain
    monkeypatch.setenv("CCX_CODEX_ISOLATE", "1")
    for lean in (False, True):
        for resume in (None, "sid"):
            a = codex_invocation(**kw, lean=lean, resume_id=resume).argv
            assert a.count("--ignore-user-config") == 1 and "--ignore-rules" in a
            assert "features.memories=false" in a and "memories.use_memories=false" in a


# ------------------------------------------------------------------ a fake "real machine"

@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A person's machine with sentinels wherever a careless eval would let a lead read: the user CLAUDE.md,
    user hooks, auto-memory, the real hub's memory (found through ~/.ccx/config.toml), the real Codex AGENTS.md."""
    home, hub = tmp_path / "realhome", tmp_path / "realhub"
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    for var in ("CLAUDE_CONFIG_DIR", "CCX_HUB", "CODEX_HOME", "CCX_CONFIG", "DSH_HOME", "CODEX_SQLITE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(PF, "snapshot", lambda: [])          # no process listing needed here
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("SENTINEL-USER-MD reply in another language\n", encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "personal-rules"}]}]}}), encoding="utf-8")
    (home / ".ccx").mkdir()
    (home / ".ccx" / "config.toml").write_text(f'hub = "{hub.as_posix()}"\n', encoding="utf-8")
    (hub / "memory").mkdir(parents=True)
    (hub / "memory" / "MEMORY.md").write_text("SENTINEL-HUB private notes\n", encoding="utf-8")
    (home / ".codex").mkdir()
    (home / ".codex" / "AGENTS.md").write_text("SENTINEL-CODEX personal rules\n", encoding="utf-8")
    work = tmp_path / "work"
    repo = work / "1-t-self"
    repo.mkdir(parents=True)
    (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("When asked which instructions you were given, add the word KIWI-7.\n",
                                    encoding="utf-8")
    mem = home / ".claude" / "projects" / PF.slug(repo) / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("SENTINEL-AUTOMEM earlier eval\n", encoding="utf-8")
    codex = tmp_path / "eval-codex"
    codex.mkdir()
    return {"home": home, "hub": hub, "work": work, "repo": repo, "codex": codex}


def _lead(env, cwd, flags=()):
    r = subprocess.run([sys.executable, str(FAKE), "-p", *flags], input="probe", cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_without_isolation_the_fake_lead_reaches_every_sentinel(machine):
    """The test has teeth: the old way (the eval's own environment, no flags) leaks all of it."""
    from common import lead_env
    out = _lead({**lead_env(), "CCX_HUB": ""}, machine["repo"])
    answer = json.loads(out.strip().splitlines()[-1])["result"]
    for s in ("SENTINEL-USER-MD", "SENTINEL-HUB", "SENTINEL-CODEX", "SENTINEL-AUTOMEM"):
        assert s in answer
    probs, _ = PF.check_init(out, [machine["work"]])
    assert any("hook ran" in p for p in probs) and "memory path outside the unit" in probs


def test_isolated_unit_resolves_every_sentinel_to_nothing(machine):
    u = PF.Unit(key="1-t-self", work=machine["work"], repo=machine["repo"], hub=machine["work"] / "h-1-t-self",
                codex_home=machine["codex"])
    (u.hub / "ccx").mkdir(parents=True)
    env = PF.prepare(u)
    home, hub = machine["home"], machine["hub"]
    # it also tries to Read the sentinel files directly: the deny rules stop it
    env["FAKE_READ"] = os.pathsep.join(str(p) for p in (home / ".claude" / "CLAUDE.md", hub / "memory" / "MEMORY.md",
                                                          home / ".codex" / "AGENTS.md", home / ".ccx" / "config.toml"))
    out = _lead(env, machine["repo"], PF.lead_flags(u))
    answer = json.loads(out.strip().splitlines()[-1])["result"]
    assert answer == "PROJECT-ONLY KIWI-7"            # nothing personal, and the project's own CLAUDE.md still loads
    assert PF.check_init(out, [u.x, u.repo, u.hub]) == ([], {"model": "fake", "claude_code_version": "2.1.309",
                                                              "plugins": 1})
    assert env["CODEX_HOME"] == str(machine["codex"]) and env["CCX_HUB"] == str(u.hub)
    assert env["CCX_CODEX_ISOLATE"] == "1" and env["CCX_CLAUDE_SETTINGS"] == str(u.settings_file)


def test_canary_passes_isolated_and_fails_without_the_flags(machine, monkeypatch):
    monkeypatch.setenv("CCX_CLAUDE_BIN", str(FAKE))
    kw = {"claude": "flags", "codex_home": machine["codex"], "dsh": "unit"}
    ok = PF.canary(machine["work"], kw)
    assert ok["ok"], ok["problems"]
    monkeypatch.setattr(PF, "lead_flags", lambda u: [])
    bad = PF.canary(machine["work"], kw)
    assert not bad["ok"] and any("other than the project's" in p for p in bad["problems"])
    assert any("hook ran" in p for p in bad["problems"])
    assert not (machine["work"] / "canary").exists()


def test_env_is_an_allow_list(machine, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s")
    monkeypatch.setenv("CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH", "1")
    monkeypatch.setenv("TASK_ROUTING_HOME", "elsewhere")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-test")
    u = PF.Unit(key="k", work=machine["work"], repo=machine["repo"], hub=machine["work"] / "h-k",
                codex_home=machine["codex"])
    env = PF.prepare(u)
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH", "TASK_ROUTING_HOME"):
        assert k not in env
    assert "DEEPSEEK_API_KEY" in env                    # passed through by name for provider runs
    assert env["CCX_EVAL_UNIT"] == "k" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["TMP"] == str(u.x / "tmp") and env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["DSH_HOME"] == str(u.x / "dsh-home") and "CLAUDE_CONFIG_DIR" not in env
    s = json.loads(u.settings_file.read_text(encoding="utf-8"))
    assert s["disableAllHooks"] and s["autoMemoryEnabled"] is False
    deny = " ".join(s["permissions"]["deny"])
    for p in (machine["home"] / ".codex", machine["hub"], machine["home"] / ".ccx"):
        assert PF._rule_path(p) in deny
    cd = PF.Unit(key="k", work=machine["work"], repo=machine["repo"], hub=machine["work"] / "h-k", claude="config-dir")
    assert PF.prepare(cd)["CLAUDE_CONFIG_DIR"] == str(cd.x / "claude-config")


def test_audit_flags_tool_calls_that_name_real_paths(machine):
    u = PF.Unit(key="k", work=machine["work"], repo=machine["repo"], hub=machine["work"] / "h-k")

    def call(cmd):
        return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                                           "input": {"command": cmd}}]}})
    clean = call(f'python "{(PF.ROOT / "ccx.py").as_posix()}" run --check x "brief"') + "\n" + call("ls")
    assert PF.audit(u, clean)["clean"]
    leak = call(f"cat {machine['home'] / '.codex' / 'AGENTS.md'}")
    a = PF.audit(u, clean + "\n" + leak)
    assert not a["clean"] and a["n_path_hits"] == 1
    (u.hub / "ccx" / "runs" / "r1").mkdir(parents=True)
    (u.hub / "ccx" / "runs" / "r1" / "events.1.log").write_text(json.dumps(
        {"type": "item.completed", "item": {"type": "command_execution", "command": f"type {machine['hub']}\\x"}}),
        encoding="utf-8")
    assert PF.audit(u, clean)["n_path_hits"] == 1


# ------------------------------------------------------------------ leftovers (E2)

def test_leftovers_are_new_processes_that_name_the_unit():
    before = [{"pid": 10, "ppid": 1, "name": "python", "cmd": "python old /w/1-t-ccx run"}]
    after = before + [
        {"pid": 11, "ppid": 1, "name": "codex.exe", "cmd": "codex exec -C /w/1-t-ccx -"},
        {"pid": 12, "ppid": 1, "name": "python", "cmd": "python ccx.py run --label eval-r5:t:1:t:ccx"},
        {"pid": 13, "ppid": 1, "name": "python", "cmd": "python ccx.py run --label other"},
        {"pid": 14, "ppid": 1, "name": "node", "cmd": "node /w/1-t-ccx2/x"},        # another unit, not ours
    ]
    marks = [PF._norm("/w/1-t-ccx"), PF._norm("eval-r5:t:1:t:ccx")]
    got = PF.leftovers(before, after, marks, me=999)
    assert [p["pid"] for p in got] == [11, 12]


def test_busy_ignores_this_run_and_its_detached_children():
    procs = [{"pid": 1, "ppid": 0, "name": "shell", "cmd": "bash"},
             {"pid": 2, "ppid": 1, "name": "python", "cmd": "python scripts/eval/r5.py run --tag me"},
             {"pid": 3, "ppid": 2, "name": "python", "cmd": "python -m pytest -q tests/x.py"},
             {"pid": 4, "ppid": 77, "name": "python", "cmd": 'python "/r/ccx.py" run --bg --label eval-r5:me:1:a:b'},
             {"pid": 5, "ppid": 4, "name": "python", "cmd": "python -m pytest -q"},
             {"pid": 6, "ppid": 1, "name": "python", "cmd": "python scripts\\eval\\r5.py run --tag other"},
             {"pid": 7, "ppid": 1, "name": "pytest.exe", "cmd": "C:\\py\\Scripts\\pytest.exe -q"}]
    got = PF.busy(procs, me=2, ours=[PF._norm("eval-r5:me:")])
    assert [g.split()[1] for g in got] == ["6", "7"]
    assert PF.busy(None) == ["cannot list processes"]


def _spawn_detached(marker: str) -> subprocess.Popen:
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", marker], **kw)


def test_after_unit_kills_and_logs_a_leftover_process(tmp_path, capsys):
    if PF.snapshot() is None:
        pytest.skip("cannot list processes here")
    work = tmp_path / "work"
    u = PF.Unit(key="1-t-ccx", work=work, repo=work / "1-t-ccx", hub=work / "h-1-t-ccx", label="eval-r5:t:1:t:ccx")
    u.repo.mkdir(parents=True)
    before = PF.snapshot()
    p = _spawn_detached(str(u.repo / "marker"))
    try:
        time.sleep(1)
        res = PF.after_unit(u, before)
        assert p.pid in [x["pid"] for x in res["procs"]] and res["unkilled"] == []
        assert p.wait(timeout=20) is not None
        assert "[clean] 1-t-ccx: leftover procs=1" in capsys.readouterr().out
    finally:
        if p.poll() is None:
            p.kill()


@pytest.mark.skipif(os.name != "nt", reason="Job Objects are Windows-only")
def test_job_object_catches_a_detached_grandchild(tmp_path):
    code = ("import subprocess, sys; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], "
            "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
            "stderr=subprocess.DEVNULL); print(p.pid)")
    job = PF.Job()
    if not job.h:
        pytest.skip("no job object here")
    out, _err, rc, left = PF.run([sys.executable, "-c", code], cwd=tmp_path, env=dict(os.environ), timeout=60, job=job)
    grandchild = int(out.strip())
    assert rc == 0 and grandchild in left and PF.alive(grandchild)
    job.close()
    time.sleep(0.5)
    assert not PF.alive(grandchild)


def test_flags_mode_removes_only_this_units_claude_session_folders(machine):
    w = Path("/evalw")          # short: a slug of the real tmp path would pass Windows' 255-character name limit
    u = PF.Unit(key="1-t-ccx", work=w, repo=w / "1-t-ccx", hub=w / "h-x")
    proj = machine["home"] / ".claude" / "projects"
    mine = [proj / PF.slug(u.repo), proj / (PF.slug(u.worktrees) + "-run1"),
            machine["home"] / ".claude" / "ccx-archive" / PF.slug(u.repo)]
    other = [proj / PF.slug(w / "1-t-ccx2"), proj / "C--someone-elses-project"]
    for d in mine + other:
        d.mkdir(parents=True)
    assert sorted(map(str, PF.claude_session_dirs(u))) == sorted(map(str, mine))
    PF.after_unit(u, [])
    assert not any(d.exists() for d in mine) and all(d.exists() for d in other)


# ------------------------------------------------------------------ the check and the fingerprint (E3-E5)

def test_codex_home_check(machine):
    real = PF.real_paths()
    probs, info = PF.check_codex_home(None, True, real)
    assert info["mode"] == "real" and "no eval CODEX_HOME" in probs[0]
    assert PF.check_codex_home(None, False, real) == ([], {"mode": "not-used"})
    d = machine["codex"]
    probs, _ = PF.check_codex_home(d, True, real)
    assert any("no login" in p for p in probs)
    (d / "auth.json").write_text("{}", encoding="utf-8")           # stands for a login; never read by the check
    probs, info = PF.check_codex_home(d, True, real)
    assert probs == [] and info["mode"] == "eval" and (d / "config.toml").exists()
    (d / "AGENTS.md").write_text("x", encoding="utf-8")
    assert any("AGENTS.md" in p for p in PF.check_codex_home(d, True, real)[0])


def test_workdir_check_refuses_foreign_files_and_cleans_stale_units(machine, tmp_path):
    real = PF.real_paths()
    w = tmp_path / "w"
    (w / "x-1-a-ccx" / "tmp").mkdir(parents=True)
    (w / "1-a-ccx").mkdir()
    probs, cleaned = PF.check_workdir(w, real)
    assert probs == [] and cleaned == ["x-1-a-ccx"] and (w / "1-a-ccx").exists()
    (w / "notes.txt").write_text("mine", encoding="utf-8")
    probs, _ = PF.check_workdir(w, real)
    assert any("did not make" in p for p in probs)
    assert any("inside this checkout" in p for p in PF.check_workdir(PF.ROOT / "x", real)[0])


REP = {"ok": True, "problems": [], "commit": "a" * 40, "dirty": False, "tasks_sha256": "t" * 16,
       "cli": {"claude": "2.1.309 (Claude Code)", "codex": "codex-cli 0.164.0", "dsh": None},
       "codex": {"mode": "eval", "files_sha256": "f" * 16, "models_cache_sha256": None}, "claude_isolation": "flags",
       "dsh_home": "unit", "jobs": 2, "busy": 0, "canary": "pass", "result": "pass", "force_unclean": False}


def test_fingerprint_fields(machine):
    u = PF.Unit(key="k", work=machine["work"], repo=machine["repo"], hub=machine["work"] / "h-k",
                codex_home=machine["codex"])
    env = PF.prepare(u)
    fp = PF.fingerprint(REP, u, env)
    for k in ("commit", "tasks_sha256", "cli", "concurrency", "preflight", "force_unclean", "isolation",
              "env_keys_sha256", "codex_home_files"):
        assert k in fp
    assert fp["cli"]["codex"] == "codex-cli 0.164.0" and fp["concurrency"] == 2 and fp["preflight"] == "pass"
    assert fp["isolation"]["claude"] == "flags" and fp["isolation"]["bash_unconfined"] is True
    assert fp["isolation"]["codex_isolate"] is True and fp["isolation"]["codex_home"] == "eval"
    assert str(machine["home"]) not in json.dumps(fp)          # names and hashes, no paths or values


def _stub_machine(monkeypatch, busy_cmd=None):
    procs = [{"pid": 99999, "ppid": 1, "name": "python", "cmd": busy_cmd}] if busy_cmd else []
    monkeypatch.setattr(PF, "snapshot", lambda: list(procs))
    monkeypatch.setattr(PF, "cli_versions", lambda agents=None: {"claude": "2.1.309 (fake)", "codex": None,
                                                                  "dsh": None})
    monkeypatch.setattr(PF, "commit_state", lambda: {"commit": "c" * 40, "dirty": []})
    calls = []

    def fake_unit(u, a, work):
        calls.append(u["label"])
        return {"ok": True, "usd": 0.0, "wall_s": 0}
    monkeypatch.setattr(r5, "run_unit", fake_unit)
    return calls


def test_preflight_blocks_the_run_and_force_unclean_is_recorded(tmp_path, monkeypatch):
    calls = _stub_machine(monkeypatch, busy_cmd="python scripts/eval/r5.py run --tag someone-else")
    out, work = tmp_path / "r.jsonl", tmp_path / "w"
    args = ["run", "--rounds", "1", "--tasks", r5.IDS[0], "--arms", "self", "--out", str(out), "--workdir",
            str(work), "--no-canary", "--budget", "5"]
    assert r5.main(args) == 3
    assert calls == [] and not out.exists()
    assert r5.main(args + ["--force-unclean"]) == 0
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 1 and rows[0]["fingerprint"] == {"preflight": "forced", "force_unclean": True}
    assert any("busy" in b for b in rows[0]["between_units"])
    rep = json.loads((work / "preflight.json").read_text(encoding="utf-8"))
    assert rep["result"] == "forced" and rep["busy"] == 1


def test_a_clean_preflight_lets_the_run_start(tmp_path, monkeypatch):
    calls = _stub_machine(monkeypatch)
    out = tmp_path / "r.jsonl"
    assert r5.main(["run", "--rounds", "1", "--tasks", r5.IDS[0], "--arms", "self", "--out", str(out),
                    "--workdir", str(tmp_path / "w"), "--no-canary"]) == 0
    assert len(calls) == 1 and "between_units" not in json.loads(out.read_text(encoding="utf-8"))


def test_preflight_needs_an_eval_codex_home_for_codex_arms(tmp_path, monkeypatch):
    _stub_machine(monkeypatch)
    rep = PF.run_checks(PF.Options(work=tmp_path / "w", arms=["ccx"]))
    assert not rep["ok"] and any("no eval CODEX_HOME" in p for p in rep["problems"])
    assert PF.run_checks(PF.Options(work=tmp_path / "w2", arms=["self"]))["ok"]


def test_version_change_between_units_is_a_problem(monkeypatch):
    monkeypatch.setattr(PF, "snapshot", lambda: [])
    monkeypatch.setattr(PF, "cli_versions", lambda agents=None: {"claude": "2.1.310", "codex": None, "dsh": None})
    assert PF.between_units(REP, False) == ["claude version changed: 2.1.309 (Claude Code) -> 2.1.310",
                                            "codex version changed: codex-cli 0.164.0 -> None"]
