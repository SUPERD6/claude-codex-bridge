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
  builtin2r opt-in (--arms builtin2r): builtin2 whose worker's own prompt also carries ccx's KEEP_TESTS and WIRING
           rules (imported from ccx/prompts.py), so ccx2 vs builtin2r tells ccx apart from those rules (fairness C5)

The lead is sonnet medium unless --lead-model / --lead-effort say otherwise; both are recorded in every row, in its
fingerprint and in the done-key, and a summary shows another lead's units as their own arm (`ccx2@opus-high`).
--budget counts the spend of this tag's rows only (plus --extra-spent), not the whole results file.

The summary pairs every two arms on the units they share (tag, round, task): McNemar exact p (Holm over the pairs),
task-level bootstrap 95% CIs for the cost-per-success and wall-median differences; per arm a Wilson CI, the right
count per round and, for units that used ccx, the wall per phase (sub-agent attempts, checks, reviews, fix rounds,
the lead waiting) from the ccx run records; with arms `balanced` and `save` both present, the tier decision rule.

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
final claims, five of them from other open-source repositories (scripts/eval/ext_repo.py: before the canary, each is
cloned once into a temporary folder outside the work dir, from its URL or from a local copy given with
--ext-cache DIR, read into memory and removed; a unit gets the parent's tree as a fresh one-commit repository; the
copies are denied to its agents along with Claude's web tools, pip has no index, and the audit flags installing or
fetching packages; tests run with PYTHONPATH=src and the Python given with --ext-python, which must have the modules
the repository's tests need and not the library itself, and must not sit next to the --ext-cache copies). Its
results go to their own file, and every finished unit's repository, hub and lead stream leave the
work dir after scoring (the stream is kept under .ccx/eval/r5/streams/<tag>/), so a later round's agents cannot find
an earlier round's finished answer next to them. r5 keeps its old behaviour.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import re
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
import seven_ab as S  # noqa: E402
from common import ROOT, append_jsonl, archive_hub, ccx_verify, git, read_jsonl  # noqa: E402
from ccx.prompts import KEEP_TESTS, WIRING  # noqa: E402
import ext_repo  # noqa: E402
import tasks_holdout  # noqa: E402
import tasks_r5  # noqa: E402

# r5: the 10 tasks the loop was tuned on; holdout (scripts/eval/tasks_holdout.py): 10 others never used for tuning,
# for the final claims (backlog C1). r5 stays the default everywhere.
TASKSETS = {"r5": tasks_r5, "holdout": tasks_holdout}
IDS = tasks_r5.IDS

OUT = ROOT / ".ccx" / "eval" / "r5"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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
# A task of another repository (tasks_holdout.REPOS): same shape, that repository's own description. It is not
# installed; PYTHONPATH=src is set (relative, so it also works in a ccx worktree), so tests run from the root.
LEAD_PROMPT_EXT = """You are the lead agent on this repository: {name}. It is not installed, and nothing can be
installed (pip has no package index here): PYTHONPATH=src is set, so from the repository root
`python -m pytest -q tests/...` tests the code in src/. {note}Run the tests that matter for your change. The person
asked:

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
# builtin2r (opt-in, `--arms builtin2r`): builtin2's lead wording, and a worker whose own prompt also carries the
# rules every ccx sub-agent gets (ccx/prompts.py, imported, not retyped): keep existing tests, test through the
# named entry point; and it is told to run the acceptance command (targeted tests while it works), as a ccx sub-agent
# with --check is, instead of the whole suite. ccx2 vs builtin2r then differs by ccx alone, not by these rules
# (fairness C5).
# The base worker prompt's "run the tests with `python -m pytest -q`" (the whole suite) would contradict WIRING's
# "run only the relevant test files, not the whole suite", so builtin2r's worker is told what a ccx sub-agent with
# --check is (SELFCHECK_CMD, in short): run the acceptance command it is given, targeted tests while it works.
WORKER_TESTS_BASE = "run the tests with `python -m pytest -q`"
WORKER_TESTS_R = ("run the acceptance command you are given (while you work, only the targeted tests touching your "
                  "change; the full acceptance command at most once, at the end)")
assert WORKER_TESTS_BASE in r3.WORKER["worker"]["prompt"]
WORKER_RULES = {"worker": {**r3.WORKER["worker"],
                           "prompt": r3.WORKER["worker"]["prompt"].replace(WORKER_TESTS_BASE, WORKER_TESTS_R)
                           + " Rules: " + KEEP_TESTS + " " + WIRING.rstrip()}}
CCX_ARMS = ("ccx", "ccx2")
BUILTIN_ARMS = PF.BUILTIN_ARMS
OPT_IN_ARMS = ("ccx2", "builtin2", "builtin2r")   # not in ARMS: the default schedule (and old tags' done-keys) stay
DEFAULT_LEAD = (r3.LEAD_MODEL, r3.LEAD_EFFORT)
# with both of these arms present the summary checks the tier decision rule (tier_rule)
TIER_RULE_ARMS = ("balanced", "save")
DIRECT = ["--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--review", "on", "--context", "off",
          "--no-escalate", "--no-fallback"]


def ext_spec(task: dict) -> dict | None:
    """The other repository a task belongs to (tasks_holdout.REPOS), or None for a task of this one."""
    return tasks_holdout.REPOS[task["repo"]] if task.get("repo") else None


def ext_cache(work: Path) -> Path:
    """Where a run keeps its clones of the other repositories (one per repository per work dir)."""
    return Path(work) / "ext-cache"


_FETCH = threading.Lock()
# (repo, commit, tests) -> ext_repo.material: what the units of an external task need, read once out of the clone.
# A run fills it before the first unit from a clone outside the work dir that it then removes (prepare_external).
_EXT: dict[tuple, dict] = {}


def ext_clone(task: dict, work: Path, source: str | Path | None = None, cache: Path | None = None) -> Path:
    """The cached clone of a task's repository, fetched on first use (one fetch at a time) and its sha checked."""
    with _FETCH:
        repo = ext_repo.fetch(task["repo"], ext_spec(task), Path(cache) if cache else ext_cache(work),
                              Path(source) if source else None)
        ext_repo.pin(repo, task["commit"])
    return repo


def _ext_key(task: dict) -> tuple:
    return (task["repo"], task["commit"], tuple(task["tests"]))


def ext_material(task: dict, work: Path | None = None, source: str | Path | None = None,
                 cache: Path | None = None) -> dict:
    """The task's material (ext_repo.material), read from its clone on first use: the clone in `cache`, else in the
    work dir's ext-cache (holdout_check; a run has always filled it before, from outside the work dir)."""
    key = _ext_key(task)
    if key not in _EXT:
        repo = ext_clone(task, work, source, cache)
        m = ext_repo.material(repo, task["commit"], task["tests"])
        with _FETCH:
            _EXT.setdefault(key, m)
    return _EXT[key]


def make_repo(task: dict, dest: Path, work: Path | None = None, source: str | Path | None = None) -> None:
    """The repository at the commit's parent, today's conftest committed into it. A task of another repository:
    the parent's tree alone in a fresh repository (ext_repo.repo_from_tar), nothing of this one added."""
    r2._rmtree(dest)
    if ext_spec(task):
        ext_repo.repo_from_tar(ext_material(task, work or dest.parent, source)["tar"], ext_spec(task), dest)
        return
    dest.mkdir(parents=True)
    data = subprocess.run(["git", "archive", f"{task['commit']}^"], cwd=ROOT, capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(data)).extractall(dest)
    (dest / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "start")


def ext_python(a=None) -> str:
    """The Python that runs another repository's tests (and that its agents find first on PATH)."""
    return str(getattr(a, "ext_python", "") or sys.executable)


def task_env(task: dict, env: dict, python: str | None = None) -> dict:
    """A unit's environment for its task: for another repository, PYTHONPATH=src and its Python first on PATH."""
    spec = ext_spec(task)
    if not spec:
        return env
    py = python or sys.executable
    return {**env, **ext_repo.run_env(spec), "PATH": str(Path(py).parent) + os.pathsep + env.get("PATH", "")}


def ext_note(spec: dict) -> str:
    """The repository's own remark for the lead prompt (e.g. a test file that needs plugins not installed)."""
    return f"{spec['note']} " if spec.get("note") else ""


# what the audit flags in an external unit's tool calls: the run's clone folder, installing or downloading packages,
# fetching from the code hosts or package index (the released library has the fix)
EXT_FLAGS = (r"ext-cache", r"\bpip3?(\.exe)?[\"']?\s+(install|download)\b", r"-m\s+pip\s+(install|download)\b",
             r"\b(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm|git\s+clone)\b[^\n]*"
             r"(github\.com|gitlab\.com|pypi\.org|pythonhosted\.org)")


def ext_guard(task: dict, a, work: Path) -> dict:
    """Unit fields for an external task: folders denied (the work dir's ext-cache, the --ext-cache copies), Claude's
    web tools denied, and the audit's flags (EXT_FLAGS, the repository's URL, the copies' folder by its last two
    names, so a relative path to it is flagged too)."""
    spec = ext_spec(task)
    if not spec:
        return {}
    hidden, flags = [ext_cache(work)], list(EXT_FLAGS)
    url = re.sub(r"^\w+://|\.git$", "", spec["url"]).lower()
    flags.append(re.escape(url))
    src = getattr(a, "ext_cache", "") or ""
    if src:
        sp = Path(src).expanduser()
        hidden.append(sp)
        flags.append(re.escape(f"{sp.parent.name}/{sp.name}".lower()))
    return {"hidden": tuple(hidden), "deny": ("WebFetch", "WebSearch"), "flags": tuple(flags)}


def iso_env(d: Path, python: str | None = None) -> dict:
    env = {k: v for k, v in PF.base_env().items() if not k.endswith(PF.ENV_KEEP_SUFFIX)
           and not k.startswith(("CCX_", "CLAUDE", "CODEX"))}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = str(Path(python or sys.executable).parent) + os.pathsep + env.get("PATH", "")
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


def hidden(task: dict, work: Path, source: str | Path | None = None) -> dict[str, bytes]:
    """The commit's own test files: from this checkout, or from the cached clone of the task's repository."""
    if ext_spec(task):
        return ext_material(task, work, source)["tests"]
    return {t: subprocess.run(["git", "show", f"{task['commit']}:{t}"], cwd=ROOT, capture_output=True,
                              check=True).stdout for t in task["tests"]}


def score(repo: Path, task: dict, work: Path, job: PF.Job | None = None, python: str | None = None,
          source: str | Path | None = None) -> dict:
    """The commit's own test files (overwriting whatever the agent left in them), in throwaway homes. Another
    repository's: its test folder and test configuration put back from the parent first (ext_repo.
    restore_test_setup), no conftest of ours, its install-time stubs put back if gone, PYTHONPATH=src, `python`."""
    spec = ext_spec(task)
    if spec:
        m = ext_material(task, work, source)
        ext_repo.restore_test_setup(repo, m["tar"], spec, keep=m["changed"])
    for t, body in hidden(task, work, source).items():
        (repo / t).parent.mkdir(parents=True, exist_ok=True)
        (repo / t).write_bytes(body)
    if spec:
        ext_repo.write_stubs(repo, spec)
    else:
        (repo / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    py = python or sys.executable
    iso = Path(tempfile.mkdtemp(prefix="r5iso-", dir=work))
    try:
        env = iso_env(iso, py)
        if spec:
            env.update(ext_repo.run_env(spec))
        color = ["--color=no"] if spec else []         # humanize's addopts asks for colour: keep the row's text plain
        out, _err, rc, _left = PF.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *color,
                                       *pytest_args(task)], cwd=repo, env=env, timeout=900, job=job)
        if rc == -9:
            return {"ok": False, "pytest": "timeout"}
        tail = ANSI.sub("", (out.strip().splitlines() or [""])[-1])
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
    if arm in ("builtin2", "builtin2r"):          # builtin2r: the same lead wording, the rules are in the worker
        return HOW_BUILTIN2
    return r3.HOW[arm]


