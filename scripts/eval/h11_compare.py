"""H11: does delegating through `ccx run` save the lead's tokens? A paired comparison on real CLIs.

Each pair is one task from tasks.py done twice, each time in a fresh scratch git repo by a fresh headless
Claude Code lead:
  self      the lead does the task with its own tools;
  delegate  the lead must hand the task to Codex with `ccx run --check ...` and may fix or follow up after.
The order of the two arms alternates between pairs (the prompt cache warms up over a batch). Afterwards a hidden
acceptance test the agents never saw decides right or wrong; the delegated run's verdict is recorded with
`ccx verify` (label eval-h11:<tag>:<task>). Spend is summed as it goes and the batch stops at --budget.

  python scripts/eval/h11_compare.py list
  python scripts/eval/h11_compare.py run --pairs 6 --budget 0.8 [--tasks slugify,roman] [--dry-run]
  python scripts/eval/h11_compare.py summary [--lead-context 219465]

Results go to .ccx/eval/h11/results.jsonl (git-ignored: it holds local paths). Needs logged-in `claude` and
`codex` CLIs; tests never call this.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CCX, ROOT, append_jsonl, boot_ci, ccx_rows, ccx_verify, make_repo, read_jsonl,  # noqa: E402
                    run_lead, score, sign_test, spent)
from tasks import TASKS, by_id  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "h11"
ACCEPT = "python -m pytest -q"
TAIL = (f"Acceptance: `{ACCEPT}` must pass. Make sure it does before you answer. Do not commit. "
        "Finish with one line: DONE or FAILED, and a short reason.")

SELF = "You are the lead agent in this repository.\nTask: {brief}\n" + TAIL + \
       "\nDo the work yourself with your own tools; do not delegate it to other agents."

DELEGATE = "You are the lead agent in this repository.\nTask: {brief}\n" + TAIL + """
Delegate the work to Codex instead of doing it yourself: write a short brief and run (one Bash call)
  {ccx} run --to codex --model {model} --effort {effort} --mode write --new --no-ab --review off --label {label} --check "{accept}" "<your brief>"
