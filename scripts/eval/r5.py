"""Round 5 (docs/research/2026-10-26-r5-plan.md): large tasks from this repository's own history.

Rounds 3-4 showed that on small tasks cheap models are right anyway and a lead makes as many requests whether it
does the work or hands it away. Here every task is a real change in the whole ccx code base (scripts/eval/tasks_r5.py),
so doing it takes many requests. Arms (the lead is a fresh headless Claude Code, sonnet medium, as in round 3):

  self     the lead does it itself
  builtin  the lead must hand the implementation to its built-in sub-agent (Agent tool, a haiku `worker`)
  ccx      the lead must hand it to `ccx run --tradeoff save --review on --context auto`
  direct   no lead: `ccx run` straight to Codex gpt-6-luna low with another vendor's cheap review on
  ccx2     opt-in (--arms ccx2): ccx as the agent-delegate skill now says (verbatim brief, --bg + show --wait,
           default review, trust a passed check, no commit request); not in the default schedule

Every unit: the repository at the task commit's parent, with today's tests/conftest.py committed into it (old
commits' tests may predate per-test hubs, #73), a fresh throwaway hub (CCX_HUB, as round 3). The hidden test is the
commit's own test files, run in a throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR.

  python scripts/eval/r5.py run --rounds 1 --tasks waiting-evals --budget 3      # the pilot
  python scripts/eval/r5.py run --rounds 2 --budget 40
  python scripts/eval/r5.py run --rounds 2 --arms ccx,ccx2 --tag r5b --budget 20  # old vs new lead guidance
  python scripts/eval/r5.py summary
  python scripts/eval/r5.py export docs/research/data/2026-10-26-r5.json
"""
from __future__ import annotations

import argparse
import io
import json
import random
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2  # noqa: E402
import r3  # noqa: E402
import r4  # noqa: E402
from common import ROOT, append_jsonl, archive_hub, git, lead_env, read_jsonl  # noqa: E402
from tasks_r5 import IDS, by_id  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "r5"
ARMS = ("self", "builtin", "ccx", "direct")
CONFTEST = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
LEAD_PROMPT = """You are the lead agent on this repository: relayline, the `ccx` command (Python, standard library only;
see AGENTS.md). The full test suite takes about 7 minutes, so run the tests that matter for your change, e.g.
`python -m pytest -q tests/test_<area>.py`. The person asked:

{brief}

{how}

When the work is done and the relevant tests pass, end with one line: DONE: <what changed>."""
HOW_CCX = ("Do not edit files yourself: hand the implementation to a sub-agent through ccx. Run\n"
           "  {ccx} run --tradeoff save --review on --context auto --mode write --new --no-ab --label {label} "
           "--check \"<a pytest command for the relevant test files>\" \"<a brief that contains everything it needs>\"\n"
           "It prints one JSON object (run_id, ok, summary, check, review, ...). When it reports back, check the "
           "result (read the diff, run the tests); if something is wrong or missing, send it back with\n"
           "  {ccx} resume <run_id> \"<what to fix>\"")
# ccx2 (opt-in, `--arms ccx2`): the lead follows the agent-delegate skill's "Delegate cheaply" guidance written
# after round 5 (verbatim brief, --bg + show --wait, default review, trust a passed check, no commit request)
HOW_CCX2 = ("Do not edit files yourself: hand the implementation to a sub-agent through ccx. Run\n"
            "  {ccx} run --bg --tradeoff save --context auto --mode write --new --no-ab --label {label} "
            "--check \"<a pytest command for the relevant test files>\" \"<brief>\"\n"
            "then wait for it with\n"
            "  {ccx} show <run_id> --wait\n"
            "and call that again while it says the run is still running (never resume a running run; do not pipe ccx "
            "output through tail or head). The brief is the person's request above copied verbatim (do not re-word "
            "interfaces, names, strings or numbers), plus file paths you already know and the acceptance command; do "
            "not read the code base first to write it, and do not ask the sub-agent to commit. When the result's "
            "check passed and its files_changed / diffstat fit the request, accept it without re-running the tests "
            "or reading the full diff; only if the check failed or is missing, or the status is partial or blocked, "
            "look yourself and send it back with\n"
            "  {ccx} resume <run_id> \"<what to fix>\"\n"
            "After accepting, commit the work yourself.")
CCX_ARMS = ("ccx", "ccx2")
OPT_IN_ARMS = ("ccx2",)        # not in ARMS: the default schedule (and its done-keys for old tags) stays the same
DIRECT = ["--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--review", "on", "--context", "off",
          "--no-escalate", "--no-fallback"]


