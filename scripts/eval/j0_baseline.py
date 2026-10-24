"""J0: the lead's own cost, measured the same way before and after proposal J (J1 fixed overhead, J2 cache breaks,
J3 compressed outputs, J6 a one-page STATUS).

  python scripts/eval/j0_baseline.py real [--days 7]          # free: the real lead sessions + the ledger
  python scripts/eval/j0_baseline.py tasks --ref HEAD [--repeat 2] [--model haiku]
  python scripts/eval/j0_baseline.py summary [--tag TAG]

`real` reads what already happened (no model calls): per lead request, the tokens it re-read (new input + cache
writes + cache reads), its API-equivalent cost, the cache read / write shares, how many requests broke the cache (a
cache write of 20k+ tokens and over half of the request), and what ccx sub-runs cost in the same window.

`tasks` runs a fixed set of lead tasks in a fresh clone of this repo at `--ref`, each by a new headless Claude Code
lead with the person's DEFAULT setup (their CLAUDE.md, hooks, skills and MCP — what J1–J3 and J6 change; no slim
flags). Each answer is checked against facts read from the clone itself, so "acceptance" means the same before and
after. Per run: requests, tokens re-read per request (first request = fixed start-up overhead), cache shares, $.
Run it now, and again with the same arguments after J lands; compare with `summary`.
Results go to .ccx/eval/j0/ (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, append_jsonl, git, lead_env, read_jsonl  # noqa: E402

from ccx import learn, ledger  # noqa: E402
from ccx.config import paths  # noqa: E402
from ccx.runners import bin_argv  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "j0"
BREAK_MIN = 20_000      # a cache write this big, and over half the request, counts as a cache break (J2)

# The three things a lead does all day here: get its bearings, look at a large output, read code to answer.
TASKS = {
    "orient": "You are starting work on this repository. Follow its own start-here instructions for coding agents. "
              "Then answer in at most 6 lines: the package version, and the next 3 steps the project lists.",
    "diff": "Summarise what the last 3 commits changed (look at `git diff HEAD~3 HEAD`), in at most 6 bullets. "
            "Name the files that changed most.",
    "code": "Where is `ccx verify --sweep` implemented, and how does it decide that a run was probably right? "
            "Answer in at most 5 lines and name the function.",
}


def expected(clone: Path) -> dict:
    """Facts each answer must contain, read from the clone (so the check moves with the code)."""
    ver = re.search(r'__version__\s*=\s*"([^"]+)"', (clone / "ccx" / "__init__.py").read_text(encoding="utf-8"))
    files = [l.split("|")[0].strip() for l in git(clone, "diff", "--stat", "HEAD~3", "HEAD").splitlines() if "|" in l]
    sweep = sorted({m.group(1) for f in (clone / "ccx").rglob("*.py")
                    for m in re.finditer(r"def (\w*(?:sweep|soft_verdict)\w*)\(", f.read_text(encoding="utf-8"))})
    return {"orient": [ver.group(1)] if ver else [], "diff": [Path(f).name for f in files],
            "code": sweep}


def accepted(task: str, answer: str, facts: dict) -> bool:
    want = facts.get(task) or []
    return bool(want) and any(w and w in answer for w in want)


def per_request(stdout: str) -> list[dict]:
    """One row per API request (deduplicated by message id) from Claude's stream-json."""
    msgs: dict[str, dict] = {}
    final = {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant" and (ev.get("message") or {}).get("id"):
            m = ev["message"]
            msgs[m["id"]] = m.get("usage") or {}
        elif ev.get("type") == "result":
            final = ev
    rows = [{"fresh": u.get("input_tokens", 0) or 0, "write": u.get("cache_creation_input_tokens", 0) or 0,
             "read": u.get("cache_read_input_tokens", 0) or 0, "out": u.get("output_tokens", 0) or 0}
            for u in msgs.values()]
    return rows, final


def shares(rows: list[dict]) -> dict:
    tok = [r["fresh"] + r["write"] + r["read"] for r in rows]
    total = sum(tok) or 1
    return {"requests": len(rows), "first_request_tokens": tok[0] if tok else 0,
            "median_request_tokens": statistics.median(tok) if tok else 0, "max_request_tokens": max(tok, default=0),
            "tokens_read": sum(tok), "cache_read_share": round(sum(r["read"] for r in rows) / total, 3),
            "cache_write_share": round(sum(r["write"] for r in rows) / total, 3),
            "cache_breaks": sum(r["write"] >= BREAK_MIN and r["write"] > t / 2 for r, t in zip(rows, tok)),
            "output_tokens": sum(r["out"] for r in rows)}


def cmd_tasks(a) -> int:
    work = Path(a.workdir or tempfile.mkdtemp(prefix="ccx-j0-"))
    clone = work / "repo"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(clone)], check=True)
    git(clone, "checkout", "-q", a.ref)
    commit = git(clone, "rev-parse", "--short", "HEAD").strip()
    facts = expected(clone)
    tag = a.tag or f"{time.strftime('%Y%m%d')}-{commit}"
    for rep in range(1, a.repeat + 1):
        for task, prompt in TASKS.items():
            argv = [*bin_argv("claude"), "-p", "--output-format", "stream-json", "--verbose", "--model", a.model,
                    "--effort", a.effort, "--permission-mode", "dontAsk", "--allowed-tools",
                    "Read Grep Glob Bash(git:*) Bash(ls:*) Bash(cat:*) Bash(python:*)",
                    "--no-session-persistence", "--max-budget-usd", str(a.lead_budget)]
            t0 = time.time()
            r = subprocess.run(argv, input=prompt, cwd=clone, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=lead_env(), timeout=900)
            rows, final = per_request(r.stdout)
            answer = str(final.get("result", ""))
            row = {"tag": tag, "ref": a.ref, "commit": commit, "task": task, "rep": rep, "model": a.model,
                   "ok": accepted(task, answer, facts), "cost_usd": final.get("total_cost_usd"),
                   "wall_s": round(time.time() - t0, 1), **shares(rows), "per_request": rows,
                   "answer": answer[-600:], "expected": facts.get(task), "ts": time.time()}
            append_jsonl(OUT / "tasks.jsonl", row)
            print(json.dumps({k: row[k] for k in ("task", "rep", "ok", "cost_usd", "requests", "first_request_tokens",
                                                  "median_request_tokens", "tokens_read", "cache_read_share",
                                                  "cache_breaks", "wall_s")}), flush=True)
    return 0


