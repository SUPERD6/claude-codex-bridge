"""External hold-out tasks (scripts/eval/ext_repo.py and its wiring in r5.py / holdout_check.py), on a local fake
upstream repository: no network, no real agent CLI."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import ext_repo  # noqa: E402
import holdout_check  # noqa: E402
import preflight as PF  # noqa: E402
import r5  # noqa: E402
import tasks_holdout  # noqa: E402

CORE_OLD = "def f(x):\n    return x\n"
CORE_NEW = ("def f(x):\n    # 0 for None\n    if x is None:\n        return 0\n    # -x for a negative x\n"
            "    if x < 0:\n        return -x\n    return x\n")                # 6 lines added
TEST_OLD = "from fakepkg.core import f\n\n\ndef test_f():\n    assert f(1) == 1\n"
TEST_NEW = TEST_OLD + "\n\ndef test_none_and_negative():\n    assert f(None) == 0 and f(-2) == 2\n"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c",
                           "core.autocrlf=false", *args], cwd=cwd, capture_output=True, text=True, check=True
                          ).stdout.strip()


def write(root: Path, files: dict):
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.encode("utf-8"))                              # LF on every OS


@pytest.fixture(autouse=True)
def fresh_material():
    """r5 keeps each external task's material for the whole process: every test reads its own fake upstream."""
    r5._EXT.clear()
    yield
    r5._EXT.clear()


@pytest.fixture()
def upstream(tmp_path):
    """source/fakepkg: start -> fix (the task commit, with its test) -> a later commit and a tag (the future)."""
    src = tmp_path / "source" / "fakepkg"
    src.mkdir(parents=True)
    git(src, "init", "-q")
    write(src, {".gitignore": "src/*/_version.py\n", "pyproject.toml": "[project]\nname = 'fakepkg'\n",
                "src/fakepkg/__init__.py": "from ._version import __version__\n",
                "src/fakepkg/core.py": CORE_OLD, "tests/test_core.py": TEST_OLD})
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "start")
    start = git(src, "rev-parse", "HEAD")
    write(src, {"src/fakepkg/core.py": CORE_NEW, "tests/test_core.py": TEST_NEW,
                "CHANGES.rst": "fixed f\n"})
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "fix f")
    fix = git(src, "rev-parse", "HEAD")
    write(src, {"src/fakepkg/later.py": "LATER = 1\n"})
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "later work")
    git(src, "tag", "v9")
    spec = {"url": "https://example.invalid/fakepkg.git", "name": "fakepkg, a fake library", "pythonpath": "src",
            "stubs": ["src/fakepkg/_version.py"], "needs": ["pytest"]}
    task = {"id": "fake-f", "repo": "fakepkg", "commit": fix, "tests": ["tests/test_core.py"], "area": "fake: f",
            "size": 6, "files": 1, "brief": "f should handle None and negative numbers."}
    return {"src": src, "source": tmp_path / "source", "start": start, "fix": fix, "spec": spec, "task": task}


@pytest.fixture()
def registered(upstream, monkeypatch):
    """The fake repository and task known to r5 (as tasks_holdout's are)."""
    monkeypatch.setitem(tasks_holdout.REPOS, "fakepkg", upstream["spec"])
    return upstream


def test_fetch_clones_once_from_the_local_copy(upstream, tmp_path):
    cache = tmp_path / "work" / "ext-cache"
    repo = ext_repo.fetch("fakepkg", upstream["spec"], cache, upstream["source"])
    assert repo == cache / "fakepkg.git" and (repo / "HEAD").exists()
    assert git(repo, "rev-parse", upstream["fix"]) == upstream["fix"]
    import shutil
    shutil.rmtree(upstream["source"], ignore_errors=True)                 # a second fetch reuses the clone
    assert ext_repo.fetch("fakepkg", upstream["spec"], cache, upstream["source"]) == repo
    with pytest.raises(FileNotFoundError):
        ext_repo.fetch("other", upstream["spec"], cache, tmp_path / "nowhere")


