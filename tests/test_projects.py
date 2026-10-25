"""ccx projects: the project catalog, found by code in a fake folder tree (no real CLI, no model)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ccx import projects
from ccx.config import load_config, paths, set_setting

REPO = Path(__file__).resolve().parent.parent


def ccx(*args, cwd=None):
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), *args], capture_output=True, text=True,
                       encoding="utf-8", cwd=cwd)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def git_repo(d: Path, subjects=("first commit",), remote="https://github.com/someone/pet-repo.git"):
    d.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(d), "remote", "add", "origin", remote], check=True)
    for i, s in enumerate(subjects):
        (d / f"f{i}.txt").write_text(s, encoding="utf-8")
        subprocess.run(["git", "-C", str(d), "add", "."], check=True, env=env)
        subprocess.run(["git", "-C", str(d), "commit", "-qm", s], check=True, env=env)


def tree(tmp_path: Path) -> Path:
    """root/
        AGENTS.md                      rules of the whole workspace
        group/  CLAUDE.md              a group: rules only, projects inside
          desk-pet/  (git) README: 桌宠
          notes-site/ package.json
          node_modules/junk/ package.json   skipped
        lab/ (git) AGENTS.md (approval rules), docs/STATUS.md, topics/a-topic, .ccx/journal.jsonl
        plain-readme/ README.md        a README right under the root
        wrapper/ AGENTS.md, shared/source/engine (git)   a project holding its source repo deeper inside
        deep/x/y/z/w/pyproject.toml    deeper than max_depth: not found
    """
    root = tmp_path / "ws"
    (root / "group").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Workspace rules\n\nWhere things go.\n", encoding="utf-8")
    (root / "group" / "CLAUDE.md").write_text("# Group\n\nProjects of the group.\n", encoding="utf-8")
    pet = root / "group" / "desk-pet"
    git_repo(pet, ("add sprites", "fix drag on second screen"))
    (pet / "README.md").write_text("# Desk Pet 桌宠 — a cat on your screen\n\n[![ci](x)](y)\n\n"
                                   "A small **desktop pet** that walks on the taskbar.\nSecond line.\n\n"
                                   "## Install\n\nnope\n", encoding="utf-8")
    site = root / "group" / "notes-site"
    site.mkdir()
    (site / "package.json").write_text(json.dumps({"name": "my-notes", "bin": {"notes": "x.js"}}), encoding="utf-8")
    (site / "node_modules" / "junk").mkdir(parents=True)
    (site / "node_modules" / "junk" / "package.json").write_text("{}", encoding="utf-8")
    lab = root / "lab"
    git_repo(lab, ("stage 2 results",), remote=None)
    (lab / "AGENTS.md").write_text("# Research lab\n\nApproval needed before each stage.\n", encoding="utf-8")
    (lab / "docs").mkdir()
    (lab / "docs" / "STATUS.md").write_text("now", encoding="utf-8")
    (lab / "topics" / "a-topic").mkdir(parents=True)
    (lab / "topics" / "a-topic" / "AGENTS.md").write_text("# not a project\n", encoding="utf-8")
    (lab / ".ccx").mkdir()
    (lab / ".ccx" / "journal.jsonl").write_text(json.dumps({"seq": 1, "text": "ran the ablation"}) + "\n",
                                                encoding="utf-8")
    (root / "plain-readme").mkdir()
    (root / "plain-readme" / "README.md").write_text("Just notes.\n", encoding="utf-8")
    (root / "wrapper" / "shared" / "source").mkdir(parents=True)
    (root / "wrapper" / "AGENTS.md").write_text("# Wrapper\n\n[中文](README.zh.md) | English\n\nThe wrapper.\n",
                                                encoding="utf-8")
    git_repo(root / "wrapper" / "shared" / "source" / "engine", remote=None)
    (root / "wrapper" / "ui").mkdir()                       # a project right inside, but wrapper has work of its own
    (root / "wrapper" / "ui" / "AGENTS.md").write_text("# UI\n", encoding="utf-8")
    (root / "wrapper" / ".ccx").mkdir()
    fish = root / "fish"                                    # no README on top; one in pet/
    git_repo(fish, ("基线：桌面伙伴",), remote=None)
    (fish / "pet").mkdir()
    (fish / "pet" / "README.md").write_text("# 大鱼 · 桌面伙伴\n\nA whale on the desktop.\n", encoding="utf-8")
    deep = root / "deep" / "x" / "y" / "z" / "v" / "w"
    deep.mkdir(parents=True)
    (deep / "pyproject.toml").write_text('name = "deep"\n', encoding="utf-8")
    return root


def by_name(cat):
    return {e["name"]: e for e in cat["projects"]}


def test_scan_finds_projects_groups_and_skips(tmp_path):
    root = tree(tmp_path)
    cat = projects.scan([str(root)])
    got = by_name(cat)
    assert set(got) == {"desk-pet", "notes-site", "lab", "plain-readme", "wrapper", "engine", "ui", "fish"}   # no group, junk, deep
    assert got["engine"]["parent"] == "wrapper" and got["engine"]["rules"] == [str(root / "wrapper" / "AGENTS.md"),
                                                                                str(root / "AGENTS.md")]
    assert got["wrapper"]["summary"] == "The wrapper." and got["ui"]["parent"] == "wrapper"
    assert got["fish"]["keywords"] == ["大鱼 · 桌面伙伴"] and got["fish"]["summary"] == "A whale on the desktop."
    pet = got["desk-pet"]
    assert pet["summary"] == "A small desktop pet that walks on the taskbar. Second line."
    assert {"desk-pet", "Desk Pet 桌宠", "桌宠", "pet-repo"} <= set(pet["aliases"])
    assert pet["recent"][0] == "fix drag on second screen" and pet["git"]
    assert pet["rules"] == [str(root / "group" / "CLAUDE.md"), str(root / "AGENTS.md")]   # inherited, nearest first
    assert {"my-notes", "notes"} <= set(got["notes-site"]["aliases"])
    lab = got["lab"]
    assert lab["rules"][0] == str(root / "lab" / "AGENTS.md")
    assert "docs/STATUS.md" in lab["state"] and "topics/" in lab["state"] and lab["topics"] == ["a-topic"]
    assert lab["journal"] == ["ran the ablation"]
    assert all(e["last_active"] > 0 for e in cat["projects"])


def test_a_link_to_a_seen_folder_is_recorded_once(tmp_path):
    root = tree(tmp_path)
    link = root / "pet-link"
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(root / "group" / "desk-pet")],
                           check=True, capture_output=True)
        else:
            link.symlink_to(root / "group" / "desk-pet", target_is_directory=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("cannot make a link here")
    cat = projects.scan([str(root)])
    pets = [e for e in cat["projects"] if e["path"].endswith("desk-pet")]
    assert len(pets) == 1 and pets[0]["also_at"] == [str(link)]
    assert "pet-link" not in by_name(cat)


def test_same_folder_name_twice_gets_parent_prefix(tmp_path):
    for parent in ("a", "b"):
        d = tmp_path / "ws" / parent / "tool"
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text('name = "x"\n', encoding="utf-8")
    names = set(by_name(projects.scan([str(tmp_path / "ws")])))
    assert names == {"a/tool", "b/tool"}


def test_summary_skips_badges_code_and_imports():
    t, s = projects.title_and_summary("@AGENTS.md\n\n# T\n\n```\ncode\n```\n<p>x</p>\n\nReal text [link](u).\n")
    assert (t, s) == ("T", "Real text link.")


def test_roots_setting_and_commands(tmp_path):
    root = tree(tmp_path)
    p = paths()
    assert ccx("projects")["projects"] == []                      # no catalog yet: says how to make one
    set_setting(p, "projects.roots", f"{root};{tmp_path / 'nope'}")
    assert projects.configured_roots(load_config(p)) == [str(root), str(tmp_path / "nope")]
    out = ccx("projects", "scan")
    assert out["projects"] == 8 and out["missing_roots"] == [str(tmp_path / "nope")]
    assert Path(out["catalog"]).parent == p.state
    rows = ccx("projects")["projects"]
    assert {r["name"] for r in rows} == {"desk-pet", "notes-site", "lab", "plain-readme", "wrapper", "engine", "ui", "fish"}
    assert ccx("projects", "show", "桌宠")["name"] == "desk-pet"      # an alias works as a name
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), "projects", "show", "nothing"], capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 3 and "no project named" in r.stdout


def test_scan_without_roots_says_how(tmp_path):
    with pytest.raises(ValueError, match="projects.roots"):
        projects.refresh(paths(), load_config(paths()))


# ---- ccx where ----

def catalog(tmp_path):
    cat = projects.scan([str(tree(tmp_path))])
    projects.save(paths(), cat)
    return cat


def test_where_chinese_name_from_title_or_commits(tmp_path):
    cat = catalog(tmp_path)
    r = projects.where(cat, "改一下那个桌宠")
    assert r["terms"] == ["桌宠"] and r["pick"] == "desk-pet"
    assert "桌宠" in r["candidates"][0]["why"][0]
    assert projects.where(cat, "桌面伙伴 的问题")["pick"] == "fish"        # a README one level down


def test_where_english_typo_and_remote_name(tmp_path):
    cat = catalog(tmp_path)
    assert projects.where(cat, "the pet-repo PR")["pick"] == "desk-pet"   # git remote name
    assert projects.where(cat, "fix the notse site")["pick"] == "notes-site"   # one letter off


def test_where_lists_when_several_fit(tmp_path):
    cat = catalog(tmp_path)
    r = projects.where(cat, "wrapper ui")
    assert r["pick"] is None
    assert {"wrapper", "ui"} <= {c["name"] for c in r["candidates"]}


def test_where_nothing(tmp_path):
    cat = catalog(tmp_path)
    r = projects.where(cat, "完全无关 quantum")
    assert r["pick"] is None and r["candidates"] == []


def test_where_command(tmp_path):
    catalog(tmp_path)
    out = ccx("where", "那个", "桌宠")
    assert out["pick"] == "desk-pet" and out["candidates"][0]["path"].endswith("desk-pet")
    assert out["read_first"][0].endswith("CLAUDE.md")


# ---- ccx run --project ----

def run_env(tmp_path):
    fakes = REPO / "tests" / "fakes"
    return {**os.environ, "CCX_CODEX_BIN": str(fakes / "fake_codex.py"), "CCX_CLAUDE_BIN": str(fakes / "fake_claude.py"),
            "FAKE_LOG": str(tmp_path / "calls.jsonl"), "CCX_AB_RATE": "0", "CCX_NO_BENCH_REFRESH": "1",
            "CCX_NO_QUOTA_PROBE": "1"}


def run_ccx(env, *args):
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), *args], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return r.returncode, json.loads(r.stdout)


def test_run_project_goes_into_it_with_its_rules(tmp_path):
    catalog(tmp_path)
    env = run_env(tmp_path)
    code, out = run_ccx(env, "run", "--from", "claude", "--to", "codex", "--tier", "T1", "--project", "桌宠",
                        "rename foo to bar in a.py")
    assert code == 0, out
    assert out["project"]["name"] == "desk-pet"
    call = json.loads((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert call["prompt"].count("Project: desk-pet") == 1 and "CLAUDE.md" in call["prompt"]
    assert any(x.endswith("desk-pet") for x in call["argv"])                       # it runs in that folder


def test_run_project_with_approval_rules_stops_until_the_lead_read_them(tmp_path):
    catalog(tmp_path)
    env = run_env(tmp_path)
    code, out = run_ccx(env, "run", "--from", "claude", "--to", "codex", "--tier", "T1", "--project", "lab", "x")
    assert code == 0 and out["delegated"] is False
    assert out["approval_rules"][0]["text"] == "Approval needed before each stage."     # quoted as written
    assert not (tmp_path / "calls.jsonl").exists()
    code, out = run_ccx(env, "run", "--from", "claude", "--to", "codex", "--tier", "T1", "--project", "lab",
                        "--rules-ok", "x")
    assert code == 0 and out["project"]["approval_rules"]


def test_run_project_not_unique_lists_candidates(tmp_path):
    catalog(tmp_path)
    code, out = run_ccx(run_env(tmp_path), "run", "--from", "claude", "--project", "wrapper ui", "x")
    assert code == 3 and "candidates" in out["error"] and "wrapper" in out["error"]
    code, out = run_ccx(run_env(tmp_path), "run", "--from", "claude", "--project", "lab", "--cwd", ".", "x")
    assert code == 3 and "not both" in out["error"]


def test_where_shows_approval_rules_and_session_start_points_at_where(tmp_path):
    catalog(tmp_path)
    out = ccx("where", "research", "lab")
    assert out["pick"] == "lab" and out["approval_rules"][0]["line"] == 3
    r = subprocess.run([sys.executable, str(REPO / "ccx.py"), "mem", "delta", "--as", "claude", "--peek"],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert "ccx where" in r.stdout and "8 projects" in r.stdout
