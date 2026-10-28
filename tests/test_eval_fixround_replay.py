"""Fix-round replay (scripts/eval/fixround_replay.py) and r5's per-tag wall summary: local fake repos and hubs,
a fake scorer, no real CLI."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import fixround_replay as F  # noqa: E402
import r5  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ccx import review  # noqa: E402


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def fake_repo(d: Path) -> str:
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@example.invalid")
    git(d, "config", "user.name", "t")
    (d / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    return git(d, "rev-parse", "HEAD")


def snap_diff(repo: Path, base: str) -> str:
    """The diff text a review prompt holds, made by ccx's own review.changes()."""
    return review.changes(repo, {"base": base, "repo": str(repo), "untracked": []})[1]


def write_run(hub: Path, rid: str, ts: float, **kw):
    d = hub / "ccx" / "runs" / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps({"run_id": rid, "ts": ts, **kw}), encoding="utf-8")
    return d


def review_of(hub: Path, rid: str, diff: str, ts: float, cut: bool = False):
    d = write_run(hub, f"rev-{rid}", ts, caller="ccx-review", label=f"review:{rid}")
    text = review.brief(rid, "the task", "did it", diff, 10 if cut else 12000, {"cmd": "pytest", "passed": True})
    # written in text mode, as delegate.py does: \r\n on Windows
    (d / "prompt.md").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    return f"rev-{rid}"