def make_repo(task: dict, dest: Path) -> None:
    """The repository at the commit's parent, today's conftest committed into it."""
    r2._rmtree(dest)
    dest.mkdir(parents=True)
    data = subprocess.run(["git", "archive", f"{task['commit']}^"], cwd=ROOT, capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(data)).extractall(dest)
    (dest / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "start")


def iso_env(d: Path) -> dict:
    env = {k: v for k, v in lead_env().items() if not k.endswith(("_API_KEY", "_AUTH_TOKEN"))
           and not k.startswith(("CCX_", "CLAUDE", "CODEX"))}
    for var, sub in (("CCX_HUB", "hub"), ("CODEX_HOME", "codex-home"), ("CLAUDE_CONFIG_DIR", "claude-home"),
                     ("HOME", "home"), ("USERPROFILE", "home")):
        (d / sub).mkdir(parents=True, exist_ok=True)
        env[var] = str(d / sub)
    env["CCX_CONFIG"] = str(d / "user-config.toml")
    return env


def score(repo: Path, task: dict, work: Path) -> dict:
    """The commit's own test files (overwriting whatever the agent left in them), in throwaway homes."""
    for t in task["tests"]:
        body = subprocess.run(["git", "show", f"{task['commit']}:{t}"], cwd=ROOT, capture_output=True, check=True).stdout
        (repo / t).parent.mkdir(parents=True, exist_ok=True)
        (repo / t).write_bytes(body)
    (repo / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    iso = Path(tempfile.mkdtemp(prefix="r5iso-", dir=work))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *task["tests"]], cwd=repo,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           env=iso_env(iso))
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        return {"ok": r.returncode == 0, "pytest": tail[:200]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "pytest": "timeout"}
    finally:
        r2._rmtree(iso)


def changed(repo: Path) -> dict:
    """What changed since the start commit, committed or not (leads follow AGENTS.md and commit their work)."""
    start = git(repo, "rev-list", "--max-parents=0", "HEAD").split()[0]
    git(repo, "add", "-A", "-N")
    files = [x for x in git(repo, "diff", "--name-only", start).splitlines() if x.strip()]
    return {"files_changed": len(files), "diffstat": git(repo, "diff", "--shortstat", start).strip(),
            "commits": len(git(repo, "rev-list", f"{start}..HEAD").split())}


def lead_how(arm: str, label: str) -> str:
    """What the lead is told about how to do the work, per arm."""
    if arm == "ccx":
        return HOW_CCX.format(ccx=r3.CCX_CMD, label=label)
    if arm == "ccx2":
        return HOW_CCX2.format(ccx=r3.CCX_CMD, label=label)
    return r3.HOW[arm]


def lead_unit(u: dict, a, work: Path, repo: Path, hub: Path) -> dict:
    task = by_id(u["task"])
    env = {**lead_env(), "CCX_HUB": str(hub), "CCX_NO_QUOTA_PROBE": "1", "BASH_DEFAULT_TIMEOUT_MS": "900000",
           "BASH_MAX_TIMEOUT_MS": "1200000"}
    is_ccx = u["arm"] in CCX_ARMS
    how = lead_how(u["arm"], u["label"])
    prompt = LEAD_PROMPT.format(brief=task["brief"], how=how)
    t0 = time.time()
    try:
        # ccx2 needs the same lead flags as ccx (a session file for --context auto)
        r = subprocess.run(r3.lead_argv("ccx" if is_ccx else u["arm"], a.lead_budget), input=prompt, cwd=repo, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=a.timeout)
        out, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc = -9
    wall = round(time.time() - t0, 1)
    key = f"{u['round']}-{u['task']}-{u['arm']}"
    (work / f"{key}.stream.jsonl").write_text(out, encoding="utf-8")
    fin = r3.last_result(out)
    lm = r3.lead_metrics(out)
    cost = r2.hub_cost(hub)
    by_model = r3.model_split(fin.get("modelUsage") or {})
    lead_usd = float(fin.get("total_cost_usd") or 0)
    row = {"rc": rc, "wall_s": wall, "subtype": fin.get("subtype"), "lead_usd": round(lead_usd, 6),
           "by_model_usd": by_model, "ccx_usd": cost["usd"], "ccx_review_usd": cost["review_usd"],
           "ccx_agents": cost["agents"], "ccx_run_ids": cost["run_ids"], "usd": round(lead_usd + cost["usd"], 6), **lm}
    row["sub_usd"] = round(sum(v for m, v in by_model.items() if r3.WORKER_MODEL in m), 6) if u["arm"] == "builtin" \
        else cost["usd"]
    row["lead_only_usd"] = round(row["usd"] - row["sub_usd"], 6)
    ccx_runs = len([x for x in cost["run_ids"] if not str(x).startswith("review")])
    row["delegated"] = bool(lm["agent_calls"]) if u["arm"] == "builtin" else bool(cost["run_ids"]) \
        if is_ccx else None
    row["rework"] = max(0, lm["agent_calls"] - 1) if u["arm"] == "builtin" else \
        (lm["ccx_resumes"] + max(0, lm["ccx_runs"] - 1)) if is_ccx else 0
    row["ccx_ledger_rows"] = ccx_runs
    if is_ccx:
        row["context_attached"] = sum((hub / "ccx" / "runs" / str(rid) / "shared-context.md").exists()
                                      for rid in cost["run_ids"])
    return row


