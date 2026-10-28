"""C3: could ccx reuse the builder's own passing check instead of running it again? A measurement only.

Offline, no model calls. For every recorded write run that had a `--check` (r5c..r5h hubs, review children left
out), read the builder's last attempt (events.<N>.log) and find the commands it ran after its last file edit:

  exact_pass   it ran ccx's check command as a whole statement (same text up to quotes and spaces, after the
               shell wrapper `powershell -Command '...'` / `bash -lc '...'` is taken off and the command is split
               on ; && || and new lines) and it passed
  exact_fail   it ran it and it failed
  exact_unclear it ran it inside a compound command whose output does not say how that statement ended
  other_pass   it ran some other test command (pytest/unittest/npm test ..., a narrower `file::test` or a wider
               set of files included) that exited 0, not ccx's command
  none         it ran no test after its last edit

Passed/failed: when the check is the whole command, its exit code (Claude Code: the tool result's is_error); in
a compound command the exit code is the last statement's, so the outcome is read from the output instead, and
only when the compound runs no other test command and the output has exactly one pytest summary line.

and compares that with ccx's own check result (run.json `check.passed`):

  match        exact_pass and ccx passed (the only case reuse could skip ccx's run)
  mismatch     exact_pass but ccx failed, or exact_fail but ccx passed (reuse would have been wrong)

Seconds: `check.seconds` of runs without a review are on the critical path (nothing runs beside them); with a
review they overlap it from #130 on (r5g/r5h) and are serial before. The report gives both, plus the seconds reuse
could have saved at most (match runs only).

  python scripts/eval/c3_check_reuse.py [--records <dir>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline_common as oc  # noqa: E402

TEST_WORDS = re.compile(r"\b(pytest|unittest|npm (run )?test|go test|cargo test|tox|nox)\b")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def norm(s: str) -> str:
    """A command's text with quotes and runs of spaces flattened (shell wrappers keep the inner text)."""
    return re.sub(r"\s+", " ", s.replace("\\\\", "\\").replace("'", '"').replace('"', "")).strip()


def builder_commands(log: Path) -> tuple[list[dict], int]:
    """(commands [{i, cmd, ok}], index of the last file edit or -1) of one attempt's event log, Codex
    (`item.completed` command_execution / file_change) or Claude Code (stream-json Bash / Edit tool calls)."""
    cmds, last_write, claude = [], -1, {}
    for i, e in enumerate(oc.read_jsonl(log)):
        it = e.get("item") or {}
        if e.get("type") == "item.completed":
            if it.get("type") == "file_change":
                last_write = i
            elif it.get("type") == "command_execution":
                cmds.append({"i": i, "cmd": it.get("command") or "", "ok": it.get("exit_code") == 0,
                             "out": it.get("aggregated_output") or ""})
            continue
        msg = e.get("message") or {}
        for c in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
            if not isinstance(c, dict):
                continue
            if e.get("type") == "assistant" and c.get("type") == "tool_use":
                if c.get("name") in WRITE_TOOLS:
                    last_write = i
                elif c.get("name") == "Bash":
                    row = {"i": i, "cmd": (c.get("input") or {}).get("command") or "", "ok": True, "out": ""}
                    cmds.append(row)
                    claude[c.get("id")] = row
            elif e.get("type") == "user" and c.get("type") == "tool_result" and c.get("tool_use_id") in claude:
                claude[c["tool_use_id"]]["ok"] = not c.get("is_error")
                t = c.get("content")
                if isinstance(t, list):
                    t = "\n".join(x.get("text", "") for x in t if isinstance(x, dict))
                claude[c["tool_use_id"]]["out"] = str(t or "")
    return cmds, last_write


WRAPPER = re.compile(r"""^\s*["']?[^"']*?\b(?:powershell|pwsh|bash|sh|zsh|cmd)(?:\.exe)?["']?"""
                     r"""(?:\s+-(?:NoProfile|NonInteractive|NoLogo|ExecutionPolicy\s+\S+))*"""
                     r"""\s+(?:-Command|-c|-lc|/c|/C)\s+(?P<inner>.*)$""", re.I | re.S)
SUMMARY = re.compile(r"^=*\s*(?:\d+ (?:passed|failed|errors?|skipped|deselected|xfailed|xpassed)[^\n]*"
                     r"| ?no tests ran[^\n]*)$", re.M)


def unwrap(cmd: str) -> str:
    """The command a shell wrapper runs (`powershell -Command '...'`, `bash -lc "..."`), outer quotes removed."""
    m = WRAPPER.match(cmd)
    if not m:
        return cmd
    inner = m["inner"].strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "'\"":
        inner = inner[1:-1]
    return inner


