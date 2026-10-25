"""Warm lanes on real CLIs: round 2's ten small modules (PAR10) as one run (p1), ten runs side by side (p10), and
ten pieces in 2 or 3 warm lanes (`ccx batch --lanes N`: each lane continues one Codex session piece after piece).
Codex held to gpt-6-luna low; every unit in its own throwaway hub (CCX_HUB); the hidden tests decide right or wrong.

  python scripts/eval/warm_lanes.py run [--arms p1,p10,l2,l3] [--rounds 1] [--budget 1]
  python scripts/eval/warm_lanes.py summary

Results go to .ccx/eval/warm/results.jsonl. Needs a logged-in `codex`; tests never run this with real CLIs.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2  # noqa: E402
from common import ROOT, append_jsonl, git, make_repo, read_jsonl  # noqa: E402
from tasks_r2 import PAR10, PIECES, piece_brief  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "warm"
ARMS = ("p1", "p10", "l2", "l3")


def lanes_unit(u: dict, a, work: Path, n: int) -> dict:
    """Ten pieces, one task each, in n warm lanes; each lane's worktree branch merged back afterwards."""
    repo, hub = r2._paths(u, work)
    make_repo(PAR10, repo)
    hinfo = r2.make_hub(hub)
    plan = {"tasks": [{"id": f"{u['label']}:{p['id']}", "brief": piece_brief([p]), "to": "codex",
                       "model": "gpt-6-luna", "effort": "low", "mode": "write", "check": r2.ACCEPT,
                       "cwd": str(repo), "minutes": 5} for p in PIECES]}
    pf = work / f"{repo.name}.plan.json"
    pf.write_text(json.dumps(plan), encoding="utf-8")
    out, rc, wall, err = r2.ccx(["batch", str(pf), "--from", "user", "--lanes", str(n)], repo, hub, a.timeout * 3)
    res = out.get("results") or []
    conflicts, merged = 0, 0
    for wt in dict.fromkeys(r.get("worktree") for r in res if r.get("worktree")):
        if not Path(wt).is_dir():
            continue
        git(Path(wt), "add", "-A")
        git(Path(wt), "commit", "-q", "-m", "leftover")
        m = subprocess.run(["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "merge",
                            "--no-edit", f"ccx/{Path(wt).name}"], cwd=repo, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if m.returncode:
            conflicts += 1
            git(repo, "merge", "--abort")
        else:
            merged += 1
    sp = r2.score_pieces(repo)
    for r in res:
        r2.verify(hub, r.get("run_id"), bool(r.get("ok")) and not conflicts, "warm lane piece (see pieces_ok)")
    return {**u, "wall_s": wall, "rc": rc, "lanes": out.get("lanes"), "ok": sp["n_ok"] == 10, **sp,
            "conflicts": conflicts, "merged": merged, "warm": [r.get("warm") for r in res],
            "lane_of": [r.get("lane") for r in res], "lane_next": [r.get("lane_next") for r in res if r.get("lane_next")],
            "piece_tokens": [r2._tok(r.get("tokens")) for r in res], "ccx_ok": [r.get("ok") for r in res],
            "hub": hinfo, "stderr": err if rc else "", **r2.hub_cost(hub)}


def run_unit(u: dict, a, work: Path) -> dict:
    if u["arm"] == "p1":
        return r2.single_par(u, a, work, r2.LUNA, ["--no-subagents"])
    if u["arm"] == "p10":
        return r2.batch_unit(u, a, work, 10)
    return lanes_unit(u, a, work, int(u["arm"][1:]))


def cmd_run(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res_f = OUT / "results.jsonl"
    done = {(r["arm"], r["round"]) for r in read_jsonl(res_f)}
    spent = sum(r.get("usd") or 0 for r in read_jsonl(res_f))
    work = Path(tempfile.mkdtemp(prefix="ccx-warm-"))
    for k in range(a.rounds):
        for arm in a.arms.split(","):
            if (arm, k) in done:
                continue
            if spent >= a.budget:
                print(f"budget reached: ${spent:.4f}")
                return 2
            u = {"exp": "warm", "round": k, "task": "par10", "arm": arm, "label": f"eval-warm:{arm}:{k}"}
            t0 = time.time()
            row = run_unit(u, a, work)
            row["ts"] = t0
            append_jsonl(res_f, row)
            spent += row.get("usd") or 0
            print(f"{arm} r{k}: {row.get('n_ok')}/10 in {row['wall_s']}s, {row['tokens']} tokens, ${row['usd']:.4f}"
                  f" (total ${spent:.4f})", flush=True)
            try:
                from common import archive_hub
                archive_hub(work / f"hub-warm-{k}-par10-{arm}")
            except Exception:  # noqa: BLE001 — tidying sessions never fails the measurement
                pass
    return 0


def cmd_summary(a) -> int:
    rows = read_jsonl(OUT / "results.jsonl")
    print("| arm | n | right | wall s | tokens | USD | runs |")
    print("|---|---|---|---|---|---|---|")
    for arm in ARMS:
        g = [r for r in rows if r["arm"] == arm]
        if not g:
            continue
        def col(fmt, g=g):
            return " / ".join(fmt(r) for r in g)
        print(f"| {arm} | {len(g)} | {col(lambda r: str(r.get('n_ok')) + '/10')} | {col(lambda r: str(r['wall_s']))} | "
              f"{col(lambda r: str(r['tokens']))} | {col(lambda r: format(r['usd'], '.4f'))} | "
              f"{col(lambda r: str(r['n_runs']))} |")
    if rows:
        print(f"\ntotal ${sum(r.get('usd') or 0 for r in rows):.4f}; median wall by arm:",
              {arm: statistics.median([r["wall_s"] for r in rows if r["arm"] == arm])
               for arm in ARMS if any(r["arm"] == arm for r in rows)})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--rounds", type=int, default=1)
    r.add_argument("--budget", type=float, default=1.0, help="stop before a unit once this much is spent (USD)")
    r.add_argument("--timeout", type=int, default=600)
    r.set_defaults(fn=cmd_run)
    sub.add_parser("summary").set_defaults(fn=cmd_summary)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
