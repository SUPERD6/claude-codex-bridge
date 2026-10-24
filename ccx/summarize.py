"""Long command output, cut down by code before the lead reads it (proposal J3). Whatever enters the lead's
conversation is re-read on every later turn, so a 3,000-line test log costs far more than the minute it took to
run. `ccx sum -- <command>` runs the command, keeps the full output in .ccx/sum/, and prints only what matters:
failures and their last frames for tests, a per-file summary and the first hunks for diffs, error lines with a
little context for logs. Too long even then: `--ask "..."` lets a cheap routed model answer from the saved log."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

MAX_CHARS = 2_000
TAIL = 12
ERR = re.compile(r"error|fail|exception|traceback|fatal|denied|not found|panic|refused|timed? ?out|warn",
                 re.IGNORECASE)
TEST_SUMMARY = re.compile(r"^(=+ .*(passed|failed|error).* =+|Ran \d+ tests? in .*|OK( \(.*\))?|FAILED \(.*\)|"
                          r"\d+ (passed|failed)|Tests?: .*|test result: .*)$", re.IGNORECASE)


def kind_of(text: str, argv: list[str]) -> str:
    head = text[:4000]
    cmd = " ".join(argv).lower()
    if head.lstrip().startswith("diff --git") or re.search(r"\bgit (diff|show)\b", cmd):
        return "diff"
    if re.search(r"pytest|unittest|\btest\b|jest|vitest|cargo test|go test|npm (run )?test", cmd) \
            or "Traceback (most recent call last)" in text or re.search(r"^Ran \d+ tests?", text, re.M):
        return "test"
    return "log"


def _dedupe(lines: list[str]) -> list[str]:
    out, last, n = [], None, 0
    for ln in lines + [None]:
        if ln == last:
            n += 1
            continue
        if last is not None:
            out.append(last + (f"   [×{n}]" if n > 1 else ""))
        last, n = ln, 1
    return out


def _test(lines: list[str]) -> list[str]:
    """Each failure's header, its last frame and the error line; the summary lines."""
    keep: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^(FAIL|ERROR|FAILED)[: ]", ln) or re.match(r"^_{3,} .* _{3,}$", ln):
            keep.append(ln)
        elif ln.startswith("Traceback (most recent call last)"):
            j = i + 1
            frame = None
            while j < len(lines) and (lines[j].startswith(" ") or not lines[j].strip()):
                if lines[j].lstrip().startswith("File "):
                    frame = [lines[j], lines[j + 1] if j + 1 < len(lines) else ""]
                j += 1
            if frame:
                keep += [x for x in frame if x.strip()]
            if j < len(lines):
                keep.append(lines[j])          # the exception line
            i = j
        elif re.match(r"^E\s{2,}", ln) or re.match(r"^\S+\.py:\d+: \w*(Error|Exception)", ln):
            keep.append(ln)                    # pytest's E lines and file:line: Error
        elif TEST_SUMMARY.match(ln.strip()):
            keep.append(ln)
        i += 1
    return keep or lines[-TAIL:]


def _diff(lines: list[str], budget: int) -> list[str]:
    files: list[list] = []
    for ln in lines:
        if ln.startswith("diff --git"):
            files.append([ln.split(" b/", 1)[-1], 0, 0, []])
        elif files and ln.startswith("+") and not ln.startswith("+++"):
            files[-1][1] += 1
            files[-1][3].append(ln)
        elif files and ln.startswith("-") and not ln.startswith("---"):
            files[-1][2] += 1
            files[-1][3].append(ln)
        elif files and ln.startswith("@@"):
            files[-1][3].append(ln)
    out = [f"{len(files)} files changed, +{sum(f[1] for f in files)} −{sum(f[2] for f in files)}"]
    out += [f"  {f[0]}  +{f[1]} −{f[2]}" for f in files]
    used = sum(len(x) + 1 for x in out)
    for f in files:
        if used > budget:
            break
        out.append(f"--- {f[0]}")
        for ln in f[3]:
            used += len(ln) + 1
            if used > budget:
                out.append("   … (more in the full log)")
                break
            out.append(ln)
    return out


def _log(lines: list[str]) -> list[str]:
    hit = set()
    for i, ln in enumerate(lines):
        if ERR.search(ln):
            hit.update((i - 1, i, i + 1))
    keep = [lines[i] for i in sorted(hit) if 0 <= i < len(lines)]
    tail = lines[-TAIL:]
    return _dedupe(keep) + (["…", *tail] if tail and tail[-1] not in keep else [])


def cut(text: str, argv: list[str], kind: str = "auto", max_chars: int = MAX_CHARS) -> tuple[str, str]:
    kind = kind_of(text, argv) if kind == "auto" else kind
    lines = text.splitlines()
    kept = _test(lines) if kind == "test" else _diff(lines, max_chars) if kind == "diff" else _log(lines)
    kept = _dedupe(kept)
    out = "\n".join(kept)
    if len(out) > max_chars:
        half = max_chars // 2
        out = out[:half] + "\n   … (cut: more in the full log, or ask with --ask)\n" + out[-half:]
    return out, kind


def run(argv: list[str], cwd: Path, kind: str = "auto", max_chars: int = MAX_CHARS, shell: bool = False,
        timeout: int = 1800) -> dict:
    t0 = time.time()
    try:
        r = subprocess.run(" ".join(argv) if shell else argv, cwd=cwd, shell=shell, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        text, rc = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else ""), r.returncode
    except FileNotFoundError as e:
        text, rc = str(e), 127
    except subprocess.TimeoutExpired as e:
        text, rc = ((e.stdout or "") if isinstance(e.stdout, str) else "") + f"\n[timed out after {timeout}s]", 124
    d = cwd / ".ccx" / "sum"
    d.mkdir(parents=True, exist_ok=True)
    (d / ".gitignore").write_text("*\n", encoding="utf-8")       # raw output never gets committed
    log = d / (time.strftime("%Y%m%d-%H%M%S-") + f"{int(time.time() * 1000) % 1000:03d}.log")
    log.write_text(text, encoding="utf-8")
    for old in sorted(d.glob("*.log"))[:-20]:          # keep the last 20
        old.unlink(missing_ok=True)
    short, k = cut(text, argv, kind, max_chars)
    return {"exit": rc, "kind": k, "lines": len(text.splitlines()), "chars": len(text), "kept_chars": len(short),
            "log": str(log), "seconds": round(time.time() - t0, 1), "text": short}


def header(res: dict, argv: list[str]) -> str:
    return (f"[ccx sum] `{' '.join(argv)}` exit {res['exit']} · {res['lines']:,} lines ({res['chars']:,} chars) → "
            f"{res['kept_chars']:,} chars ({res['kind']}) · full output: {res['log']}")
