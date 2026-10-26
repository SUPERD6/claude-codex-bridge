"""Independent review (proposal F1): after a write run, a cheap model from another vendor reads the diff against
the task and answers pass / issues, so the lead reads a verdict and the problem spots instead of the whole change.

Only when it is worth it (`auto`, the default): the task was marked visible or critical, the change has 50+ changed
code lines, the sub-agent listed things it is unsure of (open_questions), or its claimed files don't match the
actual diff, or the evidence is weak (H13, judged from the run itself: no acceptance command, a command that runs
no tests, tests that never name a changed file or public function, or a command that let wrong work through before;
at most `weak_daily` of these a day, on the other vendors' cheapest rung). `on` reviews every write run
with changes, `off` never. The same model reviewing its own work misses its own mistakes, so the reviewer is always
another vendor ([review] by in tiers.toml). Issues go back to the same sub-session for one fix round, which is
reviewed again; still failing -> kind review_failed, for the lead to decide."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Paths
    from .delegate import Request

MARK = "[ccx review"
BRIEF = """{mark} of run {run_id}] Review a change another agent made. Do not edit anything.

## The task it was given
{task}

## What it says it did
{summary}

## The change (git diff against the tree before it started{cut})
```diff
{diff}
```
{context}
## Checks
{check}{edited}