It prints a JSON result; ccx has already re-run the acceptance command (see its check field). If the sub-agent
failed, either follow up once with `{ccx} resume <run_id> "<what to fix>"` or fix it yourself."""


def run_arm(task: dict, arm: str, label: str, a, work: Path) -> dict:
    repo = make_repo(task, work / f"{task['id']}-{arm}")
    tmpl = SELF if arm == "self" else DELEGATE
    prompt = tmpl.format(brief=task["brief"], ccx=CCX, model=a.sub_model, effort=a.sub_effort, label=label,
                         accept=ACCEPT)
    lead = run_lead(prompt, repo, a.lead_model, a.lead_effort, a.lead_budget)
    sc = score(repo, task)
    row = {"tag": a.tag, "task": task["id"], "arm": arm, "label": label, "ts": time.time(),
           "lead_model": a.lead_model, "lead": lead, "ok": sc["ok"], "pytest": sc["pytest"]}
    if arm == "delegate":
        subs = ccx_rows(label)
        row.update(sub_runs=[r["run_id"] for r in subs], sub_ae_usd=round(sum(r.get("ae_usd") or 0 for r in subs), 6),
                   sub_seconds=round(sum(r.get("seconds") or 0 for r in subs), 1),
                   sub_ok=[r.get("ok") for r in subs], delegated=bool(subs),
                   resumed=sum("resume" in c for c in lead["bash"]),
                   lead_edits=lead["tools"].get("Edit", 0) + lead["tools"].get("Write", 0))
        if subs:   # the hidden test is the verdict on the delegated work as the lead left it
            row["verify"] = ccx_verify(subs[-1]["run_id"], sc["ok"], f"eval-h11 hidden acceptance: {sc['pytest']}")
    return row


def cmd_run(a) -> int:
    ids = a.tasks.split(",") if a.tasks else [t["id"] for t in TASKS]
    tasks = [by_id(i) for i in ids][: a.pairs]
    out = OUT / "results.jsonl"
    done = read_jsonl(out)
    work = Path(a.workdir or tempfile.mkdtemp(prefix="ccx-h11-"))
    print(f"work dir: {work}\nalready spent in results: ${spent(done):.3f}", flush=True)
    for i, task in enumerate(tasks):
        arms = ["self", "delegate"] if i % 2 == 0 else ["delegate", "self"]
        for arm in arms:
            if spent(read_jsonl(out)) >= a.budget:
                print(f"budget ${a.budget} reached: stopping", flush=True)
                return 2
            label = f"eval-h11:{a.tag}:{task['id']}"
            if a.dry_run:
                print(f"[dry] {task['id']} {arm} {label}")
                continue
            row = run_arm(task, arm, label, a, work)
            append_jsonl(out, row)
            L = row["lead"]
            print(f"{task['id']:10} {arm:8} ok={row['ok']} lead=${L['cost_usd']} req={L['requests']} "
                  f"ctx={L['context_tokens']} sub=${row.get('sub_ae_usd', 0)} {L['wall_s']}s", flush=True)
    return 0


def _pairs(rows: list[dict]) -> list[tuple[dict, dict]]:
    by = {}
    for r in rows:
        by.setdefault((r["tag"], r["task"]), {})[r["arm"]] = r
    return [(d["self"], d["delegate"]) for d in by.values() if "self" in d and "delegate" in d]


def summarize(rows: list[dict], lead_context: int) -> dict:
    pairs = _pairs(rows)

    def arm(i, f):
        return [f(p[i]) for p in pairs]

    def stats(xs):
        xs = [x for x in xs if x is not None]
        return {"n": len(xs), "median": statistics.median(xs) if xs else None,
                "mean": round(statistics.fmean(xs), 6) if xs else None}

    metrics = {
        "lead_usd": lambda r: r["lead"]["cost_usd"] or 0,
        "total_usd": lambda r: (r["lead"]["cost_usd"] or 0) + (r.get("sub_ae_usd") or 0),
        "lead_requests": lambda r: r["lead"]["requests"],
        "lead_context_tokens": lambda r: r["lead"]["context_tokens"],
        "lead_output_tokens": lambda r: r["lead"]["output_tokens"] or 0,
        "wall_s": lambda r: r["lead"]["wall_s"],
        # what the same number of lead requests would read in a long real conversation
        "lead_tokens_at_real_context": lambda r: r["lead"]["requests"] * lead_context,
    }
    res = {"pairs": len(pairs), "lead_context_assumed": lead_context, "metrics": {}}
    for name, f in metrics.items():
        s, d = arm(0, f), arm(1, f)
        diffs = [y - x for x, y in zip(s, d)]
        res["metrics"][name] = {"self": stats(s), "delegate": stats(d), "diff_median": stats(diffs)["median"],
                                "diff_ci95": boot_ci(diffs), "sign_p": sign_test(diffs)}
    res["ok"] = {"self": sum(p[0]["ok"] for p in pairs), "delegate": sum(p[1]["ok"] for p in pairs)}
    res["rework"] = {"resumed": sum(p[1].get("resumed", 0) > 0 for p in pairs),
                     "lead_edited_after_delegating": sum(p[1].get("lead_edits", 0) > 0 for p in pairs),
                     "did_not_delegate": sum(not p[1].get("delegated") for p in pairs),
                     "sub_check_failed": sum(any(o is False for o in p[1].get("sub_ok", [])) for p in pairs)}
    res["rows"] = [{"task": s["task"], "self_ok": s["ok"], "del_ok": d["ok"],
                    "self_usd": s["lead"]["cost_usd"], "del_lead_usd": d["lead"]["cost_usd"],
                    "del_sub_usd": d.get("sub_ae_usd"), "self_req": s["lead"]["requests"],
                    "del_req": d["lead"]["requests"], "self_ctx": s["lead"]["context_tokens"],
                    "del_ctx": d["lead"]["context_tokens"], "self_s": s["lead"]["wall_s"], "del_s": d["lead"]["wall_s"],
                    "del_sub_s": d.get("sub_seconds"), "resumed": d.get("resumed"), "lead_edits": d.get("lead_edits")}
                   for s, d in pairs]
    return res


def cmd_summary(a) -> int:
    rows = read_jsonl(Path(a.file) if a.file else OUT / "results.jsonl")
    if a.tag:
        rows = [r for r in rows if r["tag"] == a.tag]
    print(json.dumps(summarize(rows, a.lead_context), ensure_ascii=False, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=lambda a: print("\n".join(f"{t['id']:10} {t['brief'][:90]}" for t in TASKS)) or 0)
    r = sub.add_parser("run")
    r.add_argument("--pairs", type=int, default=8)
    r.add_argument("--tasks", default="")
    r.add_argument("--tag", default=time.strftime("%Y%m%d"))
    r.add_argument("--budget", type=float, default=0.8, help="stop before a new arm once results reach this ($)")
    r.add_argument("--lead-model", default="haiku")
    r.add_argument("--lead-effort", default="low")
    r.add_argument("--lead-budget", type=float, default=0.15, help="claude --max-budget-usd per lead")
    r.add_argument("--sub-model", default="gpt-6-luna")
    r.add_argument("--sub-effort", default="low")
    r.add_argument("--workdir", default="")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("--file", default="")
    s.add_argument("--tag", default="")
    s.add_argument("--lead-context", type=int, default=219465,
                   help="tokens one request of a real lead re-reads (ccx stats --summary: lead_turn_tokens_median)")
    s.set_defaults(fn=cmd_summary)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