def direct_unit(u: dict, a, repo: Path, hub: Path) -> dict:
    task = by_id(u["task"])
    argv = ["run", "--mode", "write", "--new", "--no-ab", "--force", "--label", u["label"], "--minutes", "60",
            *DIRECT, task["brief"]]
    t0 = time.time()
    res, rc, wall, err = r2.ccx(argv, repo, hub, a.timeout)
    cost = r2.hub_cost(hub)
    rec = r2.record(hub, res.get("run_id"))
    return {"rc": rc, "wall_s": round(time.time() - t0, 1), "usd": cost["usd"], "ccx_usd": cost["usd"],
            "ccx_review_usd": cost["review_usd"], "ccx_run_ids": cost["run_ids"], "model": res.get("model"),
            "status": res.get("status"), "ccx_ok": res.get("ok"),
            "verdicts": [v.get("verdict") for v in (rec.get("first_review"), rec.get("review")) if v],
            "stderr": err if rc else ""}


def run_unit(u: dict, a, work: Path) -> dict:
    task = by_id(u["task"])
    key = f"{u['round']}-{u['task']}-{u['arm']}"
    repo, hub = work / key, work / f"h-{key}"
    r2._rmtree(hub)
    make_repo(task, repo)
    hinfo = r3.make_hub(hub)
    row = direct_unit(u, a, repo, hub) if u["arm"] == "direct" else lead_unit(u, a, work, repo, hub)
    row.update(changed(repo))
    sc = score(repo, task, work)
    row.update({**u, "ok": sc["ok"], "pytest": sc["pytest"], "hub": hinfo})
    for rid in row.get("ccx_run_ids") or []:
        r2.verify(hub, rid, bool(sc["ok"]), sc["pytest"])
    row["archived_sessions"] = archive_hub(hub)
    return row


def schedule(rounds: int, seed: int, tasks: list[str], arms: list[str]) -> list[dict]:
    out = []
    for rd in range(1, rounds + 1):
        rnd = random.Random(f"{seed}:r5:{rd}")
        ts = list(tasks)
        rnd.shuffle(ts)
        for t in ts:
            arm_list = list(arms)
            rnd.shuffle(arm_list)
            out += [{"exp": "r5", "round": rd, "task": t, "arm": arm} for arm in arm_list]
    return out


def spent(f: Path) -> float:
    return round(sum(r.get("usd") or 0 for r in read_jsonl(f)), 4)