## Answer
You cannot run commands; judge from the diff and the files. Do not report that tests were not run.
First go through the task above requirement by requirement (each return value, case, rule and error it names) and
check the code meets it; the acceptance tests may cover only some of them.
`[must] file:line — "task words" — what is wrong` is only for: (a) a requirement stated in the task that the change
does not meet or gets wrong, quoting the task sentence it rests on; (b) a bug that breaks existing behaviour or
existing tests, or crashes on inputs the task itself names (say which); (c) a way the task's stated behaviour
fails on its normal path, even silently: a name used but not defined or imported in that scope, an exception
swallowed on the new path (`except Exception: pass`, output sent to devnull), a subprocess or import that only works
from the repo directory; trace the entry point the task names (command, function) down to the new code; (d) a real
safety problem the change adds (code execution, secrets, data loss). A [must] without such a basis is treated as a note. Everything else is
`[note] ...`, at most 3: hardening, extra validation, edge cases or robustness the task did not ask for, style,
missing extra tests. Start summary with exactly `REVIEW: pass` (no [must]) or `REVIEW: issues` (at least one
[must]); put the items in open_questions, [must] first. Status done."""

# a [must] that labels itself as outside the task right after the tag ("[must] (out of scope) ...", "[must] Hardening:
# ...") is a note: round 5 found fix rounds spent on robustness the task never asked for, none of them making a unit right
_OUT_OF_SCOPE = re.compile(r"^\s*\[must\][\s:—–-]*[(\[]?\s*(out[- ]of[- ]scope|beyond the task|not (asked|required|"
                           r"in the task|part of the task)|outside the task|hardening|robustness|nice[- ]to[- ]have)\b",
                           re.I)


def _git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def changes(cwd: Path, snap: dict | None) -> tuple[list[str], str]:
    """(changed paths, diff text) since the undo snapshot: tracked edits plus files that are new since then."""
    if not snap:
        return [], ""
    base = snap["base"]
    # paths as git has them from the repo root (like the snapshot's untracked list), unquoted: with core.quotepath
    # on (git's default) a non-ASCII name came back as "sub/ä..." and matched no file
    q = ("-c", "core.quotepath=off")
    names = [n for n in _git(cwd, *q, "diff", "--name-only", base).splitlines() if n and not n.startswith(".ccx/")]
    diff = _git(cwd, *q, "diff", base, "--", ".", ":(exclude).ccx")
    before = set(snap.get("untracked") or [])
    for n in _git(cwd, *q, "ls-files", "--others", "--exclude-standard", "--full-name").splitlines():
        if n and n not in before and not n.startswith(".ccx/"):
            names.append(n)
            try:
                body = (Path(snap["repo"]) / n).read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                body = ""
            diff += f"\n--- /dev/null\n+++ b/{n}\n" + "".join(f"+{ln}\n" for ln in body.splitlines())
    return names, diff


def _norm(f: str) -> str:
    return f.replace("\\", "/").lstrip("./").lower()


DOC_SUFFIXES = (".md", ".txt", ".rst", ".adoc")


def code_lines(diff: str) -> int:
    """Changed lines (added + removed) in code files, docs not counted."""
    n, doc = 0, False
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            doc = ln.rstrip().lower().endswith(DOC_SUFFIXES)
        elif ln.startswith(("+", "-")) and not ln.startswith(("---", "+++")) and not doc:
            n += 1
    return n


def reason(mode: str, risk: str | None, result: dict, claimed: list[str], actual: list[str],
           lines: int = 0, min_lines: int = 50) -> str | None:
    """Why to review this run, or None. Called only for write runs that changed something and passed their check."""
    if mode == "off" or not actual:
        return None
    if mode == "on":
        return "asked"
    if risk in ("visible", "critical"):
        return f"risk {risk}"
    if min_lines and lines >= min_lines:
        # big enough that reading the verdict instead of the diff pays for the review (F1 trial: ~50 lines), and
        # the trial's one real bug sat in a change none of the other triggers would have reviewed
        return f"{lines} changed code lines"
    if result.get("open_questions"):
        return "the sub-agent is unsure"
    a = {_norm(f) for f in actual}
    c = {_norm(f) for f in claimed}
    if c and not any(x.endswith(y) or y.endswith(x) for x in a for y in c):
        return "its claimed files don't match the diff"
    if not c:
        return "it reported no files but the tree changed"
    return None


# an acceptance command that runs tests (not only a linter, an import or `exit 0`)
_TEST_CMD = re.compile(
    r"\b(py\.?test|unittest|nose2?|tox|nox|jest|vitest|mocha|jasmine|karma|playwright|cypress|rspec|phpunit|ctest"
    r"|bats|go\s+test|cargo\s+(test|nextest)|dotnet\s+test|deno\s+test|swift\s+test|mix\s+test"
    r"|(npm|pnpm|yarn|bun)\s+(run\s+)?test|make\s+(test|check)|(mvn|gradlew?)\b.*\btest"
    r"|test_\w+\.py|\w+_test\.\w+)\b", re.I)
CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php",
                 ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".scala")
_DEF = re.compile(r"^(\s*)(?:export\s+)?(?:pub(?:\(\w+\))?\s+)?(?:async\s+)?"
                  r"(?:def|class|function|func|fn)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def is_test_file(f: str) -> bool:
    f = _norm(f)
    name = f.rsplit("/", 1)[-1]
    return (bool(re.search(r"(^|/)(tests?|__tests__|spec)/", f)) or name.startswith("test_")
            or bool(re.search(r"(_test|\.test|\.spec|test)\.\w+$", name)))


def _per_file(diff: str) -> dict[str, list[int]]:
    """{path: new-side line numbers added or changed} from a unified diff."""
    out: dict[str, list[int]] = {}
    cur, n = None, 0
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            cur = ln[4:].strip()
            cur = None if cur == "/dev/null" else cur[2:] if cur.startswith("b/") else cur
            n = 0
            if cur:
                out.setdefault(cur, [])
        elif (m := _HUNK.match(ln)):
            n = int(m.group(1))
        elif cur and ln.startswith("+"):
            out[cur].append(n)
            n += 1
        elif cur and ln.startswith("-") and not ln.startswith("---"):
            out[cur].append(n)            # a removed line: the code around it changed
        elif cur and not ln.startswith("\\"):
            n += 1
    return out


def edited_tests(diff: str) -> list[str]:
    """Test files that existed before the run and lost or changed lines (a diff line starting with `-`), deleted
    ones included; new test files and pure additions to old ones are fine. Round 5: a builder rewrote an existing
    regression test's assertion to fit its misreading of the task, and the passing check then proved nothing."""
    out: list[str] = []
    old = None
    for ln in diff.splitlines():
        if ln.startswith("--- "):
            old = ln[4:].strip()
            old = None if old == "/dev/null" else old[2:] if old.startswith("a/") else old
        elif ln.startswith("+++ "):
            continue
        elif old and ln.startswith("-") and is_test_file(old) and old not in out:
            out.append(old)
    return out


