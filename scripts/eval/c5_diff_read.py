"""C5: base rate of "the lead did not read the diff", in units that ended right versus wrong. Offline, no model calls.

The failure analysis found that the wrong ccx2 units had a lead that never looked at the diff, but had no control
group: how often did the lead skip the diff in units that ended right? If it skips it just as often there, "read
the diff" cannot tell right from wrong and a conditional read-the-diff skill variant has nothing to stand on.

For every recorded lead stream (<tag>/<round>-<task>-<arm>.stream.jsonl) whose lead delegated (a `ccx run` /
`ccx resume` Bash call, or an Agent call), the lead's own tool calls after its first delegation are sorted into:

  diff     a Bash `git diff` / `git show` / `git log -p` that prints content (not only --stat / --name-only)
  file     a Read / Grep / Bash cat|type|Get-Content of a file the unit changed (since its "start" commit)
  none     neither

and joined with the unit's scored row (`ok`, results.jsonl). The table is per arm: right and wrong units, how many
had no diff read (strict: no `diff`; broad: neither `diff` nor `file`), and a two-sided Fisher exact p.

  python scripts/eval/c5_diff_read.py [--records <dir>] [--results <results.jsonl>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import offline_common as oc  # noqa: E402

DELEGATE = re.compile(r"\bccx(\.py)?\"?\s+(run|resume)\b")
GIT_DIFF = re.compile(r"\bgit\b(\s+-C\s+\S+)?(\s+-c\s+\S+)*\s+(diff|show|log\s+[^|;&]*-p)\b")
STAT_ONLY = re.compile(r"--(stat|shortstat|numstat|name-only|name-status|quiet|exit-code|check)\b")
CAT = re.compile(r"\b(cat|type|Get-Content|gc|head|tail|sed|less|more)\b")


def diff_commands(cmd: str) -> bool:
    """True when one of the shell command's parts prints diff content (a `git diff --stat` part alone does not)."""
    for part in re.split(r"&&|\|\||;|\n", cmd):
        if GIT_DIFF.search(part) and not STAT_ONLY.search(part):
            return True
    return False


def changed_files(repo: Path) -> set[str]:
    base = (oc.git(repo, "rev-list", "--max-parents=0", "HEAD").split() or [""])[-1]
    if not base:
        return set()
    names = set(oc.git(repo, "diff", "--name-only", base).split("\n"))
    names |= set(oc.git(repo, "ls-files", "--others", "--exclude-standard").split("\n"))
    return {n for n in names if n}


def lead_reads(calls: list[dict], changed: set[str]) -> dict:
    """{'delegated', 'diff', 'file'} of one lead's calls (only the calls after its first delegation count)."""
    first = next((c["i"] for c in calls if c["name"] in ("Agent", "Task")
                  or (c["name"] == "Bash" and DELEGATE.search(str(c["input"].get("command") or "")))), None)
    out = {"delegated": first is not None, "diff": False, "file": False}
    if first is None:
        return out
    tails = {n.split("/")[-1] for n in changed}
    for c in calls:
        if c["i"] <= first:
            continue
        inp = c["input"] or {}
        if c["name"] == "Bash":
            cmd = str(inp.get("command") or "")
            if diff_commands(cmd):
                out["diff"] = True
            elif CAT.search(cmd) and any(n in cmd.replace("\\", "/") for n in changed):
                out["file"] = True
        elif c["name"] in ("Read", "Grep"):
            p = str(inp.get("file_path") or inp.get("path") or "").replace("\\", "/")
            if p and (any(p.endswith(n) for n in changed) or p.split("/")[-1] in tails):
                out["file"] = True
    return out


def unit_rows(base: Path, results: dict[str, dict], tags) -> list[dict]:
    rows = []
    for tag in tags:
        for s in sorted((Path(base) / tag).glob("*.stream.jsonl")):
            unit = s.name.removesuffix(".stream.jsonl")
            key = oc.unit_key(tag, unit)
            row = results.get(key)
            if not row or row.get("ok") is None:
                continue
            repo = Path(base) / tag / unit
            reads = lead_reads(oc.lead_tool_calls(s), changed_files(repo) if (repo / ".git").exists() else set())
            if not reads["delegated"]:
                continue
            rows.append({"label": key, "arm": row.get("arm") or oc.UNIT.match(unit)["arm"], "ok": bool(row["ok"]),
                         **reads})
    return rows


def table(rows: list[dict]) -> dict:
    out = {}
    for arm in sorted({r["arm"] for r in rows}) + ["all"]:
        rs = [r for r in rows if arm == "all" or r["arm"] == arm]
        right, wrong = [r for r in rs if r["ok"]], [r for r in rs if not r["ok"]]
        t = {"right": len(right), "wrong": len(wrong)}
        for name, miss in (("strict", lambda r: not r["diff"]), ("broad", lambda r: not (r["diff"] or r["file"]))):
            a, c = sum(map(miss, right)), sum(map(miss, wrong))
            t[f"no_read_{name}_right"], t[f"no_read_{name}_wrong"] = a, c
            t[f"p_{name}"] = (round(oc.fisher_exact(a, len(right) - a, c, len(wrong) - c), 4)
                              if right and wrong else None)
        out[arm] = t
    return out


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="", help="folder holding the round folders (default: temp_root())")
    ap.add_argument("--results", default=str(ROOT / ".ccx/eval/r5/results.jsonl"))
    ap.add_argument("--tags", default=",".join(oc.TAGS), type=lambda x: [t for t in x.split(",") if t])
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    rows = unit_rows(Path(a.records) if a.records else oc.temp_root(), oc.results(Path(a.results), a.tags), a.tags)
    t = table(rows)
    print(json.dumps(t, indent=1))
    for r in rows:
        if not r["ok"]:
            print(f"  wrong {r['label']}: diff={r['diff']} file={r['file']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"table": t, "rows": rows}, indent=1), encoding="utf-8")
    return {"table": t, "rows": rows}


if __name__ == "__main__":
    main()