def lead_flags_arm(arm: str) -> str:
    """The round-3 arm whose lead command line (tools, agents, session file) this arm uses."""
    return "ccx" if arm in CCX_ARMS else "builtin" if arm in BUILTIN_ARMS else arm


def worker_agents(arm: str) -> dict | None:
    """The --agents definition for a builtin arm's lead (None: r3.WORKER, as before)."""
    return WORKER_RULES if arm == "builtin2r" else None


NO_LEAD_ARMS = ("direct",)      # ccx straight from the command line: no Claude lead, --lead-model changes nothing


def has_lead(arm: str) -> bool:
    return arm not in NO_LEAD_ARMS


def lead_of(r: dict) -> tuple[str, str]:
    """A unit's or row's lead (model, effort); rows from before --lead-model had the default. An arm without a lead
    (direct) always counts as the default, whatever a row carries, so its units and rows keep one key, folder, label
    and summary arm under any --lead-model (they are not re-run, and they pool and pair as one arm)."""
    if not has_lead(r.get("arm") or ""):
        return DEFAULT_LEAD
    return (r.get("lead_model") or DEFAULT_LEAD[0], r.get("lead_effort") or DEFAULT_LEAD[1])


def _lead_suffix(r: dict) -> str:
    m, e = lead_of(r)
    return "" if (m, e) == DEFAULT_LEAD else "@" + re.sub(r"[^\w.-]", "_", f"{m}-{e}")