def changed_symbols(text: str, lines: list[int]) -> list[str]:
    """Public functions / classes that contain (or are) the changed lines: the nearest less-indented def above."""
    src = text.splitlines()
    out: list[str] = []
    for no in sorted(set(lines)):
        i = min(no, len(src)) - 1
        while i >= 0 and not src[i].strip():
            i -= 1
        if i < 0:
            continue
        ind = len(src[i]) - len(src[i].lstrip()) + 1      # the changed line itself may be the def
        for s in reversed(src[:i + 1]):
            if not s.strip():
                continue
            d = len(s) - len(s.lstrip())
            if d >= ind:
                continue
            m = _DEF.match(s)
            if m:
                if not m.group(2).startswith("_") and m.group(2) not in out:
                    out.append(m.group(2))
                break
            ind = d
            if d == 0:                                    # reached module level outside any def
                break
    return out


def _test_texts(cwd: Path, cmd: str) -> list[str]:
    """The tests the acceptance command runs: the test paths it names, else every test file in the tree."""
    return [text for _f, text in _test_files(cwd, cmd)]


def _test_files(cwd: Path, cmd: str) -> list[tuple[str, str]]:
    """(path, text) of the tests the acceptance command runs (see _test_texts)."""
    files = [f for f in (_git(cwd, "ls-files").splitlines() + _git(cwd, "ls-files", "--others", "--exclude-standard")
                         .splitlines()) if f and not f.startswith(".ccx/")]
    named = [t.strip("'\"") for t in re.split(r"\s+", cmd) if t.strip("'\"") and (cwd / t.strip("'\"")).exists()
             and t.strip("'\"") not in (".", "./")]
    if named:
        keep = {_norm(t).rstrip("/") for t in named}
        files = [f for f in files if any(_norm(f) == k or _norm(f).startswith(k + "/") for k in keep)]
    texts = []
    for f in files:
        if is_test_file(f) and f.lower().endswith(CODE_SUFFIXES):
            try:
                texts.append((f, (cwd / f).read_text(encoding="utf-8", errors="replace")[:200_000]))
            except OSError:
                pass
        if len(texts) >= 300:
            break
    return texts


