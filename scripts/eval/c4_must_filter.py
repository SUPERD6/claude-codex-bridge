"""C4: would a stronger reviewer, filtering the first review's [must] items, keep the fix rounds that saved a unit
and drop the ones that "fixed" code that was already right? Written, priced, NOT run yet (it spends money).

Input: the fix-round replay rows (scripts/eval/fixround_replay.py --json; each row has the reviewed run, its
[must] issues and `outcome` = pass->pass / fail->pass / fail->fail measured with the hidden test). For each row
with an outcome, a filter review is built: the recorded review brief of that run (task, summary, diff, checks)
followed by the first reviewer's [must] items and the question "keep or drop each one". It runs read-only on the
tree the first reviewer saw (rebuilt as fixround_replay.py does), in the round-5 clean room, with --model/--effort
(default sonnet medium) through review_replay.py's runner.

Gate (improvement plan, C4): every fail->pass round must keep at least one [must] (10/10 rescues kept; 9/9 here,
the 10th had no [must] items); what it would save is the pass->pass rounds where every [must] is dropped (no fix
round would start). A rescue the filter did not judge (failed, unparsed, skipped, or cut by --budget) counts as
not kept: the gate is over every planned rescue, never over the parsed subset.

  python scripts/eval/c4_must_filter.py --rows fixreplay-rows.json --dry-run      # rounds, prompt sizes, $ estimate
  python scripts/eval/c4_must_filter.py --rows ... --budget 1.0 --out c4.json     # spends money
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline_common as oc  # noqa: E402

PRICES = {"sonnet": (3.0, 15.0), "opus": (5.0, 25.0), "haiku": (1.0, 5.0)}   # $ per million input / output tokens
EXPLORE_TOKENS = 25_000      # a read-only reviewer reads files besides its brief (round 5 haiku reviews: ~20-40k)
OUT_TOKENS = 1_500
ASK = """## The first reviewer's [must] items
{items}

## Answer
You are the second reviewer. You cannot run commands; read the diff and the files. For each [must] item above decide
whether it is real: the change really fails a requirement the task states (quote it), breaks existing behaviour, or
fails silently on the task's normal path. Answer one line per item, in the same order, starting with `[keep] ` or
`[drop] ` followed by the item's first words and one short reason. Start summary with `FILTER: keep N of M`. Status
done."""


def filter_brief(review_prompt: str, issues: list[str]) -> str:
    """The recorded review brief up to its own Answer section, then the first reviewer's items and the question."""
    head = review_prompt.split("\n## Answer", 1)[0].rstrip()
    items = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(issues))
    return head + "\n\n" + ASK.format(items=items)


def decisions(items: list[str]) -> list[str]:
    return [m.group(1).lower() for x in items if (m := re.match(r"\s*(?:\d+\.\s*)?\[(keep|drop)\]", x, re.I))]


def estimate(chars: int, model: str) -> float:
    pin, pout = PRICES.get(model, PRICES["sonnet"])
    return (chars / 3.5 + EXPLORE_TOKENS) * pin / 1e6 + OUT_TOKENS * pout / 1e6


def review_text(hub: Path, rid: str) -> str | None:
    runs = oc.hub_runs(hub)
    rev = (runs.get(rid) or {}).get("review") or {}
    rr = runs.get(rev.get("run_id") or "")
    if not rr:
        return None
    raw = (Path(rr["_dir"]) / "prompt.md").read_bytes().decode("utf-8", "replace")
    return raw.replace("\r\n", "\n")


def plan(rows: list[dict], model: str) -> dict:
    jobs, skipped = [], []
    for r in rows:
        if not r.get("outcome") or not r.get("issues"):
            continue
        musts = [x for x in r["issues"] if str(x).lstrip().lower().startswith("[must]")] or r["issues"]
        text = review_text(Path(r["hub"]), r["run"])
        if not text:
            skipped.append({"run": r["run"], "outcome": r["outcome"]})
            continue
        b = filter_brief(text, musts)
        jobs.append({"run": r["run"], "label": r.get("label"), "outcome": r["outcome"], "musts": len(musts),
                     "chars": len(b), "usd": round(estimate(len(b), model), 4), "brief": b, "row": r})
    return {"model": model, "rounds": len(jobs), "skipped": skipped,
            "by_outcome": {o: sum(j["outcome"] == o for j in jobs) for o in sorted({j["outcome"] for j in jobs})},
            "est_usd": round(sum(j["usd"] for j in jobs), 2), "jobs": jobs}