def arm_of(r: dict) -> str:
    """The arm a summary counts a row under: its arm, plus its lead when not the default (`ccx2@opus-high`), so
    units with different leads are never pooled or paired as one arm."""
    return f"{r['arm']}{_lead_suffix(r)}"


def done_key(r: dict) -> tuple:
    """What makes a unit done: tag, round, task, arm and the lead (old rows: the default lead, so they still match)."""
    return (r.get("tag"), r.get("round"), r.get("task"), r.get("arm"), *lead_of(r))


def unit_key(u: dict) -> str:
    """The unit's folder / stream name in the work dir (the old name for the default lead)."""
    return f"{u['round']}-{u['task']}-{u['arm']}{_lead_suffix(u)}"


def lead_unit(u: dict, a, work: Path, repo: Path, hub: Path, iso: PF.Unit | None = None, env: dict | None = None,
              job: PF.Job | None = None) -> dict:
    task = by_id(u["task"])
    env = {**(env or PF.base_env()), "CCX_HUB": str(hub), "CCX_NO_QUOTA_PROBE": "1",
           "BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000"}
    is_ccx, is_builtin = u["arm"] in CCX_ARMS, u["arm"] in BUILTIN_ARMS
    env = task_env(task, env, ext_python(a))
    how = lead_how(u["arm"], u["label"])
    spec = ext_spec(task)
    prompt = (LEAD_PROMPT_EXT.format(name=spec["name"], note=ext_note(spec), brief=task["brief"], how=how)
              if spec else LEAD_PROMPT.format(brief=task["brief"], how=how))
    t0 = time.time()
    # ccx2 / builtin2 need the same lead flags as ccx / builtin (a session file; the Agent tool and worker); the
    # clean-room flags (no user settings, hooks, CLAUDE.md, auto-memory; deny rules) come from preflight
    model, effort = lead_of(u)
    argv = r3.lead_argv(lead_flags_arm(u["arm"]), a.lead_budget, model, effort, worker_agents(u["arm"])) \
        + (PF.lead_flags(iso) if iso else [])
    out, _err, rc, _left = PF.run(argv, input=prompt, cwd=repo, env=env, timeout=a.timeout, job=job)
    wall = round(time.time() - t0, 1)
    (work / f"{unit_key(u)}.stream.jsonl").write_text(out, encoding="utf-8")
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
        if cost["run_ids"]:
            row["phases"] = phase_wall(hub, cost["run_ids"], wall)
    return row


PHASES = ("sub_s", "check_s", "review_s", "fix_s", "overlap_s", "lead_wait_s", "lead_active_s")


def phase_wall(hub: Path, run_ids: list, wall_s: float | None = None) -> dict:
    """Where a unit's ccx time went, from its run records (run.json): the sub-agent's attempts (sub_s, n_attempts),
    ccx's acceptance checks (check_s), the reviews (review_s: the `review:<id>` runs), the fix rounds after a review
    (fix_s: a run with review_of, its attempts and its check) and, with the lead's wall, the lead waiting on ccx
    (lead_wait_s, an estimate: ccx runs block the lead, or it waits with show --wait) and the rest (lead_active_s).
    Checks count every run of ccx's check: the final one (record["check"]) and those of earlier rungs that failed
    and climbed (an attempt's check_seconds). ccx runs a run's review while its final check runs, so lead_wait_s
    counts that time once (overlap_s: the shorter of the two, per run with both) and is at most the wall. A review
    started alongside an earlier rung's check and stopped when that check failed (a `review:<id>` run that is not
    the linked one) overlaps those failed checks the same way. Records
    that cannot be read are counted in `missing`."""
    sub = check = review = fix = overlap = 0.0
    n_att = n_rev = n_fix = missing = 0
    ids, seen = list(dict.fromkeys(str(x) for x in run_ids)), set()
    recs: dict[str, dict] = {}
    while ids:
        rid = ids.pop(0)
        if rid in seen:
            continue
        seen.add(rid)
        rec = r2.record(hub, rid)
        if not rec:
            missing += 1
            continue
        recs[rid] = rec
        rv = (rec.get("review") or {}).get("run_id")
        if rv and str(rv) not in seen:          # a review not in the ledger list is still counted
            ids.append(str(rv))

    def secs(rec: dict) -> float:
        return sum(float(x.get("seconds") or 0) for x in rec.get("attempts") or [])

    def is_review(rec: dict) -> bool:
        return str(rec.get("label") or "").startswith("review:")

    by_parent: dict[str, list[tuple[str, dict]]] = {}
    for rid, rec in recs.items():
        if is_review(rec):
            by_parent.setdefault(str(rec["label"])[len("review:"):], []).append((rid, rec))

    for rid, rec in recs.items():
        if is_review(rec):
            review, n_rev = review + secs(rec), n_rev + 1
            continue
        final = (rec.get("check") or {}).get("seconds")
        early = sum(float(x.get("check_seconds") or 0) for x in rec.get("attempts") or [])
        c = float(final or 0) + early
        linked = str((rec.get("review") or {}).get("run_id"))
        rv = recs.get(linked)
        if final and rv and is_review(rv):      # the review ran alongside the final check
            overlap += min(float(final), secs(rv))
        # reviews stopped when an earlier rung's check failed ran alongside those checks
        stopped = sum(secs(x) for xid, x in by_parent.get(str(rid), []) if xid != linked)
        if early and stopped:
            overlap += min(early, stopped)
        if rec.get("review_of"):
            fix, n_fix = fix + secs(rec) + c, n_fix + 1
        else:
            sub, check, n_att = sub + secs(rec), check + c, n_att + len(rec.get("attempts") or [])
    out = {"sub_s": round(sub, 1), "check_s": round(check, 1), "review_s": round(review, 1), "fix_s": round(fix, 1),
           "overlap_s": round(overlap, 1), "n_attempts": n_att, "n_reviews": n_rev, "n_fix_rounds": n_fix,
           "missing": missing}
    if wall_s is not None:
        wait = min(float(wall_s), sub + check + review + fix - overlap)
        out.update(lead_wait_s=round(wait, 1), lead_active_s=round(float(wall_s) - wait, 1))
    return out


