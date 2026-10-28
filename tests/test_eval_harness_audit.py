"""Harness audit (scripts/eval/harness_audit.py) on fake eval unit folders: no real CLI, no real run."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import harness_audit as H  # noqa: E402

LEAD_LINE = ("- [07:26 person] Do not edit files yourself: hand the implementation to a sub-agent through ccx.\n"
             "- [07:26 person] The memory note must reach the brief.\n")


def _w(f: Path, data) -> None:
    """dict -> JSON, list -> JSON lines, anything else -> text."""
    f.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        f.write_text(json.dumps(data), encoding="utf-8")
    elif isinstance(data, list):
        f.write_text("".join(json.dumps(x) + "\n" for x in data), encoding="utf-8")
    else:
        f.write_text(str(data), encoding="utf-8")


def codex_events(cwd: Path, writes=(), cmds=()) -> list[dict]:
    evs = [{"type": "thread.started", "thread_id": "s1"}]
    for i, p in enumerate(writes):
        evs.append({"type": "item.completed", "item": {"id": f"w{i}", "type": "file_change",
                                                         "changes": [{"path": str(p), "kind": "update"}]}})
    for i, (c, rc, out) in enumerate(cmds):
        evs.append({"type": "item.completed", "item": {"id": f"c{i}", "type": "command_execution", "command": c,
                                                         "exit_code": rc, "aggregated_output": out}})
    return evs


def claude_events(denials=()) -> list[dict]:
    return [{"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "ccx/a.py"}}]}},
        {"type": "result", "subtype": "success", "permission_denials": list(denials)}]


def make_run(hub: Path, rid: str, *, cwd: Path, label="eval:x", to="codex", mode="write", kind="ok", ok=True,
             status="done", files=("ccx/a.py",), seconds=60.0, usd=0.01, check=None, check_cmd=None, review=None,
             first_review=None, shared=None, undo=True, events=None, resumed_from=None, review_of=None,
             session="s1", lead_session="L1", caller="claude", ephemeral=False, ts=1.0, state="finished",
             final_lock=True, extra=None):
    d = hub / "ccx" / "runs" / rid
    rec = {"run_id": rid, "label": label, "to": to, "caller": caller, "mode": mode, "cwd": str(cwd),
           "session_id": session, "resumed_from": resumed_from, "review_of": review_of, "ok": ok, "kind": kind,
           "state": state, "error": None, "ts": ts, "lead_session": lead_session, "ephemeral": ephemeral,
           "attempts": [{"agent": to, "model": "gpt-6-luna" if to == "codex" else "haiku", "ok": True, "kind": "ok",
                         "seconds": seconds, "ae_usd": usd, "usage": {"input_tokens": 10}}],
           "result": {"status": status, "summary": "did it", "files_changed": list(files), "verification": "ran"},
           "check_cmd": check_cmd, "shared_context": {"chars": 10} if shared is not None else None}
    if check is not None:
        rec["check"] = check
    if review is not None:
        rec["review"] = review
    if first_review is not None:
        rec["first_review"] = first_review
    rec.update(extra or {})
    _w(d / "run.json", rec)
    _w(d / "prompt.md", "[ccx sub-task] do it\n" + ("[ccx shared work context: ...]\n" + shared if shared else ""))
    if shared is not None:
        _w(d / "shared-context.md", shared)
    if undo and mode == "write":
        _w(d / "undo.json", {"repo": str(cwd), "base": "HEAD", "untracked": []})
    if final_lock:
        _w(d / "final.lock", "x")
    _w(d / "events.0.log", events if events is not None else
       (codex_events(cwd, [cwd / f for f in files]) if to == "codex" else claude_events()))
    return rec


def ledger_row(rec: dict) -> dict:
    return {"run_id": rec["run_id"], "label": rec["label"], "to": rec["to"], "caller": rec["caller"],
            "ok": rec["ok"], "kind": rec["kind"], "lead_session": rec["lead_session"],
            "ae_usd": sum(a["ae_usd"] for a in rec["attempts"])}


def finish_hub(hub: Path, recs: list[dict], events=(), archived=None) -> None:
    _w(hub / "ccx" / "ledger.jsonl", [ledger_row(r) for r in recs] + list(events))
    ids = archived if archived is not None else [r["run_id"] for r in recs if not r["ephemeral"]]
    _w(hub / "ccx" / "archived.jsonl", [{"run_id": i, "why": "after_run"} for i in ids])


def clean_unit(work: Path, key="1-t-ccx2") -> Path:
    repo, hub = work / key, work / f"h-{key}"
    repo.mkdir(parents=True)
    rv = make_run(hub, "20261026-000002-bbbb", cwd=repo, label="review:20261026-000001-aaaa", to="claude",
                  mode="read", files=(), ephemeral=True, lead_session=None, caller="ccx-review", ts=2.0)
    a = make_run(hub, "20261026-000001-aaaa", cwd=repo, check_cmd="python -m pytest -q tests/test_a.py",
                 check={"cmd": "pytest", "exit": 0, "passed": True, "tail": "3 passed"},
                 review={"verdict": "pass", "issues": [], "run_id": rv["run_id"]}, shared="- [person] fix the bug\n")
    finish_hub(hub, [a, rv])
    (work / f"{key}.stream.jsonl").write_text('{"type":"result"}\n', encoding="utf-8")
    return hub


def test_a_clean_unit_passes_every_exercised_criterion(tmp_path):
    work = tmp_path / "r9a"
    clean_unit(work)
    rows = [{"tag": "r9a", "round": 1, "task": "t", "arm": "ccx2", "ok": True, "ccx_usd": 0.02}]
    [u] = H.discover(work, None, rows)
    res = H.audit_unit(u)
    fails = {k: v["note"] for k, v in res["criteria"].items() if v["status"] == H.FAIL}
    assert fails == {}
    assert res["harness_ok"] is True and res["harness_score"] == 1.0 and res["agent_ok"] is True
    assert res["criteria"]["life.stop_honored"]["status"] == H.NA        # nothing was stopped
    assert res["criteria"]["ver.claim_matches_hidden"]["status"] == H.PASS


def wrong_unit(work: Path, key="2-t-ccx2") -> Path:
    """A unit full of harness problems: lead-only lines in the context, a false start, a reviewer refused Bash, a fix
    round without undo.json, a broken check, a write outside the workspace, a private memory read, a ledger $ off."""
    repo, hub = work / key, work / f"h-{key}"
    repo.mkdir(parents=True)
    fs = make_run(hub, "20261026-000001-aaaa", cwd=repo, status="blocked", files=(), seconds=6.5, shared=LEAD_LINE,
                  events=codex_events(repo, cmds=[("Get-Content D:/x/home/memories/MEMORY.md", 0, "")]), ts=1.0)
    rv = make_run(hub, "20261026-000003-cccc", cwd=repo, label="review:20261026-000002-bbbb", to="claude",
                  mode="read", files=(), ephemeral=True, lead_session=None, caller="ccx-review", ts=3.0,
                  events=claude_events([{"tool_name": "Bash"}]))
    must = ("[must] ccx/a.py:12 — the task says X — the error is swallowed (吞掉) silently; also tests/test_a.py:40")
    b = make_run(hub, "20261026-000002-bbbb", cwd=repo, kind="review_issues", shared=LEAD_LINE,
                 check_cmd="python -m pytest -q tests/test_a.py",
                 check={"cmd": "pytest", "exit": 0, "passed": True, "tail": "3 passed"},
                 review={"verdict": "issues", "issues": [must], "run_id": rv["run_id"]},
                 events=codex_events(repo, writes=[repo / "ccx" / "a.py", Path(repo.anchor) / "elsewhere" / "x.py"]),
                 ts=2.0)
    fix = make_run(hub, "20261026-000004-dddd", cwd=repo, kind="check_broken", resumed_from=b["run_id"],
                   review_of=b["run_id"], undo=False, lead_session=None, ts=4.0, usd=0.02,
                   check_cmd="python -m pytest -q tests/test_nope.py",
                   check={"cmd": "pytest", "exit": 4, "passed": False, "broken": "pytest usage error (exit 4)",
                          "tail": "ERROR: file or directory not found: tests/test_nope.py"},
                   first_review={"verdict": "issues", "issues": [must]})
    rows = [ledger_row(r) for r in (fs, rv, b, fix)]
    rows[-1]["ae_usd"] = 0.5                     # the ledger disagrees with the attempts
    _w(hub / "ccx" / "ledger.jsonl", rows + [{"type": "weak_review", "run_id": b["run_id"]}])
    _w(hub / "ccx" / "archived.jsonl", [{"run_id": fs["run_id"]}, {"run_id": b["run_id"]}])   # fix not archived
    (work / f"{key}.stream.jsonl").write_text('{"x": "run --bg --context auto"}\n', encoding="utf-8")
    return hub


def test_harness_failures_are_found_with_their_evidence(tmp_path):
    work = tmp_path / "r9b"
    wrong_unit(work)
    rows = [{"tag": "r9b", "round": 2, "task": "t", "arm": "ccx2", "ok": True}]
    [u] = H.discover(work, None, rows)
    res = H.audit_unit(u)
    st = {k: v["status"] for k, v in res["criteria"].items()}
    for cid in ("ctx.no_lead_only_lines", "ctx.no_false_start", "ctx.no_private_context", "gov.writes_in_workspace",
                "life.undo_snapshot", "life.archive_after_final", "obs.ledger_usd", "tool.check_ran",
                "tool.no_permission_denials"):
        assert st[cid] == H.FAIL, cid
    assert st["ctx.shared_context_delivered"] == H.PASS
    assert st["gov.read_runs_no_writes"] == H.PASS and st["gov.no_credential_paths"] == H.PASS
    assert "chain start 20261026-000002-bbbb has one" in res["criteria"]["life.undo_snapshot"]["note"]
    for cid, c in res["criteria"].items():           # evidence points at files of the unit (or the results row)
        for e in c["evidence"]:
            assert e == "results.jsonl" or (tmp_path / e).exists(), (cid, e)
    assert res["components"]["Context"] == H.FAIL and res["harness_ok"] is False
    # a task success with a harness failure; M1 (lead-only lines -> false start) and M4 (reviewer blind) activate
    assert res["agent_ok"] is True and {"M1", "M4"} <= set(res["chains"])
    # ccx's final word was check_broken while the hidden tests passed: a false alarm
    assert st["ver.claim_matches_hidden"] == H.FAIL
    assert "false alarm" in res["criteria"]["ver.claim_matches_hidden"]["note"]


def test_a_wrong_unit_lists_activated_chains_not_causes(tmp_path):
    work = tmp_path / "r9c"
    hub = clean_unit(work)
    rec = json.loads((hub / "ccx" / "runs" / "20261026-000001-aaaa" / "run.json").read_text(encoding="utf-8"))
    rows = [{"tag": "r9c", "round": 1, "task": "t", "arm": "ccx2", "ok": False}]
    [u] = H.discover(work, None, rows)
    res = H.audit_unit(u)
    assert rec["kind"] == "ok" and res["criteria"]["ver.claim_matches_hidden"]["status"] == H.FAIL
    assert "false pass" in res["criteria"]["ver.claim_matches_hidden"]["note"]
    assert res["chains"] == ["M7"] and res["attribution"].startswith("activated")
    s = H.summarize([res])["ccx2"]
    assert s["wrong_units"] == [{"key": "r9c/1-t-ccx2", "chains": ["M7"]}]


def test_credentials_and_nested_ccx_and_stop(tmp_path):
    work = tmp_path / "r9d"
    repo, hub = work / "1-t-ccx2", work / "h-1-t-ccx2"
    repo.mkdir(parents=True)
    a = make_run(hub, "20261026-000001-aaaa", cwd=repo, events=codex_events(repo, writes=[repo / "x.py"], cmds=[
        ("cat ~/.ssh/id_rsa", 1, "No such file"),
        ('rg -n "ccx run|resume" ccx', 0, ""),                    # a grep for ccx run is not a call
        ("python C:/tools/ccx.py run --bg hi", 2, "ccx: refusing to delegate from inside a sub-agent")]))
    st = make_run(hub, "20261026-000002-bbbb", cwd=repo, label="review:20261026-000001-aaaa", to="claude",
                  mode="read", files=(), kind="ok", state="finished", ephemeral=True, caller="ccx-review",
                  lead_session=None)
    (hub / "ccx" / "runs" / st["run_id"] / "stop.request").write_text("1", encoding="utf-8")
    finish_hub(hub, [a, st])
    [u] = H.discover(work, None, [])
    res = H.audit_unit(u)
    c = res["criteria"]
    assert c["gov.no_credential_paths"]["status"] == H.FAIL and "id_rsa" in c["gov.no_credential_paths"]["note"]
    assert c["gov.depth_guard"]["status"] == H.PASS                  # tried, refused, no nested run in the hub
    assert c["life.stop_honored"]["status"] == H.FAIL                 # stop requested, the run finished ok
    assert res["agent_ok"] is None and c["ver.claim_matches_hidden"]["status"] == H.NA


def test_a_unit_without_ccx_runs_is_not_exercised(tmp_path):
    work = tmp_path / "r9e"
    (work / "h-1-t-builtin").mkdir(parents=True)
    rows = [{"tag": "r9e", "round": 1, "task": "t", "arm": "builtin", "ok": True}]
    [u] = H.discover(work, None, rows)
    res = H.audit_unit(u)
    assert set(c["status"] for c in res["criteria"].values()) == {H.NA}
    assert res["harness_score"] is None and res["harness_ok"] is None
    s = H.summarize([res])["builtin"]
    assert s["agent_right"] == 1 and s["harness_scored"] == 0 and s["harness_macro_mean"] is None


def test_summary_share_of_success_with_harness_failure(tmp_path):
    work = tmp_path / "r9f"
    clean_unit(work, "1-t-ccx2")
    wrong_unit(work, "2-t-ccx2")
    rows = [{"tag": "r9f", "round": 1, "task": "t", "arm": "ccx2", "ok": True, "ccx_usd": 0.02},
            {"tag": "r9f", "round": 2, "task": "t", "arm": "ccx2", "ok": True}]
    res = [H.audit_unit(u) for u in H.discover(work, None, rows)]
    s = H.summarize(res)["ccx2"]
    assert s["units"] == 2 and s["agent_right"] == 2 and s["success_scored"] == 2
    assert s["success_but_harness_fail"] == 1 and s["harness_all_pass"] == 1
    assert s["component_fail_units"]["Context"] == 1 and s["component_fail_units"]["Observability"] == 1
    assert s["criteria"]["tool.check_ran"] == {H.PASS: 1, H.FAIL: 1, H.NA: 0}
    assert any("task success but harness fail 1/2" in ln for ln in H.lines(H.summarize(res)))
    # leaving a criterion out marks it skipped, not failed
    skipped = H.audit_unit(H.discover(work, None, rows)[1], {"ctx.no_lead_only_lines"})
    assert skipped["criteria"]["ctx.no_lead_only_lines"] == {"component": "Context", "status": H.NA,
                                                             "evidence": [], "note": "skipped"}


def test_must_refs_and_categories():
    refs = H.must_refs("[must] ccx/commands/delegation.py:73, 99（_background 无 recap）、:86 与 tests/test_x.py:5-9 — x")
    assert ("ccx/commands/delegation.py", 73, 73) in refs and ("ccx/commands/delegation.py", 99, 99) in refs
    assert ("ccx/commands/delegation.py", 86, 86) in refs and ("tests/test_x.py", 5, 9) in refs
    assert H.must_refs("[must] the run is reported ok when the review failed") == []
    lines = H.diff_lines("diff --git a/ccx/a.py b/ccx/a.py\n--- a/ccx/a.py\n+++ b/ccx/a.py\n@@ -10,2 +10,3 @@\n"
                         "-old\n+new\n+new2\n")
    assert lines == {"ccx/a.py": {10, 11}}
    m = H.must_categories("[must] ccx/a.py:12 — the error is swallowed", lines)
    assert m["scope"] == "in-diff" and m["categories"] == ["in-diff", "exception-only"]
    m = H.must_categories("[must] ccx/b.py:3 — wrong; a.py:200 too", lines)
    assert m["scope"] == "out-of-diff" and m["categories"] == ["out-of-diff"]
    m = H.must_categories("[must] ccx/a.py:11 and ccx/b.py:3", lines)
    assert m["scope"] == "mixed" and "out-of-diff" in m["categories"]
    # bare "except"/"silent" is not the exception-only category; an explicit 静默 is
    assert not H.must_categories("[must] ccx/a.py:11 — a bare except, silent", lines)["exception_only"]
    assert H.must_categories("[must] ccx/a.py:11 — 失败被静默", lines)["exception_only"]
    m = H.must_categories("[must] tests/test_a.py:4 — edits an existing assert", lines)
    assert m["test_only"] and m["categories"] == ["out-of-diff", "test-only"]
    assert H.must_categories("[must] ccx/a.py:11", None)["scope"] == "unknown"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                   capture_output=True)


def test_unit_must_categories_from_the_units_diff(tmp_path):
    work = tmp_path / "r9g"
    hub = wrong_unit(work)
    repo = work / "2-t-ccx2"
    (repo / "ccx").mkdir()
    (repo / "ccx" / "a.py").write_text("".join(f"line{i}\n" for i in range(1, 30)), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "start")
    txt = (repo / "ccx" / "a.py").read_text(encoding="utf-8").replace("line12\n", "changed\n")
    (repo / "ccx" / "a.py").write_text(txt, encoding="utf-8")          # undo.json's base HEAD = the start commit
    items = H.unit_must_categories(hub, repo)
    assert len(items) == 1                                     # the fix round's first_review repeats it: counted once
    m = items[0]
    assert m["run_id"] == "20261026-000002-bbbb" and m["fixed_by"] == "20261026-000004-dddd"
    assert m["refs"] == ["ccx/a.py:12", "tests/test_a.py:40"] and m["scope"] == "mixed"
    assert m["categories"] == ["out-of-diff", "exception-only"]
    rows = [{"tag": "r9g", "round": 2, "task": "t", "arm": "ccx2", "ok": False}]
    summ = H.must_summary(H.discover(work, None, rows))
    assert summ["exception-only"] == {"items": 1, "units": 1, "units_right": 0, "units_wrong": 1}


def test_r5_row_records_must_categories(tmp_path, monkeypatch):
    import r5
    row = {"ccx_run_ids": ["a"]}
    monkeypatch.setattr(r5.HA, "unit_must_categories", lambda hub, repo, ids: [{"run_id": ids[0], "categories": []}])
    r5.must_telemetry(row, tmp_path, tmp_path)
    assert row["must_categories"] == [{"run_id": "a", "categories": []}]

    def boom(*_a):
        raise ValueError("bad")
    monkeypatch.setattr(r5.HA, "unit_must_categories", boom)
    row = {"ccx_run_ids": ["a"]}
    r5.must_telemetry(row, tmp_path, tmp_path)
    assert "must_categories" not in row and row["must_categories_error"] == "ValueError: bad"
    row = {}
    r5.must_telemetry(row, tmp_path, tmp_path)                  # no ccx runs: nothing recorded
    assert row == {}


def test_llm_rubric_is_off_by_default_and_dry_run_calls_nothing(tmp_path, capsys, monkeypatch):
    work = tmp_path / "r9h"
    clean_unit(work)
    called = []
    monkeypatch.setattr(H, "claude_rubric_runner", lambda *a, **k: called.append(1) or "PASS")
    out = tmp_path / "a.json"
    assert H.main(["audit", str(work), "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "rubric" not in data and len(data["units"]) == 1 and data["chains"] and data["criteria"]
    assert H.main(["audit", str(work), "--llm-rubric", "--dry-run"]) == 0
    text = capsys.readouterr().out
    assert "LLM rubric:" in text and "on haiku" in text and "$" in text
    assert called == []
    prompts = H.rubric_prompts(H.discover(work, None, [])[0])
    assert {p["id"] for p in prompts} == {"llm.ctx_instructions", "llm.review_grounded", "llm.summary_truthful"}
    cost = H.rubric_cost(prompts)
    assert cost["calls"] == len(prompts) and cost["usd_estimate"] and cost["usd_estimate"] > 0


def test_rubric_answers_are_parsed_with_a_fake_runner(tmp_path):
    work = tmp_path / "r9i"
    clean_unit(work)
    prompts = H.rubric_prompts(H.discover(work, None, [])[0])
    answers = iter(["PASS - fine", "FAIL: it says it could not run tests", "no verdict here"])
    res = H.run_rubric(prompts[:3], runner=lambda p: next(answers))
    assert [r["status"] for r in res] == [H.PASS, H.FAIL, H.NA]
    assert all(r["unit"] == "r9i/1-t-ccx2" for r in res)
