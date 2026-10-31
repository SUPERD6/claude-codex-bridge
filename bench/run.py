"""Run the public benchmark (bench/README.md) and print its results table.

A thin wrapper over scripts/eval/r5.py, which does the work: a clean-environment check, one fresh repository and hub
per unit, the lead, the hidden tests, one result row per unit. This file only picks the arguments and prints a table
in the same form as the README's.

    python bench/run.py run --set holdout --arm self --tasks hz-intword-carry     # one unit, about $0.05-0.15
    python bench/run.py run --set holdout --arm self                              # the whole set, one round
    python bench/run.py run --set holdout --arm ccx --codex-home <your eval Codex home>
    python bench/run.py run ... --dry-run                                         # the schedule and its cost only
    python bench/run.py table bench/results/hc1.jsonl                             # our published rows
    python bench/run.py table bench/runs/holdout-<commit>-results.jsonl           # yours

Anything after `--` goes to r5.py as it is (`python scripts/eval/r5.py run -h` lists it).
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R5 = ROOT / "scripts" / "eval" / "r5.py"
RUNS = Path(__file__).resolve().parent / "runs"            # git-ignored
ARMS = {"self": "self", "ccx": "ccx2", "builtin": "builtin"}   # this README's names -> r5.py's arms
LABEL = {"self": "self (the lead does it itself)", "ccx2": "ccx2 (delegated to Codex through ccx)",
         "builtin": "builtin (Claude Code's built-in sub-agent)", "ccx": "ccx (the first lead wording, r5 only)"}


def head() -> str:
    return subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def r5_argv(a, extra: list[str]) -> tuple[list[str], Path, str]:
    """r5.py's command line, the results file and the tag. A tag runs on one commit (r5.py refuses otherwise), so the
    default tag names the set and the commit."""
    tag = a.tag or f"{a.set}-{head()}"
    out = Path(a.out) if a.out else RUNS / f"{tag}-results.jsonl"
    argv = [sys.executable, str(R5), "run", "--taskset", a.set, "--arms", ARMS[a.arm], "--rounds", str(a.rounds),
            "--tag", tag, "--budget", str(a.budget), "--out", str(out), "--jobs", str(a.jobs)]
    if a.tasks:
        argv += ["--tasks", a.tasks]
    if a.codex_home:
        argv += ["--codex-home", a.codex_home]
    if a.dry_run:
        argv.append("--dry-run")
    return argv + extra, out, tag


def median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def table(rows: list[dict], tag: str | None = None) -> str:
    """One line per (tag, arm): right / units, cost per success (all the units' spend over the right ones), true
    median wall time. Rows a clean-environment check marked unclean (env_clean False) are left out and counted;
    rows from before that check existed (no env_clean, the r5 dev runs) are kept, as in docs/measured.md."""
    if tag:
        rows = [r for r in rows if r.get("tag") == tag]
    groups: dict[tuple[str, str], list[dict]] = {}
    dropped: dict[tuple[str, str], int] = {}
    for r in rows:
        k = (r.get("tag") or "?", r.get("arm") or "?")
        if r.get("env_clean") is False:
            dropped[k] = dropped.get(k, 0) + 1
            continue
        groups.setdefault(k, []).append(r)
    out = ["| Tag | Arm | Right | Cost per success | Wall, median |", "|---|---|---|---|---|"]
    for (t, arm), rs in sorted(groups.items()):
        right = sum(1 for r in rs if r.get("ok"))
        usd = sum(float(r.get("usd") or 0) for r in rs)
        cps = f"${usd / right:.3f}" if right else "-"
        wall = median([float(r["wall_s"]) for r in rs if r.get("wall_s") is not None])
        out.append(f"| {t} | {LABEL.get(arm, arm)} | {right}/{len(rs)} | {cps} | {wall:.0f} s |")
    for (t, arm), n in sorted(dropped.items()):
        out.append(f"\n{t} {arm}: {n} row(s) not counted (env_clean false: the clean-environment check failed)")
    return "\n".join(out)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def cmd_run(a, extra: list[str]) -> int:
    argv, out, tag = r5_argv(a, extra)
    out.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(argv[1:]), flush=True)
    rc = subprocess.run(argv, cwd=ROOT).returncode
    rows = read_rows(out)
    if rows and not a.dry_run:
        print(f"\nresults: {out}\n")
        print(table(rows, tag))
    return rc


def cmd_table(a, extra: list[str]) -> int:
    if extra:
        raise SystemExit(f"table takes no extra arguments: {' '.join(extra)}")
    rows = [r for f in a.files for r in read_rows(Path(f))]
    if not rows:
        raise SystemExit("no rows in " + ", ".join(a.files))
    print(table(rows, a.tag))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run units through scripts/eval/r5.py, then print their table")
    r.add_argument("--set", choices=("holdout", "r5"), default="holdout", help="task set (default: holdout)")
    r.add_argument("--arm", choices=sorted(ARMS), default="self",
                   help="self (default, needs only Claude Code), ccx (also Codex and --codex-home), builtin")
    r.add_argument("--tasks", default="", help="comma-separated task ids (default: the whole set); see bench/tasks/")
    r.add_argument("--rounds", type=int, default=1)
    r.add_argument("--budget", type=float, default=2.0, help="stop before a new unit once this run has spent $")
    r.add_argument("--jobs", type=int, default=1, help="units at the same time (1 keeps wall times comparable)")
    r.add_argument("--tag", default="", help="default: <set>-<commit>")
    r.add_argument("--out", default="", help="results file (default: bench/runs/<tag>-results.jsonl)")
    r.add_argument("--codex-home", default="", help="ccx arm: a dedicated CODEX_HOME you logged in to once")
    r.add_argument("--dry-run", action="store_true", help="print the schedule and its cost estimate, run nothing")
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser("table", help="print the results table of one or more results files")
    t.add_argument("files", nargs="+")
    t.add_argument("--tag", default=None, help="only this tag's rows")
    t.set_defaults(fn=cmd_table)
    return ap


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    a = parser().parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    return a.fn(a, extra)


if __name__ == "__main__":
    sys.exit(main())