def direct_unit(u: dict, a, repo: Path, hub: Path, env: dict | None = None, job: PF.Job | None = None) -> dict:
    task = by_id(u["task"])
    argv = ["run", "--mode", "write", "--new", "--no-ab", "--force", "--label", u["label"], "--minutes", "60",
            *DIRECT, task["brief"]]
    t0 = time.time()
    env = task_env(task, {**(env or PF.base_env()), "CCX_HUB": str(hub)}, ext_python(a))
    out, err, rc, _left = PF.run([sys.executable, str(ROOT / "ccx.py"), *argv], cwd=repo, env=env,
                                 timeout=a.timeout, job=job)
    res, err = r2.S._last_json(out), ("timeout" if rc == -9 else err[-400:])
    cost = r2.hub_cost(hub)
    rec = r2.record(hub, res.get("run_id"))
    row = {"rc": rc, "wall_s": round(time.time() - t0, 1), "usd": cost["usd"], "ccx_usd": cost["usd"],
           "ccx_review_usd": cost["review_usd"], "ccx_run_ids": cost["run_ids"], "model": res.get("model"),
           "status": res.get("status"), "ccx_ok": res.get("ok"),
           "verdicts": [v.get("verdict") for v in (rec.get("first_review"), rec.get("review")) if v],
           "stderr": err if rc else ""}
    if cost["run_ids"]:
        row["phases"] = phase_wall(hub, cost["run_ids"])          # no lead: nothing waits
    return row


def unit_of(u: dict, a, work: Path) -> PF.Unit:
    key = unit_key(u)
    return PF.Unit(key=key, work=work, repo=work / key, hub=work / f"h-{key}", label=u["label"],
                   claude=a.claude_isolation, codex_home=Path(a.codex_home).expanduser() if a.codex_home else None,
                   dsh=a.dsh_home, agents=tuple(r3.WORKER), **ext_guard(by_id(u["task"]), a, work))


def unit_models(u: dict, row: dict) -> dict:
    """The models this unit was meant to use, and the ones its streams and ledger show it did use."""
    model, effort = lead_of(u)
    out = {"lead": model, "lead_effort": effort, "builtin_worker": r3.WORKER_MODEL}      # direct: replaced below
    if u["arm"] == "builtin2r":
        out["worker_rules"] = "KEEP_TESTS+WIRING"
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
        # a task of another repository: its material was read before the first unit (prepare_external), from a
        # clone outside the work dir that is gone now; a unit never clones into the work dir itself
        xkw = {"work": work, "source": getattr(a, "ext_cache", None)} if ext_spec(task) else {}
        if xkw and _ext_key(task) not in _EXT:
            raise RuntimeError(f"{task['id']}: the other repository was not prepared before the run")
        make_repo(task, repo, **xkw)
        if ext_spec(task):
            row["ext"] = {"repo": task["repo"], "commit": task["commit"], "date": _EXT[_ext_key(task)]["date"],
                          **(getattr(a, "ext_info", None) or {"python": ext_python(a)})}
        hinfo = r3.make_hub(hub)
        hinfo["memory_empty"] = PF.hub_memory_empty(hub)
        row["hub"] = hinfo
        env = PF.prepare(iso)
        row.update(direct_unit(u, a, repo, hub, env, job) if u["arm"] == "direct" else
                   lead_unit(u, a, work, repo, hub, iso, env, job))
        row.update(changed(repo))
        sc = score(repo, task, work, job, **({"python": ext_python(a), "source": xkw["source"]} if xkw else {}))
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
        if "ext" in row and getattr(a, "ext_venv", None):
            # the Python that scores every unit is shared: something installed into it changes later units
            try:
                now = venv_state(ext_python(a))
            except Exception as e:  # noqa: BLE001
                now = f"unreadable: {type(e).__name__}"
            if now != a.ext_venv:
                row["ext"]["venv_changed"] = True
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


def spent(f: Path, tag: str | None = None) -> float:
    """What the rows of a results file cost (only those of `tag` when given)."""
    return round(sum(r.get("usd") or 0 for r in read_jsonl(f) if tag is None or r.get("tag") == tag), 4)


def budget_spent(f: Path, tag: str, extra: float = 0.0) -> float:
    """What --budget is checked against: this tag's rows (earlier invocations of the same tag included, so going
    on with a tag does not get a fresh budget) plus --extra-spent; other tags in the same file do not count."""
    return round(spent(f, tag) + (extra or 0.0), 4)


def spend_line(f: Path, tag: str, extra: float, run_usd: float) -> str:
    """run (this invocation), tag (what the budget counts, with --extra-spent) and file totals."""
    return (f"run=${run_usd:.3f} tag=${budget_spent(f, tag, extra):.3f} file=${spent(f):.3f}")


def _py(python: str, code: str) -> str:
    """The output of a little code of ours run by `python` in isolated mode (nothing of the repositories)."""
    r = subprocess.run([python, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    if r.returncode:
        raise RuntimeError(f"{python} failed: {(r.stderr or '').strip()[-200:]}")
    return r.stdout.strip()


def missing_modules(python: str, names: list[str]) -> list[str]:
    """Which of these modules `python` cannot find (found, not imported: nothing of them is run)."""
    out = _py(python, "import importlib.util as u, json; print(json.dumps([n for n in %r if u.find_spec(n) is None]))"
              % (list(names),))
    return json.loads(out)


def python_info(python: str) -> dict:
    """The version of `python` and of its pytest (or None)."""
    out = _py(python, "import sys, json\ntry:\n    from importlib.metadata import version; p = version('pytest')\n"
                      "except Exception:\n    p = None\nprint(json.dumps(['%d.%d.%d' % sys.version_info[:3], p]))")
    v, p = json.loads(out)
    return {"python_version": v, "pytest": p}


def venv_state(python: str) -> str:
    """A fingerprint of what is installed for `python` (the names in its site-packages folders)."""
    out = _py(python, "import site, os, json\nds = site.getsitepackages() + [site.getusersitepackages()]\n"
                      "print(json.dumps(sorted(d + '|' + n for d in ds if os.path.isdir(d) for n in os.listdir(d))))")
    return hashlib.sha256(out.encode("utf-8")).hexdigest()


def _version(s: str | None) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:3])