def test_extract_diff_and_new_files_round_trip(tmp_path):
    repo = tmp_path / "r"
    base = fake_repo(repo)
    (repo / "m.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    (repo / "new.py").write_text("X = 1\n", encoding="utf-8")
    diff = snap_diff(repo, base)
    prompt = review.brief("r1", "t", "s", diff, 12000)
    got, cut = F.extract_diff(prompt)
    assert got == diff and not cut
    patch, new = F.split_new_files(got)
    assert "return 2" in patch and "new.py" not in patch
    assert new == {"new.py": "X = 1\n"}
    assert F.extract_diff(review.brief("r1", "t", "s", diff, 10))[1] is True
    assert F.extract_diff("no diff here") == (None, False)


def test_build_tree_from_a_prompt_diff(tmp_path):
    repo = tmp_path / "r"
    base = fake_repo(repo)
    (repo / "m.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "n.py").write_text("Y = 3\n", encoding="utf-8")
    patch, new, completed, why = F.state_from_prompt(snap_diff(repo, base), {})
    assert why is None and completed == 0
    dest = tmp_path / "out"
    assert F.build_tree(repo, base, dest, patch, new) is None
    assert (dest / "m.py").read_text(encoding="utf-8").replace("\r\n", "\n") == "def f():\n    return 2\n"
    assert (dest / "pkg" / "n.py").read_text(encoding="utf-8") == "Y = 3\n"


def test_a_cut_new_file_is_completed_from_the_final_tree_or_skipped(tmp_path):
    repo = tmp_path / "r"
    base = fake_repo(repo)
    big = "".join(f"line_{i} = {i}\n" for i in range(600))           # > 4000 characters
    (repo / "big.py").write_text(big, encoding="utf-8")
    diff = snap_diff(repo, base)
    _, new = F.split_new_files(diff)
    assert F.maybe_cut(new["big.py"])
    _, fnew = F.final_state(repo, base)
    patch, out, completed, why = F.state_from_prompt(diff, fnew)
    assert why is None and completed == 1 and out["big.py"] == fnew["big.py"]
    _, _, _, why = F.state_from_prompt(diff, {})
    assert "cut at 4000" in why
    _, _, _, why = F.state_from_prompt(diff, {"big.py": b"something else\n" * 400})
    assert "changed later" in why


def unit(tmp_path: Path, key: str, post_ok: bool, auto: bool = True, reviewed_fix: bool = True):
    """A work dir with one unit: run r1 (review issues) -> fix run r2 -> maybe its review; the repo's final tree."""
    wd = tmp_path / "wd"
    repo, hub = wd / key, wd / f"h-{key}"
    base = fake_repo(repo)
    (repo / "m.py").write_text("def f():\n    return 'pre'\n", encoding="utf-8")
    d = write_run(hub, "r1", 1, caller="claude", label="eval-r5:r5x:1:waiting-evals:ccx2",
                  review={"verdict": "issues", "reason": "77 changed code lines", "run_id": "rev-r1",
                          "issues": ["[must] m.py:2 — NameError: g is not defined"]})
    (d / "undo.json").write_text(json.dumps({"base": base, "repo": str(repo), "untracked": []}), encoding="utf-8")
    review_of(hub, "r1", snap_diff(repo, base), 2)
    (repo / "m.py").write_text(f"def f():\n    return {'good' if post_ok else 'bad'!r}\n", encoding="utf-8")
    fix = {"review_of": "r1"} if auto else {}
    if reviewed_fix:
        fix["review"] = {"verdict": "pass", "reason": "asked", "run_id": "rev-r2", "issues": []}
    write_run(hub, "r2", 3, caller="claude", label="eval-r5:r5x:1:waiting-evals:ccx2", resumed_from="r1", **fix)
    if reviewed_fix:
        review_of(hub, "r2", snap_diff(repo, base), 4)
    return wd


def scorer(repo, task, work):
    """The 'hidden test': passes when m.py returns 'good'."""
    return {"ok": "'good'" in (repo / "m.py").read_text(encoding="utf-8"), "pytest": "fake"}


def test_replay_counts_fail_to_pass_per_reason(tmp_path):
    wd = unit(tmp_path, "1-waiting-evals-ccx2", post_ok=True)
    out = F.replay([wd], jobs=1, scorer=scorer, scratch=tmp_path / "s", check_final=True)
    (row,) = out["rows"]
    assert row["outcome"] == "fail->pass" and row["by"] == "auto" and row["after_from"] == "fix review"
    assert row["reason_bucket"] == ">= min_lines changed code lines" and row["issue_kind"] == "crash / error"
    t = F.table(out["rows"], "reason_bucket")
    assert t[">= min_lines changed code lines"]["fail->pass"] == 1 and t["(all)"]["n"] == 1
    assert "fail->pass" in F.render(t, "review reason")
    # the second method: the final tree re-scored against the recorded result
    (fin,) = out["finals"]
    assert fin["replayed_ok"] is True
    agree = F.final_agreement(out["finals"], [{"tag": "r5x", "round": 1, "task": "waiting-evals", "arm": "ccx2",
                                               "ok": True}])
    assert agree == {"same": 1, "different": 0, "missing": 0, "different_units": []}
    # a cache hit scores nothing again
    calls = []
    F.replay([wd], jobs=1, scorer=lambda *a: calls.append(a) or {"ok": True}, cache=out["cache"],
             scratch=tmp_path / "s2")
    assert calls == []


def test_replay_a_lead_resume_uses_the_final_tree_and_pass_to_fail(tmp_path):
    wd = unit(tmp_path, "1-waiting-evals-ccx2", post_ok=False, auto=False, reviewed_fix=False)
    # make the 'before' tree pass: the scorer sees 'pre' as good here
    out = F.replay([wd], jobs=1, scorer=lambda repo, task, work: {"ok": "'bad'" not in (repo / "m.py").read_text(
        encoding="utf-8")}, scratch=tmp_path / "s")
    (row,) = out["rows"]
    assert row["by"] == "lead" and row["after_from"] == "final tree" and row["outcome"] == "pass->fail"


def test_replay_skips_a_cut_review_diff(tmp_path):
    wd = unit(tmp_path, "1-waiting-evals-ccx2", post_ok=True)
    review_of(wd / "h-1-waiting-evals-ccx2", "r1", "x" * 50, 2, cut=True)
    out = F.replay([wd], jobs=1, scorer=scorer, scratch=tmp_path / "s")
    (row,) = out["rows"]
    assert row["outcome"] == "skipped" and "max_diff_chars" in row["skip"]


def test_other_arms_are_left_out(tmp_path):
    wd = unit(tmp_path, "1-waiting-evals-direct", post_ok=True)
    assert F.replay([wd], jobs=1, scorer=scorer, scratch=tmp_path / "s")["rows"] == []
    assert len(F.replay([wd], arms=("direct",), jobs=1, scorer=scorer, scratch=tmp_path / "s")["rows"]) == 1


def test_reason_buckets_and_issue_kinds():
    assert F.reason_bucket("asked") == "asked (--review on)"
    assert F.reason_bucket("the tests it runs don't touch a.py: f") == "check does not reach the change"
    assert F.reason_bucket("the sub-agent is unsure") == "the sub-agent is unsure"
    assert F.issue_kind(['[must] a.py:3 — "returns None" — wrong']) == "task requirement (quoted)"
    assert F.issue_kind(["[must] a.py — style"]) == "other"
    assert F.classify(True, None) == "skipped" and F.classify(False, False) == "fail->fail"


def test_r5_summary_keeps_tags_and_rounds_apart_with_mean_and_p75():
    rows = [{"tag": tag, "round": rd, "task": "a", "arm": "ccx2", "ok": True, "usd": 0.1, "wall_s": w,
             "env_clean": True}
            for tag, rd, w in (("t1", 1, 100), ("t1", 1, 200), ("t1", 2, 300), ("t1", 2, 400), ("t2", 1, 1000))]
    s = r5.summarize(rows)
    t1 = s["by_tag"]["t1"]["ccx2"]
    assert t1["n"] == 4 and t1["wall_mean"] == 250.0 and t1["wall_p75"] == 300 and t1["wall_med"] == 300
    assert t1["rounds"]["1"]["wall_mean"] == 150.0 and t1["rounds"]["2"]["n"] == 2
    assert s["by_tag"]["t2"]["ccx2"]["wall_p75"] == 1000 and s["by_tag"]["t2"]["ccx2"]["cps"] == 0.1
    assert s["arms"]["ccx2"]["wall_mean"] == 400.0 and s["arms"]["ccx2"]["wall_p75"] == 400
    assert r5.wall_stats([])["wall_med"] is None
