"""Seven cores, functional checks on real CLIs (cores 1 and 7; plan section 2). Each check is one real scenario in a
fresh scratch repo, judged by files and the hidden test, not by what an agent says:

  codex-lead   a headless Codex lead (`codex exec`) hands a task to a Claude sub-agent with `ccx run --to claude`
  resume       a sub-agent run started under a task-checkpoint step is killed partway; `ccx task resume` continues it
  undo         a write run, then `ccx undo --apply`: every file back to its bytes before the run
  budget       a parallel task with a tiny `--budget`: the sub-agent's own sub-agents are stopped (kind over_budget)

  python scripts/eval/seven_func.py <check> [--kill-after 25]
  python scripts/eval/seven_func.py summary

Rows go to .ccx/eval/seven/func.jsonl (git-ignored). Tests use fakes and never call this with real CLIs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, append_jsonl, bin_argv, ccx_rows, lead_env, make_repo, read_jsonl, score  # noqa: E402
from tasks import PARALLEL_TASK, by_id  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "seven" / "func.jsonl"
CCX = [sys.executable, str(ROOT / "ccx.py")]
CP = [sys.executable, str(ROOT / "skills" / "task-checkpoint" / "scripts" / "checkpoint.py")]
ACCEPT = "python -m pytest -q"
CHEAP = ["--to", "codex", "--model", "gpt-6-luna", "--effort", "low"]


def sh(argv: list[str], cwd: Path, timeout: int = 900, env: dict | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env or lead_env(), timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -9, "", "timeout"


def last_json(text: str) -> dict:
    for line in reversed((text or "").strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def tree_hash(repo: Path) -> dict[str, str]:
    """sha256 of every file outside .git and .ccx (what a run may change and undo must put back)."""
    out = {}
    for f in sorted(repo.rglob("*")):
        rel = f.relative_to(repo).as_posix()
        if f.is_file() and not rel.startswith((".git/", ".ccx/")) and "__pycache__" not in rel \
                and ".pytest_cache" not in rel:
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass


def ccx_run(repo: Path, label: str, brief: str, extra: list[str]) -> list[str]:
    return [*CCX, "run", "--mode", "write", "--new", "--no-ab", "--force", "--label", label, "--check", ACCEPT,
            *extra, brief]


def check_codex_lead(a, work: Path) -> dict:
    task = by_id("roman")
    repo = make_repo(task, work / "codex-lead")
    label = "eval-7c:func:codex-lead"
    ccx = " ".join(f'"{x}"' for x in CCX)
    prompt = (f"You are the lead agent in this repository.\nTask: {task['brief']}\n"
              f"Acceptance: `{ACCEPT}` must pass. Do not do the work yourself: hand it to Claude with one shell "
              f"command:\n  {ccx} run --from codex --to claude --model haiku --effort low --mode write --new --no-ab "
              f"--force --label {label} --check \"{ACCEPT}\" \"<a short brief>\"\nIt prints a JSON result; ccx "
              "has already re-run the acceptance command (its check field). Then answer DONE or FAILED.")
    argv = [*bin_argv("codex"), "exec", "--json", "-m", a.lead_model, "-c", f'model_reasoning_effort="{a.lead_effort}"',
            *([] if a.lead_sandbox == "config" else ["-s", a.lead_sandbox]), "--skip-git-repo-check",
            "-C", str(repo), "-"]
    t0 = time.time()
    try:
        r = subprocess.run(argv, input=prompt, cwd=repo, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=lead_env(), timeout=900)
        out, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "", -9
    rows = ccx_rows(label)
    rows = [r for r in rows if (r.get("ts") or 0) >= t0 - 5]
    sc = score(repo, task)
    used, cmds, said = [], [], []
    for x in out.splitlines():
        try:
            ev = json.loads(x) if x.startswith("{") else {}
        except json.JSONDecodeError:
            continue
        it = ev.get("item") or {}
        if ev.get("type") == "turn.completed":
            used.append(ev.get("usage"))
        elif ev.get("type") == "item.completed" and it.get("type") == "command_execution":
            cmds.append({"command": str(it.get("command"))[:300], "exit_code": it.get("exit_code"),
                         "output": str(it.get("aggregated_output"))[-300:]})
        elif ev.get("type") == "item.completed" and it.get("type") == "agent_message":
            said.append(str(it.get("text"))[:300])
    return {"check": "codex-lead", "sandbox": a.lead_sandbox, "ok": sc["ok"] and any(r.get("to") == "claude" and r.get("caller") == "codex"
                                                            for r in rows),
            "hidden_ok": sc["ok"], "pytest": sc["pytest"], "rc": rc, "wall_s": round(time.time() - t0, 1),
            "sub_runs": [{k: r.get(k) for k in ("run_id", "caller", "to", "rungs", "ok", "ae_usd", "seconds")}
                         for r in rows], "lead_usage": used, "lead_commands": cmds, "lead_said": said}


def check_resume(a, work: Path) -> dict:
    task = by_id("inventory")
    repo = make_repo(task, work / "resume")
    env = {**lead_env(), "CHECKPOINT_ROOT": str(repo)}
    rc, out, err = sh([*CP, "init", "--title", "7c resume check", "--step", "implement the inventory changes"],
                      repo, env=env)
    tid = (out.strip().splitlines() or [""])[-1].strip()
    label = "eval-7c:func:resume"
    argv = ccx_run(repo, label, task["brief"], [*CHEAP, "--task", tid, "--step", "1", "--review", "off"])
    t0 = time.time()
    proc = subprocess.Popen(argv, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                            start_new_session=os.name != "nt")
    try:
        proc.wait(timeout=a.kill_after)
        killed = False
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        proc.wait()
        killed = True
    before = score(repo, task)
    status_rc, status, _ = sh([*CCX, "task", "status", tid, "--cwd", str(repo)], repo, env=env)
    rc2, out2, err2 = sh([*CCX, "task", "resume", tid, "--cwd", str(repo)], repo, env=env)
    res = last_json(out2)
    after = score(repo, task)
    return {"check": "resume", "ok": killed and not before["ok"] and after["ok"] and bool(res.get("resumed")),
            "task": tid, "killed": killed, "killed_after_s": round(time.time() - t0, 1) if killed else None,
            "hidden_ok_after_kill": before["ok"], "hidden_ok_after_resume": after["ok"], "pytest": after["pytest"],
            "status_after_kill": status[-600:], "resume_rc": rc2, "resumed": res.get("resumed"),
            "resume_status": res.get("status"), "resume_err": err2[-400:],
            "runs": [{k: r.get(k) for k in ("run_id", "rungs", "ok", "kind", "ae_usd", "session_id")}
                     for r in ccx_rows(label)] + [{"resumed_run": res.get("run_id"), "ok": res.get("ok")}]}


def check_undo(a, work: Path) -> dict:
    task = by_id("slugify")
    repo = make_repo(task, work / "undo")
    h0 = tree_hash(repo)
    rc, out, err = sh(ccx_run(repo, "eval-7c:func:undo", task["brief"], [*CHEAP, "--review", "off"]), repo)
    res = last_json(out)
    h1 = tree_hash(repo)
    mid = score(repo, task)
    rid = res.get("run_id", "")
    _, dry, _ = sh([*CCX, "undo", rid], repo)
    _, app, uerr = sh([*CCX, "undo", rid, "--apply"], repo)
    h2 = tree_hash(repo)
    changed = sorted(k for k in set(h0) | set(h1) if h0.get(k) != h1.get(k))
    return {"check": "undo", "ok": bool(changed) and h2 == h0, "run_id": rid, "run_ok": res.get("ok"),
            "hidden_ok_after_run": mid["ok"], "changed_by_run": changed, "restored": h2 == h0,
            "left_different": sorted(k for k in set(h0) | set(h2) if h0.get(k) != h2.get(k)),
            "dry_run": dry[-500:], "apply": app[-500:], "apply_err": uerr[-300:]}


def check_budget(a, work: Path) -> dict:
    task = PARALLEL_TASK
    repo = make_repo(task, work / f"budget-{a.budget_to}")
    pick = ["--to", "claude", "--model", "haiku", "--effort", "low"] if a.budget_to == "claude" else CHEAP
    label = f"eval-7c:func:budget:{a.budget_to}"
    t0 = time.time()
    rc, out, err = sh(ccx_run(repo, label, task["brief"], [*pick, "--parallel", "--budget", str(a.budget),
                                                           "--no-escalate", "--no-fallback", "--review", "off"]),
                      repo)
    res = last_json(out)
    rows = ccx_rows(label)
    return {"check": f"budget-{a.budget_to}", "ok": any(r.get("kind") == "over_budget" for r in rows),
            "budget": a.budget, "kinds": [r.get("kind") for r in rows], "status": res.get("status"),
            "hint": res.get("hint") or res.get("error"), "subagents": res.get("subagents"),
            "ae_usd": sum(r.get("ae_usd") or 0 for r in rows), "wall_s": round(time.time() - t0, 1),
            "hidden_ok": score(repo, task)["ok"], "run_ids": [r["run_id"] for r in rows]}


CHECKS = {"codex-lead": check_codex_lead, "resume": check_resume, "undo": check_undo, "budget": check_budget}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=[*CHECKS, "summary"])
    ap.add_argument("--kill-after", type=float, default=25.0, help="resume: kill the sub-agent after this long (s)")
    ap.add_argument("--budget", type=float, default=0.0001, help="budget: the cap ($)")
    ap.add_argument("--budget-to", choices=["claude", "codex"], default="claude")
    ap.add_argument("--lead-model", default="gpt-6-luna")
    ap.add_argument("--lead-effort", default="low")
    ap.add_argument("--lead-sandbox", default="config",
                    help="codex-lead: config = the user's own Codex setting, or a -s mode such as workspace-write")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else OUT
    if a.check == "summary":
        for r in read_jsonl(out):
            print(f"{r['check']:12} ok={r['ok']}  " + json.dumps({k: v for k, v in r.items()
                                                                if k in ("killed", "restored", "kinds", "sub_runs",
                                                                         "hidden_ok", "hidden_ok_after_resume")},
                                                               ensure_ascii=False)[:300])
        return 0
    row = CHECKS[a.check](a, Path(tempfile.mkdtemp(prefix=f"ccx-7c-{a.check}-")))
    row["ts"] = time.time()
    append_jsonl(out, row)
    print(json.dumps(row, ensure_ascii=False, indent=1))
    return 0 if row["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
