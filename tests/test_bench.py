"""bench/: the public benchmark package. Its task files agree with the evaluation's task sets, its published rows
hold no personal data and still give the numbers the docs quote, and run.py builds the r5.py command it says."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from test_repo_hygiene import DRIVE_PATH, find_personal_data

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bench" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


make_tasks = _load("bench_make_tasks", "make_tasks.py")
bench = _load("bench_run", "run.py")

RESULTS = ROOT / "bench" / "results"
RUN_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")


def test_task_files_match_the_task_sets():
    assert make_tasks.main(["--check"]) == 0, "run python bench/make_tasks.py"
    files = sorted(p.relative_to(make_tasks.OUT).as_posix() for p in make_tasks.OUT.glob("*/*.md"))
    assert len(files) == 20 and sum(f.startswith("holdout/") for f in files) == 10


def test_external_tasks_are_pointers_only():
    for p in (make_tasks.OUT / "holdout").glob("*.md"):
        text = p.read_text(encoding="utf-8")
        if "github.com/python-humanize" in text or "github.com/pallets" in text:
            assert "not copied here" in text and "/blob/" in text
            assert "def test_" not in text and "\nimport " not in text


@pytest.mark.parametrize("name", ["hc1", "r5-dev"])
def test_published_rows_hold_no_personal_data(name):
    for f in (RESULTS / f"{name}.jsonl", RESULTS / f"{name}-summary.json"):
        text = f.read_text(encoding="utf-8")
        assert not DRIVE_PATH.search(text), f"{f.name}: an absolute drive path"
        assert not find_personal_data(text), f"{f.name}: {find_personal_data(text)[:3]}"
        assert not RUN_ID.search(text), f"{f.name}: a ccx run id (its timestamp says when the machine was in use)"
        assert '"env_keys_sha256"' not in text


def test_hc1_table_gives_the_published_numbers():
    rows = bench.read_rows(RESULTS / "hc1.jsonl")
    assert len(rows) == 90
    t = bench.table(rows, "hc1")
    assert "| hc1 | ccx2 (delegated to Codex through ccx) | 29/30 | $0.063 | 61 s |" in t
    assert "| hc1 | self (the lead does it itself) | 29/30 | $0.090 | 21 s |" in t
    assert "| hc1 | builtin (Claude Code's built-in sub-agent) | 27/28 | $0.103 | 123 s |" in t
    assert "2 row(s) not counted" in t


def test_r5_dev_table_gives_measured_md_rows():
    t = bench.table(bench.read_rows(RESULTS / "r5-dev.jsonl"))
    assert "| r5h | ccx2 (delegated to Codex through ccx) | 19/20 | $0.135 | 236 s |" in t
    assert "| r5d | builtin2 (built-in sub-agent, ccx2's lean wording) | 17/20 | $0.114 | 276 s |" in t
    assert "| r5f | ccx2 (delegated to Codex through ccx) | 20/20 | $0.116 | 267 s |" in t


def test_run_builds_the_r5_command(monkeypatch):
    monkeypatch.setattr(bench, "head", lambda: "abc1234")
    a = bench.parser().parse_args(["run", "--arm", "ccx", "--tasks", "hz-intword-carry", "--codex-home", "/x/h"])
    argv, out, tag = bench.r5_argv(a, ["--no-canary"])
    assert tag == "holdout-abc1234" and out == bench.RUNS / "holdout-abc1234-results.jsonl"
    assert argv[1:3] == [str(bench.R5), "run"]
    s = " ".join(argv[3:])
    assert "--taskset holdout --arms ccx2" in s and "--tasks hz-intword-carry" in s and "--codex-home" in s
    assert argv[argv.index("--codex-home") + 1] == str(Path("/x/h").resolve())     # r5.py runs from the repo root
    assert argv[-1] == "--no-canary"
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))
    import r5
    parsed = r5.parser().parse_args(argv[2:])         # every option is one r5.py run really takes
    assert parsed.arms == "ccx2" and parsed.taskset == "holdout"


def test_several_arms_interleave_in_one_run(monkeypatch):
    monkeypatch.setattr(bench, "head", lambda: "abc1234")
    argv, _, _ = bench.r5_argv(bench.parser().parse_args(["run", "--arm", "self,ccx"]), [])
    assert argv[argv.index("--arms") + 1] == "self,ccx2"
    with pytest.raises(SystemExit):
        bench.r5_argv(bench.parser().parse_args(["run", "--arm", "self,nope"]), [])


def test_main_passes_what_follows_the_dashes(monkeypatch):
    seen = {}
    monkeypatch.setattr(bench, "cmd_run", lambda a, extra: seen.update(arm=a.arm, extra=extra) or 0)
    assert bench.main(["run", "--arm", "self", "--", "--no-canary", "--seed", "7"]) == 0
    assert seen == {"arm": "self", "extra": ["--no-canary", "--seed", "7"]}


def test_readmes_say_the_holdout_set_is_spent():
    assert "no longer a hold-out set" in (ROOT / "bench" / "README.md").read_text(encoding="utf-8")
    assert "不再是留出集" in (ROOT / "bench" / "README.zh.md").read_text(encoding="utf-8")