def cmd_real(a) -> int:
    from ccx import usage
    p = paths()
    since = time.time() - a.days * 86400
    runs = [r for r in ledger.rows(p) if not r.get("type")]
    mine = {s for r in runs for s in r.get("sessions", [])}
    evs, _ = usage.lead_events(since, mine)
    out = {"days": a.days, "taken": time.strftime("%Y-%m-%d %H:%M"), "lead": {}}
    for agent in ("claude", "codex"):
        es = [e for e in evs if e["agent"] == agent and e.get("role") == "lead"]
        if not es:
            continue
        tok = [e["usage"].get("input_tokens", 0) + e["usage"].get("cache_write_tokens", 0)
               + e["usage"].get("cached_input_tokens", 0) for e in es]
        usd = [learn.price_usd(p, agent, e.get("model") or "", e["usage"]) or 0 for e in es]
        tot = sum(tok) or 1
        writes = [e["usage"].get("cache_write_tokens", 0) for e in es]
        q = statistics.quantiles(tok, n=10) if len(tok) >= 10 else [None] * 9
        out["lead"][agent] = {
            "requests": len(es), "sessions": len({e["session"] for e in es}),
            "median_request_tokens": statistics.median(tok), "p90_request_tokens": q[8],
            "median_request_usd": round(statistics.median(usd), 4), "mean_request_usd": round(statistics.fmean(usd), 4),
            "total_usd": round(sum(usd), 2),
            "cache_read_share": round(sum(e["usage"].get("cached_input_tokens", 0) for e in es) / tot, 3),
            "cache_write_share": round(sum(writes) / tot, 3),
            "cache_breaks": sum(w >= BREAK_MIN and w > t / 2 for w, t in zip(writes, tok)),
            "cache_break_usd": round(sum(u for u, w, t in zip(usd, writes, tok) if w >= BREAK_MIN and w > t / 2), 2),
            "models": sorted({e.get("model") or "?" for e in es})}
    sub = [r for r in runs if (r.get("ts") or 0) >= since]
    out["sub_runs"] = {"runs": len(sub), "ae_usd": round(sum(r.get("ae_usd") or 0 for r in sub), 4),
                       "eval_runs": sum((r.get("label") or "").startswith("eval-") for r in sub)}
    append_jsonl(OUT / "real.jsonl", out)
    print(json.dumps(out, indent=1))
    return 0


def cmd_summary(a) -> int:
    rows = [r for r in read_jsonl(OUT / "tasks.jsonl") if not a.tag or r["tag"] == a.tag]
    out: dict = {}
    for r in rows:
        out.setdefault(r["tag"], {}).setdefault(r["task"], []).append(r)
    res = {}
    for tag, by in out.items():
        res[tag] = {}
        for task, rs in by.items():
            med = lambda k: statistics.median([x[k] for x in rs])  # noqa: E731
            res[tag][task] = {"n": len(rs), "ok": sum(x["ok"] for x in rs), "usd": med("cost_usd"),
                              "requests": med("requests"), "first_request_tokens": med("first_request_tokens"),
                              "median_request_tokens": med("median_request_tokens"), "tokens_read": med("tokens_read"),
                              "cache_read_share": med("cache_read_share"), "cache_breaks": med("cache_breaks"),
                              "wall_s": med("wall_s")}
    print(json.dumps(res, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("real")
    r.add_argument("--days", type=float, default=7)
    r.set_defaults(fn=cmd_real)
    t = sub.add_parser("tasks")
    t.add_argument("--ref", default="HEAD")
    t.add_argument("--repeat", type=int, default=2)
    t.add_argument("--model", default="haiku")
    t.add_argument("--effort", default="low")
    t.add_argument("--lead-budget", type=float, default=0.25)
    t.add_argument("--tag", default="")
    t.add_argument("--workdir", default="")
    t.set_defaults(fn=cmd_tasks)
    s = sub.add_parser("summary")
    s.add_argument("--tag", default="")
    s.set_defaults(fn=cmd_summary)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