def test_pin_wants_the_full_sha_of_a_commit_with_one_parent(upstream, tmp_path):
    repo = ext_repo.fetch("fakepkg", upstream["spec"], tmp_path / "c", upstream["source"])
    assert ext_repo.pin(repo, upstream["fix"]) == upstream["start"]
    with pytest.raises(ValueError):
        ext_repo.pin(repo, upstream["fix"][:10])
    with pytest.raises((LookupError, RuntimeError)):
        ext_repo.pin(repo, "0" * 40)
    with pytest.raises(ValueError):                                      # the root commit has no parent
        ext_repo.pin(repo, upstream["start"])


def test_parent_repo_shows_no_future(upstream, tmp_path):
    repo = ext_repo.fetch("fakepkg", upstream["spec"], tmp_path / "c", upstream["source"])
    dest = tmp_path / "unit"
    info = ext_repo.make_parent_repo(repo, upstream["fix"], upstream["spec"], dest)
    assert info == {"parent": upstream["start"], "stubs": ["src/fakepkg/_version.py"]}
    assert git(dest, "rev-list", "--all", "--count") == "1"               # one commit, nothing reachable after it
    assert git(dest, "remote") == "" and git(dest, "tag") == "" and git(dest, "stash", "list") == ""
    assert git(dest, "for-each-ref", "--format=%(refname)").splitlines() in (["refs/heads/master"],
                                                                            ["refs/heads/main"])
    for sha in (upstream["fix"], upstream["start"]):                        # not even the parent's own object
        assert subprocess.run(["git", "cat-file", "-e", sha], cwd=dest, capture_output=True).returncode != 0
    assert (dest / "src/fakepkg/core.py").read_text(encoding="utf-8") == CORE_OLD
    assert (dest / "tests/test_core.py").read_text(encoding="utf-8") == TEST_OLD
    assert not (dest / "CHANGES.rst").exists() and not (dest / "src/fakepkg/later.py").exists()
    assert "src/fakepkg/_version.py" in git(dest, "ls-files").splitlines()   # git-ignored upstream, committed here
    assert git(dest, "status", "--porcelain") == ""


def test_hidden_tests_and_reference_size(upstream, tmp_path):
    repo = ext_repo.fetch("fakepkg", upstream["spec"], tmp_path / "c", upstream["source"])
    got = ext_repo.hidden_tests(repo, upstream["fix"], ["tests/test_core.py"])
    assert got == {"tests/test_core.py": TEST_NEW.encode()}
    ch = ext_repo.ref_change(repo, upstream["fix"])
    assert ch == {"size": 6, "files": ["src/fakepkg/core.py"]}             # tests and CHANGES.rst not counted


def test_r5_makes_and_scores_an_external_unit(registered, tmp_path):
    task, work = registered["task"], tmp_path / "work"
    work.mkdir()
    repo = work / "1-fake-f-self"
    r5.make_repo(task, repo, work, registered["source"])
    assert (r5.ext_cache(work) / "fakepkg.git" / "HEAD").exists()
    assert not (repo / "tests" / "conftest.py").exists()                  # nothing of this repository added
    before = r5.score(repo, task, work, source=registered["source"])
    assert not before["ok"] and "failed" in before["pytest"]               # the commit's test on the parent fails
    assert (repo / "tests/test_core.py").read_text(encoding="utf-8") == TEST_NEW
    (repo / "src/fakepkg/core.py").write_text(CORE_NEW, encoding="utf-8")   # a right answer
    (repo / "src/fakepkg/_version.py").unlink()                          # removed by the agent: put back
    after = r5.score(repo, task, work, source=registered["source"])
    assert after["ok"], after


def test_task_env_and_prompt_for_another_repository(registered):
    task = registered["task"]
    env = r5.task_env(task, {"PATH": "p"}, python=str(Path("/py/bin/python")))
    assert env["PYTHONPATH"] == "src" and env["PATH"].startswith(str(Path("/py/bin")))
    assert env["PIP_NO_INDEX"] == "1"                                      # nothing can be fetched or installed
    assert r5.task_env(r5.by_id(r5.IDS[0]), {"PATH": "p"}) == {"PATH": "p"}     # this repository's tasks: as before
    spec = registered["spec"]
    text = r5.LEAD_PROMPT_EXT.format(name=spec["name"], note=r5.ext_note(spec), brief=task["brief"], how="HOW")
    assert "fakepkg, a fake library" in text and task["brief"] in text and "relayline" not in text
    assert "{" not in text and "no package index" in text
    spec["note"] = "Leave tests/test_slow.py out."
    assert "Leave tests/test_slow.py out. Run" in r5.LEAD_PROMPT_EXT.format(name="x", note=r5.ext_note(spec),
                                                                           brief="b", how="h")
    assert "test_benchmarks" in tasks_holdout.REPOS["humanize"]["note"]