def cmd_run(a) -> int:
    out = Path(a.out) if a.out else OUT / "results.jsonl"
    work = Path(a.workdir or (Path(tempfile.gettempdir()) / "r5"))
    work.mkdir(parents=True, exist_ok=True)
    arms = a.arms.split(",") if a.arms else list(ARMS)
    bad = [x for x in arms if x not in (*ARMS, *OPT_IN_ARMS)]
    if bad:
        raise SystemExit(f"unknown arm(s): {', '.join(bad)} (known: {', '.join((*ARMS, *OPT_IN_ARMS))})")
    done = {(r["tag"], r["round"], r["task"], r["arm"]) for r in read_jsonl(out)}
    todo = []
    for u in schedule(a.rounds, a.seed, a.tasks.split(",") if a.tasks else IDS, arms):
        u = {**u, "tag": a.tag, "seed": a.seed, "label": f"eval-r5:{a.tag}:{u['round']}:{u['task']}:{u['arm']}"}
        if (a.tag, u["round"], u["task"], u["arm"]) not in done:
            todo.append(u)
    print(f"work dir: {work}  results: {out}  units: {len(todo)}", flush=True)
    if a.dry_run:
        for u in todo:
            print(f"[dry] {u['label']}")
        return 0
    lock, stop = threading.Lock(), threading.Event()

    def one(u):
        with lock:
            total = spent(out) + a.extra_spent
            if stop.is_set() or total >= a.budget:
                if not stop.is_set():
                    print(f"budget ${a.budget} reached (${total:.3f}): stopping", flush=True)
                stop.set()
                return
        try:
            row = run_unit(u, a, work)
        except Exception as e:  # noqa: BLE001 — one broken unit is recorded, the batch goes on
            row = {**u, "ok": False, "error": f"{type(e).__name__}: {e}"[:400], "usd": 0.0, "wall_s": 0}
        row["ts"] = time.time()
        with lock:
            append_jsonl(out, row)
            print(f"r{u['round']} {u['task']:18} {u['arm']:8} ok={row.get('ok')} ${row.get('usd', 0):.4f} "
                  f"(lead ${row.get('lead_only_usd', 0) or 0:.4f}) req={row.get('lead_requests')} "
                  f"lead_tok={row.get('lead_tokens')} {row.get('wall_s')}s deleg={row.get('delegated')} "
                  f"files={row.get('files_changed')} total=${spent(out) + a.extra_spent:.3f}", flush=True)

    # units of one task run one after another (arms in their shuffled order); --jobs tasks at a time
    groups: dict[tuple, list[dict]] = {}
    for u in todo:
        groups.setdefault((u["round"], u["task"]), []).append(u)
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(lambda us: [one(u) for u in us], groups.values()))
    return 2 if stop.is_set() else 0


def summarize(rows: list[dict]) -> dict:
    rows = [r for r in rows if "error" not in r]
    out = {}
    for arm in (*ARMS, *OPT_IN_ARMS):
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        med = lambda k: sorted(r.get(k) or 0 for r in rs)[len(rs) // 2]  # noqa: E731
        ok = sum(bool(r.get("ok")) for r in rs)
        out[arm] = {"ok": ok, "n": len(rs), "usd": round(sum(r.get("usd") or 0 for r in rs), 4),
                    "cps": round(sum(r.get("usd") or 0 for r in rs) / ok, 4) if ok else None,
                    "lead_only_usd_med": med("lead_only_usd"), "lead_tokens_med": med("lead_tokens"),
                    "lead_requests_med": med("lead_requests"), "wall_med": med("wall_s")}
    return {"arms": out, "long_style": r4.summarize_long([{**r, "arm": r["arm"]} for r in rows
                                                          if r["arm"] in r4.LONG_ARMS])["paired"]}


def cmd_summary(a) -> int:
    print(json.dumps(summarize(read_jsonl(OUT / "results.jsonl")), ensure_ascii=False, indent=1))
    return 0


def cmd_export(a) -> int:
    keep = ("tag", "round", "task", "arm", "ok", "pytest", "rc", "wall_s", "usd", "lead_usd", "lead_only_usd",
            "sub_usd", "by_model_usd", "ccx_usd", "ccx_review_usd", "ccx_agents", "lead_requests", "lead_tokens",
            "lead_output_tokens", "lead_tools", "lead_edits", "agent_calls", "ccx_runs", "ccx_resumes", "rework",
            "delegated", "context_attached", "files_changed", "diffstat", "model", "status", "verdicts", "error")
    rows = read_jsonl(OUT / "results.jsonl")
    data = {"summary": summarize(rows), "rows": [r3.scrub({k: r[k] for k in keep if k in r}) for r in rows]}
    Path(a.dest).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {a.dest}: {len(rows)} rows")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag", default="r5")
    r.add_argument("--seed", type=int, default=53)
    r.add_argument("--rounds", type=int, default=2)
    r.add_argument("--tasks", default="")
    r.add_argument("--arms", default="")
    r.add_argument("--budget", type=float, default=3.0, help="stop before a new unit once the results reach $")
    r.add_argument("--extra-spent", type=float, default=0.0)
    r.add_argument("--jobs", type=int, default=2, help="tasks run at the same time")
    r.add_argument("--lead-budget", type=float, default=3.0, help="claude -p --max-budget-usd for one lead")
    r.add_argument("--out", default="")
    r.add_argument("--workdir", default="")
    r.add_argument("--timeout", type=int, default=2400)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("summary")
    s.set_defaults(fn=cmd_summary)
    e = sub.add_parser("export")
    e.add_argument("dest")
    e.set_defaults(fn=cmd_export)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