def statements(cmd: str) -> list[str]:
    """The statements of one shell command line, split on ; && || | and new lines outside quotes."""
    out, cur, q, k = [], "", "", 0
    while k < len(cmd):
        ch = cmd[k]
        if q:
            q = "" if ch == q else q
            cur += ch
        elif ch in "'\"":
            q, cur = ch, cur + ch
        elif cmd.startswith(("&&", "||"), k):
            out.append(cur)
            cur, k = "", k + 1
        elif ch in ";|\n":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        k += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def outcome(check_cmd: str, c: dict) -> bool | None:
    """Did ccx's check, run by the builder as one statement of `c`, pass? None when the command does not run it
    as a whole statement or its outcome cannot be told."""
    want = norm(check_cmd)
    parts = [norm(x) for x in statements(unwrap(c["cmd"]))]
    if not want or want not in parts:
        return None
    if len(parts) == 1:
        return c["ok"]
    if sum(bool(TEST_WORDS.search(x)) for x in parts) > 1:     # several test runs: their output is mixed
        return None
    lines = SUMMARY.findall(c.get("out") or "")
    if len(lines) != 1:
        return None
    line = lines[0]
    return "passed" in line and not re.search(r"\b(failed|errors?)\b", line)


def classify(check_cmd: str, cmds: list[dict], last_write: int) -> str:
    after = [c for c in cmds if c["i"] > last_write]
    want = norm(check_cmd)
    exact = [c for c in after if want and want in [norm(x) for x in statements(unwrap(c["cmd"]))]]
    if exact:
        ok = outcome(check_cmd, exact[-1])
        return "exact_unclear" if ok is None else "exact_pass" if ok else "exact_fail"
    if any(c["ok"] and TEST_WORDS.search(c["cmd"]) for c in after):
        return "other_pass"
    return "none"


def last_log(run_dir: Path) -> Path | None:
    logs = sorted(run_dir.glob("events.*.log"), key=lambda f: int(f.name.split(".")[1]) if
                  f.name.split(".")[1].isdigit() else -1)
    return logs[-1] if logs else None


def run_rows(base: Path, tags) -> list[dict]:
    rows = []
    for tag in tags:
        for f in sorted((Path(base) / tag).glob("h-*/ccx/runs/*/run.json")):
            try:
                r = oc.load(f)
            except (OSError, ValueError):
                continue
            chk = r.get("check") or {}
            if r.get("caller") == "ccx-review" or r.get("mode") != "write" or not chk.get("cmd"):
                continue
            log = last_log(f.parent)
            kind = classify(chk["cmd"], *builder_commands(log)) if log else "nolog"
            rv = r.get("review") or {}
            passed = bool(chk.get("passed"))
            agree = ("match" if kind == "exact_pass" and passed else
                     "mismatch" if (kind == "exact_pass" and not passed) or (kind == "exact_fail" and passed) else "")
            rows.append({"tag": tag, "unit": f.parents[3].name.removeprefix("h-"), "run_id": r.get("run_id"),
                         "fix_round": bool(r.get("resumed_from") or r.get("review_of")), "builder": kind,
                         "ccx_passed": passed, "agree": agree, "seconds": chk.get("seconds"),
                         "review": bool(rv.get("run_id") or rv.get("verdict")),
                         "tail": (chk.get("tail") or "")[-160:] if agree == "mismatch" else ""})
    return rows


def summarize(rows: list[dict]) -> dict:
    def secs(rs):
        s = [r["seconds"] for r in rs if r["seconds"] is not None]
        return {"n": len(s), "median": oc.median(s), "sum": round(sum(s), 1)}
    out = {"runs": len(rows), "builder": {}, "match": sum(r["agree"] == "match" for r in rows),
           "mismatch": sum(r["agree"] == "mismatch" for r in rows)}
    for k in ("exact_pass", "exact_fail", "exact_unclear", "other_pass", "none", "nolog"):
        out["builder"][k] = sum(r["builder"] == k for r in rows)
    out["check_seconds_no_review"] = secs([r for r in rows if not r["review"]])
    out["check_seconds_with_review"] = secs([r for r in rows if r["review"]])
    out["saveable_no_review"] = secs([r for r in rows if not r["review"] and r["agree"] == "match"])
    units: dict[str, list[dict]] = {}
    for r in rows:
        units.setdefault(f"{r['tag']}/{r['unit']}", []).append(r)
    nr = [sum(x["seconds"] or 0 for x in rs) for rs in units.values() if not any(x["review"] for x in rs)]
    out["units_no_review"] = {"n": len(nr), "median_check_seconds": oc.median(nr)}
    return out


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", default="", help="folder holding the round folders (default: temp_root())")
    ap.add_argument("--tags", default=",".join(oc.TAGS), type=lambda x: [t for t in x.split(",") if t])
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    rows = run_rows(Path(a.records) if a.records else oc.temp_root(), a.tags)
    s = summarize(rows)
    print(json.dumps(s, indent=1))
    for r in rows:
        if r["agree"] == "mismatch":
            print(f"  mismatch {r['tag']}/{r['unit']} {r['run_id']} builder={r['builder']} ccx_passed={r['ccx_passed']}"
                  f" | {r['tail'][-120:]!r}")
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": s, "rows": rows}, indent=1, ensure_ascii=False),
                                encoding="utf-8")
    return {"summary": s, "rows": rows}


if __name__ == "__main__":
    main()