def test_the_copies_and_web_are_denied_to_external_units_only(registered, tmp_path, monkeypatch):
    class A:
        claude_isolation, codex_home, dsh_home = "flags", None, "unit"
        ext_cache = str(registered["source"])
    work = tmp_path / "work"
    monkeypatch.setattr(r5, "by_id", lambda i: registered["task"] if i == "fake-f" else r5.tasks_r5.by_id(i))
    u = r5.unit_of({"round": 1, "task": "fake-f", "arm": "self", "label": "l"}, A, work)
    assert r5.ext_cache(work) in PF.forbidden(u) and Path(A.ext_cache) in PF.forbidden(u)
    deny = PF.claude_settings(u)["permissions"]["deny"]
    assert any("ext-cache" in d for d in deny) and "WebFetch" in deny and "WebSearch" in deny
    other = r5.unit_of({"round": 1, "task": r5.IDS[0], "arm": "self", "label": "l"}, A, work)
    assert r5.ext_cache(work) not in PF.forbidden(other)
    assert "WebFetch" not in PF.claude_settings(other)["permissions"]["deny"]
    assert not PF.WORK_ENTRY.match("ext-cache")                          # a leftover clone in the work dir: refused


def test_audit_flags_reaching_for_the_fix(registered, tmp_path, monkeypatch):
    class A:
        claude_isolation, codex_home, dsh_home = "flags", None, "unit"
        ext_cache = str(registered["source"])
    monkeypatch.setattr(r5, "by_id", lambda i: registered["task"] if i == "fake-f" else r5.tasks_r5.by_id(i))
    u = r5.unit_of({"round": 1, "task": "fake-f", "arm": "self", "label": "l"}, A, tmp_path / "work")
    bad = ['{"command": "git -C ../ext-cache/fakepkg.git log"}', '{"command": "pip install fakepkg"}',
           '{"command": "python -m pip download fakepkg"}', '{"command": "ls ../../' + tmp_path.name + '/source"}',
           '{"command": "curl -L https://github.com/x/fakepkg/archive/main.zip"}',
           '{"url": "https://example.invalid/fakepkg"}']
    ok = ['{"command": "python -m pytest -q tests/test_core.py"}', '{"command": "pip list"}']
    hits = PF.path_hits(bad + ok, u)
    assert len(hits) == len(bad), hits
    other = r5.unit_of({"round": 1, "task": r5.IDS[0], "arm": "self", "label": "l"}, A, tmp_path / "work")
    assert PF.path_hits(['{"command": "pip install x"}'], other) == []    # this repository's units: as before


def test_prepare_external_reads_into_memory_and_reports_problems(registered, tmp_path, monkeypatch):
    monkeypatch.setattr(r5, "by_id", lambda i: registered["task"])

    class A:
        ext_cache, ext_python = str(registered["source"]), ""
    todo = [{"task": "fake-f"}]
    work = tmp_path / "w"
    made = []
    real_mkdtemp = r5.tempfile.mkdtemp
    monkeypatch.setattr(r5.tempfile, "mkdtemp", lambda **kw: made.append(real_mkdtemp(**kw)) or made[-1])
    assert r5.prepare_external(todo, A, work) == []
    assert not work.exists() and made and not Path(made[0]).exists()     # the clone was outside the work dir, gone
    m = r5._EXT[r5._ext_key(registered["task"])]
    assert m["parent"] == registered["start"] and "tests/test_core.py" in m["changed"] and len(m["date"]) == 10
    assert A.ext_info["python"] == sys.executable and A.ext_info["pytest"] and A.ext_venv
    registered["spec"]["needs"] = ["pytest", "no_such_module_for_ccx_tests"]
    probs = r5.prepare_external(todo, A, work)
    assert len(probs) == 1 and "no_such_module_for_ccx_tests" in probs[0]
    registered["spec"].update(needs=["pytest"], module="json", pytest_min="999.0")   # the library itself installed
    probs = r5.prepare_external(todo, A, work)
    assert any("json installed" in p for p in probs) and any("999.0" in p for p in probs)
    registered["spec"].pop("module"), registered["spec"].pop("pytest_min")
    A.ext_cache = str(Path(sys.executable).parent / "copies")           # the Python next to the copies: refused
    assert any("--ext-cache" in p and "PATH" in p for p in r5.prepare_external(todo, A, work))
    r5._EXT.clear()
    A.ext_cache = str(tmp_path / "empty")
    probs = r5.prepare_external(todo, A, tmp_path / "w2")
    assert any("fake-f" in p and "FileNotFoundError" in p for p in probs)