def prepare_external(todo: list[dict], a, work: Path) -> list[str]:
    """Before the first unit (and before the paid canary): read every other repository the units need out of a
    clone made in a temporary folder outside the work dir, which is then removed (the fix is never on disk next to
    a unit), check each pinned sha, and check the Python for their tests: 3.11 or newer (ccx runs on it too, it is
    first on PATH), has the modules the tests need and a new enough pytest, does not have the library itself
    installed (its released code has the fix), and is not kept next to the --ext-cache copies (an agent sees its
    folder on PATH). Records that Python's versions and a fingerprint of what is installed in it on `a` (ext_info,
    ext_venv). Returns the problems (none: ready)."""
    tasks = {u["task"]: by_id(u["task"]) for u in todo}
    ext = [t for t in tasks.values() if ext_spec(t)]
    if not ext:
        return []
    probs = []
    tmp = Path(tempfile.mkdtemp(prefix="ccx-ext-"))
    try:
        for t in ext:
            try:
                ext_material(t, work, getattr(a, "ext_cache", None), cache=tmp)
            except Exception as e:  # noqa: BLE001 — reported, the run does not start
                probs.append(f"{t['id']}: {type(e).__name__}: {e}"[:300])
    finally:
        ext_repo._rmtree(tmp)
    py = ext_python(a)
    try:
        info = python_info(py)
    except Exception as e:  # noqa: BLE001
        return probs + [f"--ext-python {py} does not run: {e}"[:300]]
    a.ext_info = {"python": py, **info}
    if _version(info["python_version"]) < (3, 11):
        probs.append(f"{py} is Python {info['python_version']}: ccx runs on it in external units, it needs 3.11+")
    specs = {t["repo"]: ext_spec(t) for t in ext}
    needs = sorted({n for s in specs.values() for n in s.get("needs") or ()})
    gone = missing_modules(py, needs) if needs else []
    if gone:
        probs.append(f"{py} cannot import {', '.join(gone)} (the other repositories' tests need "
                     f"them): install them there or pass --ext-python")
    low = sorted({s["pytest_min"] for s in specs.values() if s.get("pytest_min")}, key=_version)
    if low and info["pytest"] and _version(info["pytest"]) < _version(low[-1]):
        probs.append(f"{py} has pytest {info['pytest']}; the other repositories' tests need {low[-1]} or newer")
    mods = sorted(s["module"] for s in specs.values() if s.get("module"))
    there = sorted(set(mods) - set(missing_modules(py, mods))) if mods else []
    if there:
        probs.append(f"{py} has {', '.join(there)} installed: its released code has the fix; use a Python without it")
    src = getattr(a, "ext_cache", "") or ""
    if src and PF._inside(Path(py).parent, Path(src).expanduser().resolve().parent):
        probs.append(f"{py} is in the folder that holds the --ext-cache copies ({Path(src).parent}): an agent finds "
                     f"that folder on PATH; keep the Python somewhere else")
    try:
        a.ext_venv = venv_state(py)
    except Exception as e:  # noqa: BLE001
        probs.append(f"cannot list what {py} has installed: {e}"[:300])
    return probs


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
    done = {done_key(r) for r in read_jsonl(out)}
    lead = {"lead_model": a.lead_model or DEFAULT_LEAD[0], "lead_effort": a.lead_effort or DEFAULT_LEAD[1]}
    todo = []
    for u in schedule(a.rounds, a.seed, tasks, arms):
        u = {**u, "tag": a.tag, "seed": a.seed, "taskset": a.taskset, **(lead if has_lead(u["arm"]) else {})}
        u["label"] = f"eval-r5:{a.tag}:{u['round']}:{u['task']}:{u['arm']}{_lead_suffix(u)}"
        if done_key(u) not in done:
            todo.append(u)
    print(f"work dir: {work}  results: {out}  units: {len(todo)}  lead: {lead['lead_model']} "
          f"{lead['lead_effort']}", flush=True)
    if a.dry_run:
        for u in todo:
            print(f"[dry] {u['label']}")
        return 0
    # the other repositories first: a bad --ext-python or copy must not cost the paid canary
    probs = prepare_external(todo, a, work)
    for p in probs:
        print(f"[external] {p}", flush=True)
    if probs:
        print("other repositories not ready: not starting", flush=True)
        return 3
    rep = PF.run_checks(PF.options_from(a, arms, work, canary_on=not a.no_canary, start=True,
                                        tasks_file=Path(TASKSETS[a.taskset].__file__)))
    for p in rep["problems"]:
        print(f"[preflight] {p}", flush=True)
    if not rep["ok"] and not a.force_unclean:
        print("preflight failed: not starting (fix the above, or --force-unclean to run anyway; it is recorded)",
              flush=True)
        return 3
    rep["lead"] = {"model": lead["lead_model"], "effort": lead["lead_effort"]}     # in every row's fingerprint
    work.mkdir(parents=True, exist_ok=True)
    (work / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[preflight] {rep['result']}: commit {rep['commit'][:12]} cli {rep['cli']} codex {rep['codex']['mode']} "
          f"claude {rep['claude_isolation']} jobs {a.jobs} canary {rep['canary']}", flush=True)
    a.preflight = rep
    need_codex = any(x in PF.CODEX_ARMS for x in arms)
    ours = [PF._norm(work), PF._norm(f"eval-r5:{a.tag}:")]
    watch = PF.Watch(ours).start()
    lock, stop = threading.Lock(), threading.Event()
    run_usd = [0.0]                       # this invocation's own spend

    def one(u):
        with lock:
            total = budget_spent(out, a.tag, a.extra_spent)
            if stop.is_set() or total >= a.budget:
                if not stop.is_set():
                    print(f"budget ${a.budget} reached (tag {a.tag}: ${total:.3f}): stopping", flush=True)
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
        if (row.get("ext") or {}).get("venv_changed"):
            row["env_clean"] = False
            why.append(f"something was installed into {ext_python(a)} during the unit (it scores every unit)")
        if (row.get("leftovers") or {}).get("unkilled"):
            why.append(f"processes that could not be killed: {row['leftovers']['unkilled']}")
        if why and not a.force_unclean:
            print(f"stopping: {'; '.join(why)[:400]}", flush=True)
            stop.set()
        with lock:
            append_jsonl(out, row)
            run_usd[0] += row.get("usd") or 0
            print(f"r{u['round']} {u['task']:18} {u['arm']:8} ok={row.get('ok')} ${row.get('usd', 0):.4f} "
                  f"(lead ${row.get('lead_only_usd', 0) or 0:.4f}) req={row.get('lead_requests')} "
                  f"lead_tok={row.get('lead_tokens')} {row.get('wall_s')}s deleg={row.get('delegated')} "
                  f"files={row.get('files_changed')} clean={row['env_clean']} "
                  f"{spend_line(out, a.tag, a.extra_spent, run_usd[0])}", flush=True)

    # units of one task run one after another (arms in their shuffled order); --jobs tasks at a time
    groups: dict[tuple, list[dict]] = {}
    for u in todo:
        groups.setdefault((u["round"], u["task"]), []).append(u)
    try:
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            list(ex.map(lambda us: [one(u) for u in us], groups.values()))
    finally:
        watch.close()
    print(f"spent: {spend_line(out, a.tag, a.extra_spent, run_usd[0])} (budget ${a.budget} counts tag)", flush=True)
    # the person's own state, by size and count only: the hub ledger must not have grown, no Claude session folder
    # named after this work dir may be left in the real ~/.claude
    rep["real_state_after"] = post = PF.real_state(PF.real_paths(), work)
    rep["postflight"] = "same" if post == rep["real_state"] else "changed"
    (work / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if post != rep["real_state"]:
        print(f"[postflight] the person's own state changed: {rep['real_state']} -> {post}", flush=True)
        return 4
    return 2 if stop.is_set() else 0


def wall_stats(rs: list[dict]) -> dict:
    """Right, spend and wall of some rows: median (as wall_med elsewhere: the upper middle), mean and p75 (nearest
    rank). The median alone hid the slow tail that the per-task routing analysis needed."""
    w = sorted(r.get("wall_s") or 0 for r in rs)
    ok = sum(bool(r.get("ok")) for r in rs)
    usd = sum(r.get("usd") or 0 for r in rs)
    return {"n": len(rs), "ok": ok, "usd": round(usd, 4), "cps": round(usd / ok, 4) if ok else None,
            "wall_med": w[len(w) // 2] if w else None, "wall_mean": round(sum(w) / len(w), 1) if w else None,
            "wall_p75": w[-(-3 * len(w) // 4) - 1] if w else None}


def round_key(rd) -> tuple:
    """Rounds in numeric order (2 before 10), anything else after them by its text, a missing one last."""
    return (rd is None, not isinstance(rd, int), rd if isinstance(rd, int) else 0, str(rd))


def ok_rate(ps: list[tuple[dict, dict]]) -> float | None:
    """The share of right rows (pairs of a row with itself, for task_boot)."""
    return round(sum(bool(x.get("ok")) for x, _ in ps) / len(ps), 4) if ps else None


def by_tag(rows: list[dict]) -> dict:
    """Per tag, per arm: wall_stats of its rows and of each round on its own, so different rounds (and the rounds
    of one tag) are never pooled without the split showing."""
    out: dict = {}
    for tag in sorted({str(r.get("tag")) for r in rows}):
        tr = [r for r in rows if str(r.get("tag")) == tag]
        for arm in arm_order(arm_of(r) for r in tr):
            ar = [r for r in tr if arm_of(r) == arm]
            rounds = {str(rd): wall_stats([r for r in ar if r.get("round") == rd])
                      for rd in sorted({r.get("round") for r in ar}, key=round_key)}
            out.setdefault(tag, {})[arm] = {**wall_stats(ar), "rounds": rounds}
    return out


def med_p75(xs: list[float]) -> dict:
    """Median (the upper middle, as wall_stats) and p75 (nearest rank) of some numbers."""
    w = sorted(xs)
    return {"med": w[len(w) // 2], "p75": w[-(-3 * len(w) // 4) - 1], "n": len(w)} if w else \
        {"med": None, "p75": None, "n": 0}


def arm_order(names) -> list[str]:
    """Arms in a stable order: the default ones, the opt-in ones, then any other (another lead: `ccx@opus-high`)."""
    known = [*ARMS, *OPT_IN_ARMS]
    base = lambda x: x.split("@", 1)[0]  # noqa: E731
    return sorted(set(names), key=lambda x: (known.index(base(x)) if base(x) in known else len(known), x))


def pair_units(rows: list[dict], A: str, B: str) -> list[tuple[dict, dict]]:
    """(A, B) rows of the same unit: tag, round, task (and rep, when rows have one); arms as arm_of names them."""
    by: dict = {}
    for r in rows:
        if "error" not in r:
            by.setdefault((str(r.get("tag")), r.get("round"), r.get("task"), r.get("rep")), {})[arm_of(r)] = r
    return [(d[A], d[B]) for _, d in sorted(by.items(), key=lambda kv: tuple(str(x) for x in kv[0]))
            if A in d and B in d]


def task_boot(ps: list[tuple[dict, dict]], stat, n: int = 4000, seed: int = 7,
              info: dict | None = None) -> tuple[float, float] | None:
    """Bootstrap 95% CI of stat(pairs), resampling tasks (the independent unit; a task's rounds go together).
    Resamples where the stat is undefined (None) are left out; `info`, when given, gets how many (dropped, of n)."""
    by: dict = {}
    for p in ps:
        by.setdefault(p[0]["task"], []).append(p)
    ts = sorted(by)
    if info is not None:
        info.update(n=0, dropped=0)
    if len(ts) < 2:
        return None
    rnd = random.Random(seed)
    vals = []
    for _ in range(n):
        v = stat([p for t in (rnd.choice(ts) for _ in ts) for p in by[t]])
        if v is not None:
            vals.append(v)
    if info is not None:
        info.update(n=n, dropped=n - len(vals))
    vals.sort()
    return (round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)) if vals else None


def _med(xs) -> float | None:
    """The median as every wall_med of the summary takes it: the upper middle."""
    w = sorted(xs)
    return w[len(w) // 2] if w else None


def cps_diff(ps: list[tuple[dict, dict]]) -> float | None:
    """Cost per success of B minus that of A on these pairs (None when either has no success)."""
    a, b = r3.cps([x for x, _ in ps]), r3.cps([y for _, y in ps])
    return None if a is None or b is None else round(b - a, 5)


def wall_med_diff(ps: list[tuple[dict, dict]]) -> float | None:
    """Median wall (the upper middle, as wall_med) of B minus that of A on these pairs."""
    if not ps:
        return None
    return round(_med([y.get("wall_s") or 0 for _, y in ps]) - _med([x.get("wall_s") or 0 for x, _ in ps]), 1)


def task_sign(ps: list[tuple[dict, dict]]) -> tuple[int, int]:
    """Per task (the independent unit), which arm was right more often over its rounds: (tasks where A was, tasks
    where B was); ties are left out. Its exact sign test does not take a task's rounds as independent pairs."""
    by: dict = {}
    for x, y in ps:
        d = by.setdefault(x["task"], [0, 0])
        d[0] += bool(x.get("ok"))
        d[1] += bool(y.get("ok"))
    return sum(a > b for a, b in by.values()), sum(b > a for a, b in by.values())


def compare_pair(ps: list[tuple[dict, dict]], A: str, B: str) -> dict:
    """One arm pair on its shared units: right counts, McNemar exact p on the discordant units, the exact sign test
    over tasks (task_sign_p: the one to read when a task has several rounds, which McNemar counts as independent
    pairs), and B - A of cost per success and of the wall median with task-level bootstrap 95% CIs (resamples where
    an arm has no success are left out of the cost one, and counted)."""
    b = sum(bool(x.get("ok")) and not y.get("ok") for x, y in ps)
    c = sum(bool(y.get("ok")) and not x.get("ok") for x, y in ps)
    tb, tc = task_sign(ps)
    n_tasks = len({x["task"] for x, _ in ps})
    ci_info: dict = {}
    out = {"arms": [A, B], "units": len(ps), "tasks": n_tasks,
           "ok": {A: sum(bool(x.get("ok")) for x, _ in ps), B: sum(bool(y.get("ok")) for _, y in ps)},
           "discordant": {f"only_{A}": b, f"only_{B}": c}, "mcnemar_p": S.mcnemar_p(b, c),
           "task_sign": {f"more_{A}": tb, f"more_{B}": tc}, "task_sign_p": S.mcnemar_p(tb, tc),
           "diff_is": f"{B} - {A}",
           "cps": {A: r3.cps([x for x, _ in ps]), B: r3.cps([y for _, y in ps])},
           "cps_diff": cps_diff(ps), "cps_diff_ci": task_boot(ps, cps_diff, info=ci_info),
           "cps_diff_ci_dropped": ci_info.get("dropped", 0),
           "wall_med_diff": wall_med_diff(ps), "wall_med_diff_ci": task_boot(ps, wall_med_diff)}
    if len(ps) > n_tasks:
        out["mcnemar_note"] = (f"{len(ps)} units from {n_tasks} tasks: McNemar takes a task's rounds as independent "
                               "pairs (anti-conservative); task_sign_p does not")
    if out["cps_diff"] is None:
        none = [arm for arm, v in out["cps"].items() if v is None]
        out["cps_diff_note"] = f"no cost per success: {', '.join(none)} has no success on these units"
    elif ci_info.get("dropped"):
        out["cps_diff_note"] = (f"{ci_info['dropped']} of {ci_info['n']} resamples had an arm without a success and "
                                "were left out: the CI is conditional on both arms succeeding")
    return out


def paired_all(rows: list[dict]) -> dict:
    """compare_pair for every two arms that share units, with Holm-adjusted McNemar and task sign p over those
    pairs."""
    arms = arm_order(arm_of(r) for r in rows if "error" not in r)
    out = {}
    for i, A in enumerate(arms):
        for B in arms[i + 1:]:
            ps = pair_units(rows, A, B)
            if ps:
                out[f"{A} vs {B}"] = compare_pair(ps, A, B)
    for key in ("mcnemar_p", "task_sign_p"):
        for k, (_p, adj) in S.holm({k: v[key] for k, v in out.items()}).items():
            out[k][f"{key}_holm"] = adj
    return out


def tier_rule(rows: list[dict], bal: str = TIER_RULE_ARMS[0], save: str = TIER_RULE_ARMS[1]) -> dict | None:
    """The tier decision rule on the units both arms share: `balanced` is worth it over `save` when it is right at
    least as often, its wall median is at most 60% of save's and its cost per success at most 1.5x save's. Each
    condition: pass / fail (n/a when a cost per success is missing); overall: fail when any condition fails, else n/a
    when one cannot be told, else pass. The wall median is the upper middle, as wall_med. None unless both arms
    have rows."""
    ps = pair_units(rows, save, bal)
    if not ps:
        return None
    s_ok, b_ok = sum(bool(x.get("ok")) for x, _ in ps), sum(bool(y.get("ok")) for _, y in ps)
    s_w = _med([x.get("wall_s") or 0 for x, _ in ps])
    b_w = _med([y.get("wall_s") or 0 for _, y in ps])
    s_c, b_c = r3.cps([x for x, _ in ps]), r3.cps([y for _, y in ps])
    pf = lambda v: "pass" if v else "fail"  # noqa: E731
    cond = {"right": {"rule": f"{bal} right >= {save} right", "value": [b_ok, s_ok], "result": pf(b_ok >= s_ok)},
            "wall": {"rule": f"{bal} wall median <= 60% of {save}'s", "value": [b_w, s_w],
                     "result": pf(b_w <= 0.6 * s_w)},
            "cps": {"rule": f"{bal} $/success <= 1.5x {save}'s", "value": [b_c, s_c],
                    "result": "n/a" if b_c is None or s_c is None else pf(b_c <= 1.5 * s_c)}}
    res = [c["result"] for c in cond.values()]
    return {"units": len(ps), "conditions": cond,
            "result": "fail" if "fail" in res else "n/a" if "n/a" in res else "pass"}


def tier_rule_lines(tr: dict | None) -> list[str]:
    """The tier decision rule as plain lines (cmd_summary prints them after the JSON, on stderr)."""
    if not tr:
        return []
    return [f"tier rule ({tr['units']} shared units): {tr['result']}"] + \
        [f"  {c['result']:4}  {c['rule']}: {c['value'][0]} vs {c['value'][1]}" for c in tr["conditions"].values()]


def phase_stats(rs: list[dict]) -> dict | None:
    """Median and p75 of each phase's wall (phase_wall) over the rows that carry one."""
    ph = [r["phases"] for r in rs if r.get("phases")]
    if not ph:
        return None
    return {k: med_p75([p[k] for p in ph if p.get(k) is not None]) for k in PHASES if any(k in p for p in ph)}


def summarize(rows: list[dict]) -> dict:
    unclean = sum(r.get("env_clean") is False for r in rows if "error" not in r)
    unknown = sum("env_clean" not in r for r in rows if "error" not in r)    # rows from before the clean room
    tags = sorted({str(r.get("tag")) for r in rows})
    rows = [r for r in rows if "error" not in r]
    out = {}
    for arm in arm_order(arm_of(r) for r in rows):
        rs = [r for r in rows if arm_of(r) == arm]
        med = lambda k: sorted(r.get(k) or 0 for r in rs)[len(rs) // 2]  # noqa: E731
        ok = sum(bool(r.get("ok")) for r in rs)
        out[arm] = {"ok": ok, "n": len(rs), "usd": round(sum(r.get("usd") or 0 for r in rs), 4),
                    "cps": round(sum(r.get("usd") or 0 for r in rs) / ok, 4) if ok else None,
                    "lead_only_usd_med": med("lead_only_usd"), "lead_tokens_med": med("lead_tokens"),
                    "lead_requests_med": med("lead_requests"), "wall_med": med("wall_s"),
                    **{k: v for k, v in wall_stats(rs).items() if k in ("wall_mean", "wall_p75")},
                    "wilson": S.wilson(ok, len(rs)),
                    # Wilson takes every row as an independent trial; a task's rounds are not: this one resamples
                    # tasks (task_boot), as the paired CIs do
                    "ok_rate_ci_tasks": task_boot([(r, r) for r in rs], ok_rate),
                    "ok_by_round": {str(rd): sum(bool(r.get("ok")) for r in rs if r.get("round") == rd)
                                    for rd in sorted({r.get("round") for r in rs}, key=round_key)}}
        n_tasks = len({r.get("task") for r in rs})
        if len(rs) > n_tasks:
            out[arm]["wilson_note"] = (f"{len(rs)} rows from {n_tasks} tasks: Wilson takes them as independent "
                                       "(too narrow); see ok_rate_ci_tasks")
        ph = phase_stats(rs)
        if ph:
            out[arm]["phases"] = ph
    res = {"arms": out, "by_tag": by_tag(rows), "unclean_rows": unclean, "env_unknown_rows": unknown, "tags": tags,
           "long_style": r4.summarize_long([{**r, "arm": arm_of(r)} for r in rows
                                            if arm_of(r) in r4.LONG_ARMS])["paired"],
           "paired": paired_all(rows)}
    tr = tier_rule(rows)
    if tr:
        res["tier_rule"] = tr
    if any(r.get("ext") for r in rows):
        # per code base, with each external task's commit date (results are reported per repository and by date:
        # a fix from before a model's training cutoff may be remembered)
        by: dict = {}
        for r in rows:
            e = r.get("ext") or {}
            cell = by.setdefault(e.get("repo") or "this repository", {}).setdefault(arm_of(r), {"ok": 0, "n": 0})
            cell["ok"] += bool(r.get("ok"))
            cell["n"] += 1
        res["by_repo"] = by
        res["ext_dates"] = {r["task"]: r["ext"].get("date") for r in rows if r.get("ext")}
    return res


def tagged(rows: list[dict], tag: str | None) -> list[dict]:
    """Rows of one tag (round), so rounds run under different conditions are never counted together."""
    return [r for r in rows if not tag or r.get("tag") == tag]


def cmd_summary(a) -> int:
    res = summarize(tagged(read_jsonl(results_file(a.taskset)), a.tag))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    for line in tier_rule_lines(res.get("tier_rule")):       # stdout stays one JSON object
        print(line, file=sys.stderr)
    return 0


def cmd_export(a) -> int:
    keep = ("tag", "taskset", "round", "task", "arm", "ok", "pytest", "rc", "wall_s", "usd", "lead_usd", "lead_only_usd",
            "sub_usd", "by_model_usd", "ccx_usd", "ccx_review_usd", "ccx_agents", "lead_requests", "lead_tokens",
            "lead_output_tokens", "lead_tools", "lead_edits", "agent_calls", "ccx_runs", "ccx_resumes", "rework",
            "delegated", "context_attached", "files_changed", "diffstat", "model", "status", "verdicts", "error",
            "env_clean", "fingerprint", "lead_model", "lead_effort", "phases")
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
    r.add_argument("--budget", type=float, default=3.0,
                   help="stop before a new unit once this tag's rows (plus --extra-spent) reach $")
    r.add_argument("--extra-spent", type=float, default=0.0, help="$ spent elsewhere, counted against --budget")
    r.add_argument("--lead-model", default="", help=f"the lead's Claude model (default: {DEFAULT_LEAD[0]}); "
                   "recorded in every row and its done-key")
    r.add_argument("--lead-effort", default="", help=f"the lead's effort (default: {DEFAULT_LEAD[1]})")
    r.add_argument("--jobs", type=int, default=2, help="tasks run at the same time")
    r.add_argument("--lead-budget", type=float, default=3.0, help="claude -p --max-budget-usd for one lead")
    r.add_argument("--out", default="")
    r.add_argument("--workdir", default="")
    r.add_argument("--timeout", type=int, default=2400)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-canary", action="store_true", help="skip the one tiny real lead that checks the isolation")
    r.add_argument("--ext-cache", default="", help="a folder with local copies (clones) of the other repositories "
                   "of the hold-out set, named after them, to clone from instead of their URLs")
    r.add_argument("--ext-python", default="", help="the Python that runs the other repositories' tests (needs "
                   "Python 3.11+, pytest and their test modules, e.g. freezegun, and not the libraries themselves; "
                   "keep it away from the --ext-cache folder; default: this one)")
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
