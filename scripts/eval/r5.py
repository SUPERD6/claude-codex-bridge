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
  builtin2 opt-in (--arms builtin2): builtin's Agent-tool hand-off with ccx2's brief and acceptance wording, word
           for word (the worker reports check / files_changed / diffstat / status); not in the default schedule

Every unit: the repository at the task commit's parent, with today's tests/conftest.py committed into it (old
commits' tests may predate per-test hubs, #73), a fresh throwaway hub (CCX_HUB, as round 3). The hidden test is the
commit's own test files, run in a throwaway HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR.

Clean environment (scripts/eval/preflight.py, after round 5h): `run` first checks the machine and refuses to start
when anything fails (another eval or pytest running, modified tracked files, no dedicated Codex home for arms that use
Codex, a work dir with foreign files, a canary lead that sees user-level instructions, ...); `--force-unclean` runs
anyway and every row records it. Each unit then gets its own clean room: an allow-listed environment, its own TMP,
git identity, CCX_CONFIG and DSH_HOME, Claude leads and sub-agents without the user's settings, hooks, CLAUDE.md and
auto-memory and with reads of the real homes denied (`--claude-isolation config-dir`: a fresh CLAUDE_CONFIG_DIR),
Codex in a dedicated CODEX_HOME with --ignore-user-config / --ignore-rules / memories off; everything it starts runs
in one Job Object and whatever survives the unit is listed, killed and logged. Every row carries `fingerprint`
(commit, task-file hash, CLI versions, isolation, concurrency, preflight result), `audit` (what its agents loaded and
which real paths their tool calls named), `leftovers` and `env_clean`. The CLI versions are checked again after
every unit; a change, a busy machine or a process that cannot be killed stops the run (unless --force-unclean).
The work dir defaults to <temp>/<tag>, so two tags never share unit folders.

  python scripts/eval/r5.py run --rounds 1 --tasks waiting-evals --codex-home <eval codex home> --budget 3

  python scripts/eval/r5.py run --rounds 1 --tasks waiting-evals --budget 3      # the pilot
  python scripts/eval/r5.py run --rounds 2 --budget 40
  python scripts/eval/r5.py run --rounds 2 --arms ccx,ccx2 --tag r5b --budget 20  # old vs new lead guidance
  python scripts/eval/r5.py run --rounds 2 --arms ccx2,builtin2 --tag r5d --budget 25  # same wording, ccx vs Agent
  python scripts/eval/r5.py run --taskset holdout --rounds 3 --tag ho1 --budget 20   # the unseen hold-out set (C1)
  python scripts/eval/r5.py summary [--taskset holdout]
  python scripts/eval/r5.py export docs/research/data/2026-10-26-r5.json

Hold-out (--taskset holdout, scripts/eval/tasks_holdout.py): 10 other past changes never used while tuning, for the
final claims. Its results go to their own file, and every finished unit's repository, hub and lead stream leave the
work dir after scoring (the stream is kept under .ccx/eval/r5/streams/<tag>/), so a later round's agents cannot find
an earlier round's finished answer next to them. r5 keeps its old behaviour.
"""
from __future__ import annotations

import argparse
import io
import json
import os
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
import preflight as PF  # noqa: E402
from common import ROOT, append_jsonl, archive_hub, ccx_verify, git, read_jsonl  # noqa: E402
import tasks_holdout  # noqa: E402
import tasks_r5  # noqa: E402

# r5: the 10 tasks the loop was tuned on; holdout (scripts/eval/tasks_holdout.py): 10 others never used for tuning,
# for the final claims (backlog C1). r5 stays the default everywhere.
TASKSETS = {"r5": tasks_r5, "holdout": tasks_holdout}
IDS = tasks_r5.IDS

OUT = ROOT / ".ccx" / "eval" / "r5"


def by_id(task_id: str) -> dict:
    """A task of any task set (ids are unique across sets)."""
    for mod in TASKSETS.values():
        if task_id in mod.IDS:
            return mod.by_id(task_id)
    raise KeyError(f"unknown task: {task_id}")


def results_file(taskset: str) -> Path:
    """Where a task set's results go by default: r5 keeps its old file, the hold-out set has its own."""
    return OUT / ("results.jsonl" if taskset == "r5" else f"{taskset}-results.jsonl")


def pytest_args(task: dict) -> list[str]:
    """The hidden test files, minus the tests a task deselects (unrelated to it and flaky under load)."""
    out = list(task["tests"])
    for node in task.get("deselect") or ():
        out += ["--deselect", node]
    return out
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
# The brief and acceptance guidance is shared word for word with builtin2, so the two differ only in how the work
# is handed away (ccx vs the Agent tool). LEAN_ACCEPT's {send_back} is filled per arm.
LEAN_BRIEF = ("The brief is the person's request above copied verbatim (do not re-word interfaces, names, strings or "
              "numbers), plus file paths you already know and the acceptance command; do not read the code base "
              "first to write it, and do not ask the sub-agent to commit.")
LEAN_ACCEPT = ("When the result's check passed and its files_changed / diffstat fit the request, accept it without "
               "re-running the tests or reading the full diff; only if the check failed or is missing, or the status "
               "is partial or blocked, look yourself and send it back with\n"
               "  {send_back}\n"
               "After accepting, commit the work yourself.")
HOW_CCX2 = ("Do not edit files yourself: hand the implementation to a sub-agent through ccx. Run\n"
            "  {ccx} run --bg --tradeoff save --context auto --mode write --new --no-ab --label {label} "
            "--check \"<a pytest command for the relevant test files>\" \"<brief>\"\n"
            "then wait for it with\n"
            "  {ccx} show <run_id> --wait\n"
            "and call that again while it says the run is still running (never resume a running run; do not pipe ccx "
            "output through tail or head). " + LEAN_BRIEF + " "
            + LEAN_ACCEPT.replace("{send_back}", "{ccx} resume <run_id> \"<what to fix>\""))
# builtin2 (opt-in, `--arms builtin2`): builtin's Agent-tool hand-off with ccx2's lean brief and acceptance, so a
# ccx2 vs builtin win is not just the instruction. The worker runs the acceptance command itself and reports what a
# ccx result carries (check, files_changed, diffstat, status).
HOW_BUILTIN2 = ("Do not edit files yourself: hand the implementation to your sub-agent. Call the Agent tool with "
                "subagent_type `worker` and the brief, and tell the worker to run the acceptance command (a pytest "
                "command for the relevant test files) when it is done and to report its status (done, partial or "
                "blocked), that command's result line (the check), the files it changed (files_changed) and "
                "`git diff --shortstat` (diffstat). " + LEAN_BRIEF + " "
                + LEAN_ACCEPT.replace("{send_back}", "another Agent call to the worker, saying what to fix"))
CCX_ARMS = ("ccx", "ccx2")
BUILTIN_ARMS = ("builtin", "builtin2")
OPT_IN_ARMS = ("ccx2", "builtin2")   # not in ARMS: the default schedule (and its done-keys for old tags) stays the same
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
    env = {k: v for k, v in PF.base_env().items() if not k.endswith(PF.ENV_KEEP_SUFFIX)
           and not k.startswith(("CCX_", "CLAUDE", "CODEX"))}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env.update({"TMP": str(d / "tmp"), "TEMP": str(d / "tmp"), "TMPDIR": str(d / "tmp"), "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(d / "gitconfig")})
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    (d / "gitconfig").write_text("[user]\n\tname = eval\n\temail = eval@example.invalid\n", encoding="utf-8")
    for var, sub in (("CCX_HUB", "hub"), ("CODEX_HOME", "codex-home"), ("CLAUDE_CONFIG_DIR", "claude-home"),
                     ("HOME", "home"), ("USERPROFILE", "home")):
        (d / sub).mkdir(parents=True, exist_ok=True)
        env[var] = str(d / sub)
    env["CCX_CONFIG"] = str(d / "user-config.toml")
    return env


def score(repo: Path, task: dict, work: Path, job: PF.Job | None = None) -> dict:
    """The commit's own test files (overwriting whatever the agent left in them), in throwaway homes."""
    for t in task["tests"]:
        body = subprocess.run(["git", "show", f"{task['commit']}:{t}"], cwd=ROOT, capture_output=True, check=True).stdout
        (repo / t).parent.mkdir(parents=True, exist_ok=True)
        (repo / t).write_bytes(body)
    (repo / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    iso = Path(tempfile.mkdtemp(prefix="r5iso-", dir=work))
    try:
        out, _err, rc, _left = PF.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *pytest_args(task)],
                                      cwd=repo, env=iso_env(iso), timeout=900, job=job)
        if rc == -9:
            return {"ok": False, "pytest": "timeout"}
        tail = (out.strip().splitlines() or [""])[-1]
        return {"ok": rc == 0, "pytest": tail[:200]}
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
    if arm == "builtin2":
        return HOW_BUILTIN2
    return r3.HOW[arm]


def lead_flags_arm(arm: str) -> str:
    """The round-3 arm whose lead command line (tools, agents, session file) this arm uses."""
    return "ccx" if arm in CCX_ARMS else "builtin" if arm in BUILTIN_ARMS else arm


def lead_unit(u: dict, a, work: Path, repo: Path, hub: Path, iso: PF.Unit | None = None, env: dict | None = None,
              job: PF.Job | None = None) -> dict:
    task = by_id(u["task"])
    env = {**(env or PF.base_env()), "CCX_HUB": str(hub), "CCX_NO_QUOTA_PROBE": "1",
           "BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000"}
    is_ccx, is_builtin = u["arm"] in CCX_ARMS, u["arm"] in BUILTIN_ARMS
    how = lead_how(u["arm"], u["label"])
    prompt = LEAD_PROMPT.format(brief=task["brief"], how=how)
    t0 = time.time()
    # ccx2 / builtin2 need the same lead flags as ccx / builtin (a session file; the Agent tool and worker); the
    # clean-room flags (no user settings, hooks, CLAUDE.md, auto-memory; deny rules) come from preflight
    argv = r3.lead_argv(lead_flags_arm(u["arm"]), a.lead_budget) + (PF.lead_flags(iso) if iso else [])
    out, _err, rc, _left = PF.run(argv, input=prompt, cwd=repo, env=env, timeout=a.timeout, job=job)
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
    row["sub_usd"] = round(sum(v for m, v in by_model.items() if r3.WORKER_MODEL in m), 6) if is_builtin \
        else cost["usd"]
    row["lead_only_usd"] = round(row["usd"] - row["sub_usd"], 6)
    ccx_runs = len([x for x in cost["run_ids"] if not str(x).startswith("review")])
    row["delegated"] = bool(lm["agent_calls"]) if is_builtin else bool(cost["run_ids"]) \
        if is_ccx else None
    row["rework"] = max(0, lm["agent_calls"] - 1) if is_builtin else \
        (lm["ccx_resumes"] + max(0, lm["ccx_runs"] - 1)) if is_ccx else 0
    row["ccx_ledger_rows"] = ccx_runs
    if is_ccx:
        row["context_attached"] = sum((hub / "ccx" / "runs" / str(rid) / "shared-context.md").exists()
                                      for rid in cost["run_ids"])
    return row


def direct_unit(u: dict, a, repo: Path, hub: Path, env: dict | None = None, job: PF.Job | None = None) -> dict:
    task = by_id(u["task"])
    argv = ["run", "--mode", "write", "--new", "--no-ab", "--force", "--label", u["label"], "--minutes", "60",
            *DIRECT, task["brief"]]
    t0 = time.time()
    out, err, rc, _left = PF.run([sys.executable, str(ROOT / "ccx.py"), *argv], cwd=repo,
                                 env={**(env or PF.base_env()), "CCX_HUB": str(hub)}, timeout=a.timeout, job=job)
    res, err = r2.S._last_json(out), ("timeout" if rc == -9 else err[-400:])
    cost = r2.hub_cost(hub)
    rec = r2.record(hub, res.get("run_id"))
    return {"rc": rc, "wall_s": round(time.time() - t0, 1), "usd": cost["usd"], "ccx_usd": cost["usd"],
            "ccx_review_usd": cost["review_usd"], "ccx_run_ids": cost["run_ids"], "model": res.get("model"),
            "status": res.get("status"), "ccx_ok": res.get("ok"),
            "verdicts": [v.get("verdict") for v in (rec.get("first_review"), rec.get("review")) if v],
            "stderr": err if rc else ""}


def unit_of(u: dict, a, work: Path) -> PF.Unit:
    key = f"{u['round']}-{u['task']}-{u['arm']}"
    return PF.Unit(key=key, work=work, repo=work / key, hub=work / f"h-{key}", label=u["label"],
                   claude=a.claude_isolation, codex_home=Path(a.codex_home).expanduser() if a.codex_home else None,
                   dsh=a.dsh_home, agents=tuple(r3.WORKER))


def unit_models(u: dict, row: dict) -> dict:
    """The models this unit was meant to use, and the ones its streams and ledger show it did use."""
    out = {"lead": r3.LEAD_MODEL, "lead_effort": r3.LEAD_EFFORT, "builtin_worker": r3.WORKER_MODEL}
    if u["arm"] == "direct":
        out = {"direct": " ".join(DIRECT)}
    seen = ((row.get("audit") or {}).get("init") or {}).get("model")
    if seen:
        out["lead_seen"] = seen
    if row.get("by_model_usd"):
        out["billed"] = sorted(row["by_model_usd"])
    return out


def run_unit(u: dict, a, work: Path) -> dict:
    """One unit in its clean room. Whatever happens inside, its leftovers are cleaned and recorded and the row
    carries the fingerprint (an error is a field of the row, not a lost row)."""
    task = by_id(u["task"])
    iso = unit_of(u, a, work)
    repo, hub = iso.repo, iso.hub
    rep = getattr(a, "preflight", None)
    stream = work / f"{iso.key}.stream.jsonl"
    stream.unlink(missing_ok=True)              # an earlier, unfinished try of this unit must not be audited
    row: dict = {**u}
    env = None
    before, job = PF.snapshot(), PF.Job()
    try:
        r2._rmtree(hub)
        make_repo(task, repo)
        hinfo = r3.make_hub(hub)
        hinfo["memory_empty"] = PF.hub_memory_empty(hub)
        row["hub"] = hinfo
        env = PF.prepare(iso)
        row.update(direct_unit(u, a, repo, hub, env, job) if u["arm"] == "direct" else
                   lead_unit(u, a, work, repo, hub, iso, env, job))
        row.update(changed(repo))
        sc = score(repo, task, work, job)
        row.update({**u, "ok": sc["ok"], "pytest": sc["pytest"], "hub": hinfo})
        for rid in row.get("ccx_run_ids") or []:
            ccx_verify(rid, bool(sc["ok"]), f"eval-r2 hidden acceptance: {sc['pytest']}", hub=hub, env=env)
        row["archived_sessions"] = archive_hub(hub, env=env)
    except Exception as e:  # noqa: BLE001 — recorded in the row; the clean-up below still runs
        row.update({"ok": False, "error": f"{type(e).__name__}: {e}"[:400]})
        row.setdefault("usd", 0.0)
        row.setdefault("wall_s", 0)
    finally:
        try:
            row["audit"] = PF.audit(iso, stream.read_text(encoding="utf-8") if stream.exists() else "")
        except Exception as e:  # noqa: BLE001
            row["audit"] = {"clean": False, "problems": [f"audit failed: {type(e).__name__}: {e}"[:200]],
                            "session_ids": []}
        fresh = u.get("taskset", "r5") != "r5"     # hold-out: nothing of a finished unit stays in the work dir
        if fresh and stream.exists():
            keep = OUT / "streams" / str(u.get("tag") or "untagged")
            keep.mkdir(parents=True, exist_ok=True)
            os.replace(stream, keep / stream.name)
        row["leftovers"] = PF.after_unit(iso, before, job, row["audit"].get("session_ids") or [], keep_repo=not fresh)
    if rep:
        row["fingerprint"] = PF.fingerprint(rep, iso, env, unit_models(u, row))
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
    out = Path(a.out) if a.out else results_file(a.taskset)
    ids = TASKSETS[a.taskset].IDS
    tasks = a.tasks.split(",") if a.tasks else ids
    bad_t = [x for x in tasks if x not in ids]
    if bad_t:
        raise SystemExit(f"unknown task(s) in task set {a.taskset}: {', '.join(bad_t)} (known: {', '.join(ids)})")
    work = Path(a.workdir or (Path(tempfile.gettempdir()) / a.tag))
    arms = a.arms.split(",") if a.arms else list(ARMS)
    bad = [x for x in arms if x not in (*ARMS, *OPT_IN_ARMS)]
    if bad:
        raise SystemExit(f"unknown arm(s): {', '.join(bad)} (known: {', '.join((*ARMS, *OPT_IN_ARMS))})")
    done = {(r["tag"], r["round"], r["task"], r["arm"]) for r in read_jsonl(out)}
    todo = []
    for u in schedule(a.rounds, a.seed, tasks, arms):
        u = {**u, "tag": a.tag, "seed": a.seed, "taskset": a.taskset,
             "label": f"eval-r5:{a.tag}:{u['round']}:{u['task']}:{u['arm']}"}
        if (a.tag, u["round"], u["task"], u["arm"]) not in done:
            todo.append(u)
    print(f"work dir: {work}  results: {out}  units: {len(todo)}", flush=True)
    if a.dry_run:
        for u in todo:
            print(f"[dry] {u['label']}")
        return 0
    rep = PF.run_checks(PF.options_from(a, arms, work, canary_on=not a.no_canary, start=True,
                                        tasks_file=Path(TASKSETS[a.taskset].__file__)))
    for p in rep["problems"]:
        print(f"[preflight] {p}", flush=True)
    if not rep["ok"] and not a.force_unclean:
        print("preflight failed: not starting (fix the above, or --force-unclean to run anyway; it is recorded)",
              flush=True)
        return 3
    work.mkdir(parents=True, exist_ok=True)
    (work / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[preflight] {rep['result']}: commit {rep['commit'][:12]} cli {rep['cli']} codex {rep['codex']['mode']} "
          f"claude {rep['claude_isolation']} jobs {a.jobs} canary {rep['canary']}", flush=True)
    a.preflight = rep
    need_codex = any(x in PF.CODEX_ARMS for x in arms)
    ours = [PF._norm(work), PF._norm(f"eval-r5:{a.tag}:")]
    watch = PF.Watch(ours).start()
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
        if "fingerprint" not in row:
            row["fingerprint"] = PF.fingerprint(rep, None, None)
        between = PF.between_units(rep, need_codex, ours, watch.take())
        if between:
            row["between_units"] = between
        row["env_clean"] = PF.env_clean(row, rep)
        why = list(between)
        if (row.get("leftovers") or {}).get("unkilled"):
            why.append(f"processes that could not be killed: {row['leftovers']['unkilled']}")
        if why and not a.force_unclean:
            print(f"stopping: {'; '.join(why)[:400]}", flush=True)
            stop.set()
        with lock:
            append_jsonl(out, row)
            print(f"r{u['round']} {u['task']:18} {u['arm']:8} ok={row.get('ok')} ${row.get('usd', 0):.4f} "
                  f"(lead ${row.get('lead_only_usd', 0) or 0:.4f}) req={row.get('lead_requests')} "
                  f"lead_tok={row.get('lead_tokens')} {row.get('wall_s')}s deleg={row.get('delegated')} "
                  f"files={row.get('files_changed')} clean={row['env_clean']} total=${spent(out) + a.extra_spent:.3f}",
                  flush=True)

    # units of one task run one after another (arms in their shuffled order); --jobs tasks at a time
    groups: dict[tuple, list[dict]] = {}
    for u in todo:
        groups.setdefault((u["round"], u["task"]), []).append(u)
    try:
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            list(ex.map(lambda us: [one(u) for u in us], groups.values()))
    finally:
        watch.close()
    # the person's own state, by size and count only: the hub ledger must not have grown, no Claude session folder
    # named after this work dir may be left in the real ~/.claude
    rep["real_state_after"] = post = PF.real_state(PF.real_paths(), work)
    rep["postflight"] = "same" if post == rep["real_state"] else "changed"
    (work / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if post != rep["real_state"]:
        print(f"[postflight] the person's own state changed: {rep['real_state']} -> {post}", flush=True)
        return 4
    return 2 if stop.is_set() else 0


def summarize(rows: list[dict]) -> dict:
    unclean = sum(r.get("env_clean") is False for r in rows if "error" not in r)
    unknown = sum("env_clean" not in r for r in rows if "error" not in r)    # rows from before the clean room
    tags = sorted({str(r.get("tag")) for r in rows})
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
    return {"arms": out, "unclean_rows": unclean, "env_unknown_rows": unknown, "tags": tags,
            "long_style": r4.summarize_long([{**r, "arm": r["arm"]} for r in rows
                                                          if r["arm"] in r4.LONG_ARMS])["paired"]}


def tagged(rows: list[dict], tag: str | None) -> list[dict]:
    """Rows of one tag (round), so rounds run under different conditions are never counted together."""
    return [r for r in rows if not tag or r.get("tag") == tag]


def cmd_summary(a) -> int:
    print(json.dumps(summarize(tagged(read_jsonl(results_file(a.taskset)), a.tag)), ensure_ascii=False, indent=1))
    return 0


def cmd_export(a) -> int:
    keep = ("tag", "taskset", "round", "task", "arm", "ok", "pytest", "rc", "wall_s", "usd", "lead_usd", "lead_only_usd",
            "sub_usd", "by_model_usd", "ccx_usd", "ccx_review_usd", "ccx_agents", "lead_requests", "lead_tokens",
            "lead_output_tokens", "lead_tools", "lead_edits", "agent_calls", "ccx_runs", "ccx_resumes", "rework",
            "delegated", "context_attached", "files_changed", "diffstat", "model", "status", "verdicts", "error",
            "env_clean", "fingerprint")
    rows = tagged(read_jsonl(results_file(a.taskset)), a.tag)
    data = {"summary": summarize(rows),
            "rows": [r3.scrub({**{k: r[k] for k in keep if k in r},
                               **({"audit": {"problems": r["audit"].get("problems"),
                                             "n_path_hits": r["audit"].get("n_path_hits")}} if r.get("audit") else {})})
                     for r in rows]}
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
    r.add_argument("--taskset", choices=sorted(TASKSETS), default="r5",
                   help="r5 (default: the tasks the loop was tuned on) or holdout (unseen, for final claims)")
    r.add_argument("--tasks", default="", help="comma-separated ids from the task set (default: all of it)")
    r.add_argument("--arms", default="")
    r.add_argument("--budget", type=float, default=3.0, help="stop before a new unit once the results reach $")
    r.add_argument("--extra-spent", type=float, default=0.0)
    r.add_argument("--jobs", type=int, default=2, help="tasks run at the same time")
    r.add_argument("--lead-budget", type=float, default=3.0, help="claude -p --max-budget-usd for one lead")
    r.add_argument("--out", default="")
    r.add_argument("--workdir", default="")
    r.add_argument("--timeout", type=int, default=2400)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-canary", action="store_true", help="skip the one tiny real lead that checks the isolation")
    PF.add_options(r)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("--tag", default=None, help="only this round's rows (default: all; the tags are listed)")
    s.add_argument("--taskset", choices=sorted(TASKSETS), default="r5")
    s.set_defaults(fn=cmd_summary)
    e = sub.add_parser("export")
    e.add_argument("dest")
    e.add_argument("--tag", default=None)
    e.add_argument("--taskset", choices=sorted(TASKSETS), default="r5")
    e.set_defaults(fn=cmd_export)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