def test_a_unit_needs_its_repository_prepared(registered, tmp_path, monkeypatch):
    class A:
        claude_isolation, codex_home, dsh_home = "flags", None, "unit"
        ext_cache, ext_python = str(registered["source"]), ""
    monkeypatch.setattr(r5, "by_id", lambda i: registered["task"])
    monkeypatch.setattr(r5.PF, "snapshot", lambda: None)
    work = tmp_path / "work"
    work.mkdir()
    row = r5.run_unit({"round": 1, "task": "fake-f", "arm": "self", "label": "l"}, A, work)
    assert "not prepared" in row["error"] and not r5.ext_cache(work).exists()


def test_scoring_puts_back_the_test_setup(registered, tmp_path):
    task, work = registered["task"], tmp_path / "work"
    work.mkdir()
    repo = work / "1-fake-f-self"
    r5.make_repo(task, repo, work, registered["source"])
    (repo / "src/fakepkg/core.py").write_text(CORE_NEW, encoding="utf-8")   # a right answer, but the agent also ...
    (repo / "tests/conftest.py").write_text("import pytest\n\n\n@pytest.fixture(autouse=True)\ndef boom():\n"
                                            "    raise RuntimeError('x')\n", encoding="utf-8")
    (repo / "conftest.py").write_text("raise RuntimeError('root')\n", encoding="utf-8")
    (repo / "tests/test_extra.py").write_text("def test_extra():\n    assert False\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-x --no-such-flag'\n",
                                         encoding="utf-8")
    res = r5.score(repo, task, work, source=registered["source"])
    assert res["ok"], res                                                  # none of that applies to the hidden test
    assert not (repo / "conftest.py").exists() and not (repo / "tests/test_extra.py").exists()
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == "[project]\nname = 'fakepkg'\n"
    assert "\x1b" not in res["pytest"]


def test_summary_reports_per_repository():
    rows = [{"arm": "self", "ok": True, "task": "a", "ext": {"repo": "fakepkg", "date": "2018-01-01"}},
            {"arm": "self", "ok": False, "task": "b"}]
    s = r5.summarize(rows)
    assert s["by_repo"] == {"fakepkg": {"self": {"ok": 1, "n": 1}}, "this repository": {"self": {"ok": 0, "n": 1}}}
    assert s["ext_dates"] == {"a": "2018-01-01"}
    assert "by_repo" not in r5.summarize([rows[1]])


def test_holdout_check_handles_external_tasks(registered, tmp_path):
    ctx = holdout_check.Ctx(tmp_path / "chk", str(registered["source"]))
    task = registered["task"]
    assert holdout_check.static(task, [], ctx) == []
    row = holdout_check.check(task, [], tmp_path / "chk", True, ctx)
    assert row["ok"], row
    assert row["size"] == 6 and row["repo"] == "fakepkg" and "failed" in row["parent"]
    bad = {**task, "size": 9}
    assert any("recorded size" in p for p in holdout_check.static(bad, [], ctx))


def test_dry_run_lists_the_external_tasks_without_fetching(tmp_path, capsys):
    rc = r5.main(["run", "--dry-run", "--rounds", "1", "--arms", "self", "--taskset", "holdout",
                  "--out", str(tmp_path / "res.jsonl"), "--workdir", str(tmp_path / "work")])
    out = capsys.readouterr().out
    assert rc == 0 and not (tmp_path / "work" / "ext-cache").exists()
    for t in tasks_holdout.T:
        assert f":{t['id']}:self" in out