def check_gap(cmd: str, cwd: Path, actual: list[str], diff: str) -> str | None:
    """Why a passed acceptance command is weak evidence for this change, with no history needed: it runs no tests,
    or the tests it runs never name a changed code file or a changed public function (seven-cores r2: inventory's
    visible test imported the module but never called low_stock or remove_stock, the two places it was wrong)."""
    if not _TEST_CMD.search(cmd or ""):
        return f"the acceptance command `{cmd[:60]}` runs no tests"
    code = [f for f in actual if _norm(f).endswith(CODE_SUFFIXES) and not is_test_file(f)]
    if not code:
        return None
    texts = _test_texts(cwd, cmd)
    if not texts:
        return "the acceptance command found no test files"
    blob = "\n".join(texts)
    said = lambda w: re.search(rf"\b{re.escape(w)}\b", blob) is not None  # noqa: E731
    per, gaps = _per_file(diff), []
    for f in code:
        stem = Path(f).stem if Path(f).stem != "__init__" else Path(f).parent.name
        if stem and not said(stem):
            gaps.append(f"{f} (never named)")
            continue
        try:
            text = (cwd / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = next((v for k, v in per.items() if _norm(k) == _norm(f)), [])
        miss = [s for s in changed_symbols(text, lines) if not said(s)]
        if miss:
            gaps.append(f"{f}: {', '.join(miss[:4])}")
    if gaps:
        return "the tests it runs don't touch " + "; ".join(gaps[:3])
    return None


# Code around the change (r5 design, PR A; opt-in, [review] context = true): the Haiku reviewer makes 6-18
# sequential tool turns to read what the diff leaves out. With the changed functions, the definitions they call
# and the tests naming them in the brief, a replay of 10 recorded round-5 reviews, ~43 runs per variant
# (scripts/eval/review_replay.py, claude haiku low, 2026-10-26), took about half the time and output tokens
# (median 15 s vs 23 s with the read-only Finish text alone, 30 s with the old prompt) but found fewer of the
# known real bugs (11 of 28 tries, vs 19 and 16: the reviewer stopped reading after ~2 tool uses), so it is off.
CONTEXT_HEAD = ("\n## Code around the change\nAs the files are now: the changed functions in full, the definitions "
                "of names they call (in the same file, or imported from this repository), and tests that name "
                "them{cut}. It is where to start, not the whole review: still trace the entry point the task names "
                "and check each requirement. Whatever else the change relies on (the keys a dict really has, what a "
                "caller passes, where a value comes from), open it; open all you need at once (several reads in one "
                "turn), not one file per turn.\n")
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_BIG_SPAN, _CALLEE_LINES, _TEST_LINES, _MAX_TESTS = 150, 80, 60, 6


def _imports(cwd: Path, f: str, text: str) -> dict[str, str]:
    """{name: repo file it is imported from} for a Python file's `from x import name` lines (local imports inside
    functions included) whose module is a file in this tree."""
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return {}
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        base = Path(f).parent
        for _ in range(max(0, node.level - 1)):
            base = base.parent
        parts = node.module.split(".") if node.module else []
        mod = (base if node.level else Path()).joinpath(*parts)
        cands = [c for c in ((mod.with_suffix(".py") if parts else None), mod / "__init__.py")
                 if c is not None and (cwd / c).is_file()]
        for a in node.names:
            sub = mod / (a.name + ".py")          # `from pkg import store`: the name is the submodule pkg/store.py
            if (cwd / sub).is_file():
                out.setdefault(a.asname or a.name, sub.as_posix())
            elif cands:
                out.setdefault(a.asname or a.name, cands[0].as_posix())
    return out


def _spans(src: list[str]) -> list[tuple[str, int, int]]:
    """(name, first, last line index) of each def / class / function in a file, its end found by indentation."""
    out = []
    for i, s in enumerate(src):
        m = _DEF.match(s)
        if not m:
            continue
        d, end = len(m.group(1)), i
        for j in range(i + 1, len(src)):
            t = src[j].lstrip()
            if not t:
                continue
            if len(src[j]) - len(t) <= d:
                if t[:1] in ")]":                 # the close of a multi-line signature
                    end = j
                    continue
                if t[:1] == "}":                  # a brace language's closing line belongs to the block
                    end = j
                break
            end = j
        out.append((m.group(2), i, end))
    return out


def _innermost(spans: list[tuple[str, int, int]], i: int) -> tuple[str, int, int] | None:
    best = None
    for sp in spans:
        if sp[1] <= i <= sp[2] and (best is None or sp[1] >= best[1]):
            best = sp
    return best


def code_context(cwd: Path | None, diff: str, budget: int, check_cmd: str = "") -> str:
    """The '## Code around the change' block for a review brief, at most `budget` characters ('' when nothing fits):
    each changed function in full (a window around the change when it is longer than 150 lines; skipped when the
    diff already shows all of it as new), then the same-file definitions of the names those functions call, then
    those imported from another file of the tree (Python `from x import name`), then test functions (of the tests the acceptance command runs) that name a changed function."""
    if cwd is None or budget < 300:
        return ""
    per, new_files, old = _per_file(diff), set(), None
    for ln in diff.splitlines():
        if ln.startswith("--- "):
            old = ln[4:].strip()
        elif ln.startswith("+++ ") and old == "/dev/null":
            new_files.add(ln[4:].strip()[2:] if ln[4:].strip().startswith("b/") else ln[4:].strip())
    items: list[tuple[int, str, str, int, int, list[str]]] = []        # (priority, file, name, first, last, src)
    names: list[str] = []
    for f, lines in per.items():
        if not lines or f in new_files or is_test_file(f) or not f.lower().endswith(CODE_SUFFIXES):
            continue
        try:
            src = (cwd / f).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        spans, touched = _spans(src), set(n - 1 for n in lines)
        changed: list[tuple[str, int, int]] = []
        for i in sorted(touched):
            sp = _innermost(spans, min(i, len(src) - 1))
            if sp and sp not in changed:
                changed.append(sp)
        for name, a, b in changed:
            names.append(name)
            if all(k in touched for k in range(a, b + 1)):
                continue                                  # wholly new: the diff shows it already
            near = [k for k in touched if a <= k <= b]
            if b - a > _BIG_SPAN and near:
                a, b = max(a, min(near) - 15), min(b, max(near) + 15)
            items.append((0, f, name, a, b, src))
        called: list[str] = []
        for _n, a, b in changed:
            for c in _CALL.findall("\n".join(src[a:b + 1])):
                if c not in called:
                    called.append(c)
        imported = _imports(cwd, f, "\n".join(src)) if f.lower().endswith(".py") else {}
        for c in called:
            sp = next((s for s in spans if s[0] == c), None)
            if sp and not any(x[1] <= sp[1] <= x[2] for x in changed):
                items.append((1, f, c, sp[1], min(sp[2], sp[1] + _CALLEE_LINES), src))
            elif not sp and c in imported:
                try:
                    osrc = (cwd / imported[c]).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                sp = next((s for s in _spans(osrc) if s[0] == c), None)
                if sp:
                    items.append((2, imported[c], c, sp[1], min(sp[2], sp[1] + _CALLEE_LINES), osrc))
    if names:
        pat = re.compile(r"\b(" + "|".join(sorted({re.escape(n) for n in names})) + r")\b")
        found = 0
        for tf, text in _test_files(cwd, check_cmd):
            if found >= _MAX_TESTS or tf in new_files or not pat.search(text):
                continue
            tsrc = text.splitlines()
            for name, a, b in _spans(tsrc):
                if found < _MAX_TESTS and name.startswith("test") and pat.search("\n".join(tsrc[a:b + 1])):
                    items.append((3, tf, name, a, min(b, a + _TEST_LINES), tsrc))
                    found += 1
    head = CONTEXT_HEAD.format(cut="")
    out, used, left_out = [], len(head) + 60, False
    shown: set[tuple[str, int]] = set()
    for _p, f, name, a, b, src in sorted(items, key=lambda x: x[0]):
        if (f, a) in shown:                               # called from two changed functions, or two files
            continue
        shown.add((f, a))
        block = f"### {f}:{a + 1}-{b + 1} ({name})\n```\n" + "\n".join(src[a:b + 1]) + "\n```\n"
        if used + len(block) > budget:
            left_out = True
            continue
        out.append(block)
        used += len(block)
    if not out:
        return ""
    return CONTEXT_HEAD.format(cut="; some left out to fit, open the files for the rest" if left_out else "") + \
        "".join(out)


def weak_reason(p: Paths, rc: dict, record: dict, now: float | None = None, cwd: Path | None = None,
                actual: list[str] | None = None, diff: str = "", edited: list[str] | None = None) -> str | None:
    """H13: in `auto`, also review a write run when the evidence that the work is right is weak, up to `weak_daily`
    a day (`weak = false` in [review] switches this off). Weak, judged from this run alone (no history needed):
    no acceptance command; or it runs no tests; or its tests never name a changed file / public function. Also weak:
    this command let wrong work through before (J7, needs history). A passed command whose tests reach the change is
    strong and not reviewed. Edited pre-existing tests (`edited`) make any check weak, and are reviewed even past the
    daily cap. Each such review is logged, which is how the cap is counted."""
    import time
    from . import ledger
    if not rc.get("weak", True):
        return None
    check = record.get("check") or {}
    if edited:
        why = "existing tests edited: " + ", ".join(edited[:3])
    elif check.get("weak"):
        why = "weak check: this acceptance command let wrong work through before"
    elif not check:
        res = record.get("result") or {}
        why = ("only the sub-agent's own check" if res.get("verification", "not-run") not in ("", "not-run")
               else "no acceptance command")
    else:
        why = check_gap(check.get("cmd", ""), cwd, actual or [], diff) if cwd is not None else None
    if not why:
        return None
    now = now or time.time()
    t = time.localtime(now)
    midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    today = sum(1 for r in ledger.rows(p) if r.get("type") == "weak_review" and (r.get("ts") or 0) >= midnight)
    if today >= int(rc.get("weak_daily", 20)) and not edited:
        return None
    ledger.append_event(p, {"type": "weak_review", "run_id": record.get("run_id"), "why": why, "ts": now})
    return why


REVIEW_B = 3.0           # a review reads one diff against one brief: routed like an easy read-only task


def reviewers(cfg: dict, worker: str, installed, p=None, cheapest: bool = False) -> list[tuple[str, str, str]]:
    """(agent, model, effort) candidates for reviewing `worker`'s work, best first: models of another vendor (I3),
    never a cash provider. Order: what the person pinned in [review] by; then, per installed agent of another
    vendor, the rung routing finds cheapest for an easy read (I4: from data, not a fixed table); then
    [review] also. The next one is tried when a review can't finish (haiku ran out of structured-output retries
    twice in the 2026-10-24 trial). `cheapest`: only the pinned and T1 rungs, no routing pick and no [review] also."""
    from .agents import NAMES, get, others, same_vendor
    rc = cfg.get("review") or {}
    by = rc.get("by") or {}
    rungs = [by.get(worker)] + [v for k, v in by.items() if k != worker]
    # cheapest rung of each other vendor first: routing picked sonnet medium for reviews in the seven-cores A/B,
    # 20–40x the luna-low work it reviewed, with no gain in pass rate (PR #30); sonnet stays as the fallback (also)
    for agent in filter(installed, others(worker, cfg, only_installed=False)):
        t1 = ((cfg.get("tiers") or {}).get("T1") or {}).get(agent)
        if isinstance(t1, dict) and t1.get("model"):
            rungs.append(f"{agent}:{t1['model']}:{t1.get('effort', 'low')}")
    if p is not None:
        from . import learn
        for agent in filter(installed, others(worker, cfg, only_installed=False)):
            try:
                rungs.append(learn.pick(p, REVIEW_B, [agent], "save", mode="read", kind="read")["rung"])
            except Exception:  # noqa: BLE001 — no routing data for it: the pinned ones still apply
                pass
    out, pinned = [], set(filter(None, by.values()))
    for rung in filter(None, rungs + ([] if cheapest else list(rc.get("also") or []))):
        agent, model, effort = rung.split(":", 2)
        cash = agent in NAMES and get(agent).pay_per_token and rung not in pinned   # real money: only if pinned
        if (agent in NAMES and not cash and not same_vendor(agent, worker, cfg) and installed(agent)
                and (agent, model, effort) not in out):
            out.append((agent, model, effort))
    return out


def brief(run_id: str, task: str, summary: str, diff: str, max_chars: int, check: dict | None = None,
          edited: list[str] | None = None, static: str = "", cwd: Path | None = None) -> str:
    """The reviewer's brief. `edited` (default: found in `diff`) names pre-existing test files the change edited;
    `static`: what ccx's own static checks found (namecheck), as weak evidence under Checks.
    `cwd` (the reviewed tree): add the code around the change, in what is left of `max_chars` after the diff."""
    edited = edited_tests(diff) if edited is None else edited
    ed = (f"\nExisting tests edited: {', '.join(edited[:8])} — check the task requires it; an existing assertion "
          f"changed to fit the new code without the task asking for it is a [must] (b)." if edited else "")
    cut = f"; cut to {max_chars} characters, open the files for the rest" if len(diff) > max_chars else ""
    ran = (f"ccx ran the acceptance command `{check['cmd']}` after the change: "
           f"{'passed' if check.get('passed') else 'FAILED (exit %s)' % check.get('exit')}." if check
           else "No acceptance command was given; nobody ran the tests for you.")
    shown = diff[:max_chars]
    context = ""
    if cwd:
        try:                                  # an opt-in extra: a file it cannot parse must not stop the review
            context = code_context(cwd, diff, max_chars - len(shown), (check or {}).get("cmd") or "")
        except (OSError, ValueError, RecursionError, re.error):
            context = ""
    return BRIEF.format(mark=MARK, run_id=run_id, task=task.strip()[:2000], summary=(summary or "")[:800],
                        diff=shown or "(empty)", cut=cut, check=ran, edited=ed + static, context=context)


_PREFIX = re.compile(r"^[\s*_`#>]*review\s*[:：]?\s*[*_`]*\s*(pass|issues)\b", re.I)


def verdict(result: dict | None) -> dict:
    r = result or {}
    s = (r.get("summary") or "").strip()
    m = _PREFIX.match(s)
    v = m.group(1).lower() if m else "unclear"
    items = [str(x)[:300] for x in (r.get("open_questions") or [])]
    items = ["[note]" + x.lstrip()[len("[must]"):] if _OUT_OF_SCOPE.match(x) else x for x in items]
    must =[x for x in items if x.lstrip().lower().startswith("[must]")]
    notes = [x for x in items if x not in must]
    lenient = False
    if v == "unclear" and items:
        # no `REVIEW: ...` line (e.g. the summary written in another language, round 2 of the seven-cores A/B:
        # haiku named the real bug as [must] and the run was left unfixed): the tagged items still say it
        if must:
            v, lenient = "issues", True
        elif all(x.lstrip().lower().startswith("[note]") for x in notes):
            v, lenient = "pass", True
    if v == "issues" and not must and notes and any(x.lstrip().lower().startswith("[note]") for x in notes):
        v = "pass"                    # only notes: nothing that makes the change wrong, so no fix round
    out = {"verdict": v, "issues": (must or ([] if v == "pass" else notes))[:8], "summary": s[:400]}
    if lenient:
        out["format"] = "lenient"
    if v == "pass" and notes:
        out["notes"] = notes[:3]
    return out


def review_run(req: Request, p: Paths, cfg: dict, record: dict, cwd: Path, run_dir: Path, cancel=None) -> None:
    """F1: maybe have another vendor's cheap model review this write run's diff; sets record["review"]. When the
    change edited pre-existing tests, record["edited_tests"] (and record["review"]["edited_tests"] when a review
    is recorded) lists them. `cancel` (a threading.Event, set when ccx's check failed meanwhile): start no reviewer."""
    from .delegate import Request, run
    from .runners import find_bin
    import sys
    rv = sys.modules[__name__]
    rc = cfg.get("review") or {}
    mode = req.review if req.review != "auto" else rc.get("mode", "auto")
    first = req.resume_run if (req.resume_run and not req.continued) else None
    undo = (p.runs / first / "undo.json") if first else (run_dir / "undo.json")
    snap = json.loads(undo.read_text(encoding="utf-8")) if undo.exists() else None
    actual, diff = rv.changes(cwd, snap)
    res = record.get("result") or {}
    edited = rv.edited_tests(diff)
    if edited:                                # shown to the lead even when no review runs (e.g. `weak = false`)
        record["edited_tests"] = edited
    why = rv.reason(mode, req.risk, res, res.get("files_changed") or [], actual, rv.code_lines(diff),
                    int(rc.get("min_lines", 50)))
    weak = False
    if not why and mode == "auto" and actual:
        why = rv.weak_reason(p, rc, record, cwd=cwd, actual=actual, diff=diff, edited=edited)
        weak = bool(why)
    if not why:
        return
    # a weak-evidence review is the routine one (most write runs): only the other vendors' cheapest rung
    cands = rv.reviewers(cfg, req.provider or req.to, find_bin, None if weak else p, cheapest=weak)
    if not cands:
        record["review"] = {"verdict": "not-run", "reason": why, "error": "no reviewer from another vendor installed"}
        if edited:
            record["review"]["edited_tests"] = edited
        return
    from . import namecheck as nck
    nc = record.get("namecheck")
    if nc is None and nck.mode(req, cfg) != "off":      # a review started before the run's own namecheck
        try:
            nc = nck.scan(cwd, snap, actual, diff)
        except Exception:  # noqa: BLE001 — weak evidence only; never stops the review
            nc = None
    text = rv.brief(record["run_id"], task_for_review(p, req), res.get("summary", ""), diff,
                    int(rc.get("max_diff_chars", 12000)), record.get("check"), edited, nck.brief_note(nc),
                    cwd=cwd if rc.get("context", False) else None)
    usd, tried = 0.0, []
    for agent, model, effort in cands[:2]:
        if cancel is not None and cancel.is_set():
            return
        rev = run(Request(to=agent, model=model, effort=effort, tier="auto", mode="read", cwd=cwd, brief=text,
                          caller="ccx-review", escalate=False, fallback=False, review="off", allow_subagents=False,
                          ephemeral=True, label=f"review:{record['run_id']}"), p)
        usd += sum(a.get("ae_usd") or 0 for a in rev.get("attempts", []))
        tried.append(f"{agent}:{model}:{effort}")
        v = rv.verdict(rev.get("result")) if rev.get("ok") else {"verdict": "not-run", "issues": [],
                                                                 "summary": (rev.get("error") or "")[:300]}
        if v["verdict"] != "not-run":
            break
    record["review"] = {**v, "reason": why, "by": tried[-1], "run_id": rev["run_id"], "usd": round(usd, 4)}
    if len(tried) > 1:
        record["review"]["tried"] = tried
    if edited:
        record["review"]["edited_tests"] = edited
    if v["verdict"] == "issues":
        record["kind"] = ("review_issues" if req.review_round < fix_rounds(rc) else "review_failed")


def fix_rounds(rc: dict) -> int:
    """Fix rounds after a review: 0 or 1. Round 5: more rounds cost time and did not make units more often right."""
    try:
        return max(0, min(1, int(rc.get("fix_rounds", 1))))
    except (TypeError, ValueError):
        return 1


def task_for_review(p: Paths, req: Request) -> str:
    """The task a review judges against. A fix round's own brief is the list of review issues; judging the fix
    against that list would make every issue a requirement, so its review gets the first run's task instead."""
    rid = req.resume_run if (req.review_round and not req.continued) else None
    for _ in range(5):                       # the reviewed run may itself be a resume: walk back to the run with a task
        if not rid:
            break
        try:
            first = (p.runs / rid / "brief.md").read_text(encoding="utf-8")
            if first.strip():
                return first
        except OSError:
            pass
        try:
            prev = json.loads((p.runs / rid / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            break
        rid = None if prev.get("continued") else prev.get("resumed_from")
    return req.brief