def gate(results: list[dict], planned: list[dict] | None = None) -> dict:
    """Rescues kept (fail->pass rounds with at least one keep) and wasted rounds saved (pass->pass, all dropped).

    The denominator is every planned round (`planned`: [{run, outcome}], the plan's jobs plus the rounds it had to
    skip), not only the ones that came back parsed: a rescue whose filter review failed, timed out, was not parsed,
    lost its tree or never ran (budget) is `rescues_unjudged` and counts as NOT kept, so the gate cannot pass on a
    parsed subset. Without `planned` the results themselves are the plan."""
    out = {"rescues": 0, "rescues_kept": 0, "rescues_unjudged": 0, "wasted": 0, "wasted_dropped": 0,
           "unparsed": 0}
    left: dict[str, list[dict]] = {}
    for r in results:
        left.setdefault(str(r.get("run")), []).append(r)
    for pl in (results if planned is None else planned):
        got = left.get(str(pl.get("run"))) or []
        r = (got.pop(0) if got else None) if planned is not None else pl
        judged = r is not None and r.get("ok") is not False and not r.get("skip")
        d = decisions((r or {}).get("items") or []) if judged else []
        if not d:
            out["unparsed"] += 1
        if pl.get("outcome") == "fail->pass":
            out["rescues"] += 1
            if not d:
                out["rescues_unjudged"] += 1
            else:
                out["rescues_kept"] += "keep" in d
        elif pl.get("outcome") == "pass->pass" and d:
            out["wasted"] += 1
            out["wasted_dropped"] += all(x == "drop" for x in d)
    out["passes_gate"] = out["rescues"] > 0 and out["rescues_kept"] == out["rescues"]
    return out


def run(p: dict, budget: float, effort: str, work: Path, timeout: int) -> list[dict]:     # pragma: no cover - paid
    import fixround_replay as FR
    import review_replay as RR
    results, spent = [], 0.0
    for j in p["jobs"]:
        if spent + j["usd"] * 2 > budget:
            break
        r = j["row"]
        repo = Path(r["hub"]).parent / Path(r["hub"]).name.removeprefix("h-")
        text = review_text(Path(r["hub"]), r["run"]) or ""
        diff, _cut = FR.extract_diff(text)
        _p, final_new = FR.final_state(repo, r["base"])
        patch, new, _n, why = FR.state_from_prompt(diff or "", final_new)
        tree = work / "trees" / j["run"]
        if why or (not tree.exists() and FR.build_tree(repo, r["base"], tree, patch, new)):
            results.append({**j, "skip": why or "tree"})
            continue
        c = {"id": j["run"], "tree": str(tree), "brief": {}, "run_id": r["run"], "recorded_text": ""}
        res = RR.run_job(c, "filter", 0, {"filter": RR.ROOT}, work, timeout,
                         {"text": j["brief"], "model": p["model"], "effort": effort})
        spent += res.get("usd") or 0
        results.append({**{k: v for k, v in j.items() if k not in ("brief", "row")}, **res, "outcome": j["outcome"]})
    return results


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True, help="fixround_replay.py --json output")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget", type=float, default=0.0)
    ap.add_argument("--work", default="")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    data = oc.load(Path(a.rows))
    p = plan(data["rows"] if isinstance(data, dict) else data, a.model)
    show = {k: v for k, v in p.items() if k != "jobs"}
    show["prompt_chars_median"] = oc.median([j["chars"] for j in p["jobs"]])
    print(json.dumps(show))
    if a.dry_run:
        return show
    if p["est_usd"] > a.budget:
        raise SystemExit(f"estimate ${p['est_usd']} is over --budget ${a.budget}")
    results = run(p, a.budget, a.effort, Path(a.work or tempfile.mkdtemp(prefix="c4-")).resolve(), a.timeout)
    planned = [{"run": j["run"], "outcome": j["outcome"]} for j in p["jobs"]] + p["skipped"]
    out = {**show, "gate": gate(results, planned), "results": results}
    print(json.dumps(out["gate"]))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
