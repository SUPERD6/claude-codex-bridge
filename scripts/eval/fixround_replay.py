"""Fix-round replay: did review-driven fix rounds make recorded units right, or wrong? Offline, no model calls.

A ccx run whose independent review says `issues` gets a fix round (`review_of` in the next run's run.json) or the lead
resumes it itself. Whether that round helped is not in the results: only the unit's final state was scored. This
rebuilds the tree before and after each fix round from what the run folders recorded and runs the task's hidden test
on both:

  before  the run's start commit (undo.json `base`) + the diff in its review's prompt.md (review.changes(): tracked
          edits plus new files, each new file cut to 4000 characters there)
  after   the same from the fix round's own review prompt when it was reviewed, else the unit's final tree (which
          also holds anything the lead changed afterwards: `after_from` says which)

A new file that reached the 4000-character cut is completed from the unit's final tree when its recorded text is a
prefix of that file (`completed` counts them); otherwise, or when the prompt's diff was cut to max_diff_chars or does
not apply, the round is skipped and counted, never guessed.

  python scripts/eval/fixround_replay.py --workdirs %TEMP%/r5e %TEMP%/r5f %TEMP%/r5g %TEMP%/r5h --jobs 3
  python scripts/eval/fixround_replay.py ... --check-final    # also re-score each unit's final tree vs results.jsonl

Prints a table per review reason (why the review ran) and per kind of [must] item, with fail->pass, pass->fail and
unchanged counts; --json writes the per-round rows. Scores are cached by tree hash (--cache), so a re-run is cheap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NEW_FILE_CUT = 4000          # review.changes(): a new (untracked) file's text is cut to this many characters
DIFF_HEAD = "## The change (git diff against the tree before it started"
DIFF_END = "\n```\n\n## Checks"
LABEL = re.compile(r"^eval-r5:(?P<tag>[^:]+):(?P<round>\d+):(?P<task>[^:]+):(?P<arm>[^:]+)$")


# ---------------------------------------------------------------- reading the run folders

def extract_diff(prompt: str) -> tuple[str | None, bool]:
    """(diff text, was it cut to max_diff_chars) from a review's prompt.md; (None, False) if it has none."""
    i = prompt.find(DIFF_HEAD)
    if i < 0:
        return None, False
    head_end = prompt.find("\n", i)
    cut = "cut to" in prompt[i:head_end]
    start = prompt.find("```diff\n", head_end)
    end = prompt.rfind(DIFF_END)
    if start < 0 or end < start:
        return None, cut
    body = prompt[start + len("```diff\n"):end]
    return ("" if body == "(empty)" else body), cut


def split_new_files(diff: str) -> tuple[str, dict[str, str]]:
    """Split review.changes()'s text into the `git diff` part and its appended new files ({path: text}). A new file
    block is `--- /dev/null`, `+++ b/<path>` and `+` lines with no hunk header (git's own new files have one)."""
    lines = diff.split("\n")
    patch: list[str] = []
    new: dict[str, str] = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        after = lines[i + 2] if i + 2 < len(lines) else ""
        if ln == "--- /dev/null" and nxt.startswith("+++ b/") and not after.startswith("@@") \
                and not (patch and patch[-1].startswith(("new file mode", "index "))):
            path, body = nxt[len("+++ b/"):], []
            i += 2
            while i < len(lines) and lines[i].startswith("+") and not lines[i].startswith("+++ b/"):
                body.append(lines[i][1:])
                i += 1
            new[path] = "".join(b + "\n" for b in body)
            continue
        patch.append(ln)
        i += 1
    text = "\n".join(patch).strip("\n")
    return (text + "\n" if text else ""), new


def maybe_cut(text: str) -> bool:
    """A new file's recorded text may have been cut at NEW_FILE_CUT characters (line ends may have lost \\r)."""
    return len(text) >= NEW_FILE_CUT - 5


def load_runs(hub: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((hub / "ccx" / "runs").glob("*/run.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        j["_dir"] = str(f.parent)
        out[j.get("run_id") or f.parent.name] = j
    return out


def base_of(runs: dict, rid: str) -> str | None:
    """The start commit of a run's chain: the undo.json of the first run it resumed from."""
    for _ in range(10):
        r = runs.get(rid)
        if not r:
            return None
        u = Path(r["_dir"]) / "undo.json"
        if u.exists():
            try:
                return json.loads(u.read_text(encoding="utf-8")).get("base")
            except (OSError, ValueError):
                return None
        rid = r.get("resumed_from")
    return None


def review_prompt(runs: dict, rid: str) -> tuple[str | None, bool]:
    """The diff (and cut flag) of the review of run `rid`, from its review run's prompt.md."""
    rev = (runs.get(rid) or {}).get("review") or {}
    rr = runs.get(rev.get("run_id") or "") or next(
        (r for r in runs.values() if r.get("caller") == "ccx-review" and r.get("label") == f"review:{rid}"), None)
    if not rr:
        return None, False
    try:
        # prompt.md was written in text mode: on Windows every \n became \r\n, so undo exactly that one step
        # (a universal-newline read would also eat a \r that belongs to the diff's content)
        raw = (Path(rr["_dir"]) / "prompt.md").read_bytes().decode("utf-8", "replace")
        return extract_diff(raw.replace("\r\n", "\n") if "\r\n" in raw else raw)
    except OSError:
        return None, False


def reason_bucket(reason: str) -> str:
    r = (reason or "").strip()
    if r == "asked":
        return "asked (--review on)"
    if re.fullmatch(r"\d+ changed code lines", r):
        return ">= min_lines changed code lines"
    if r.startswith("the tests it runs don't touch") or r.startswith("the acceptance command"):
        return "check does not reach the change"
    if r.startswith("existing tests edited"):
        return "existing tests edited"
    if r.startswith("risk "):
        return r
    return r or "(none)"


_CRASH = re.compile(r"NameError|AttributeError|TypeError|KeyError|ImportError|IndexError|ValueError|"
                    r"UnboundLocal|not defined|undefined|not imported|crash|raises?\b|exception|traceback", re.I)


def issue_kind(issues: list[str]) -> str:
    """A rough class of the first [must] item: crash (an error on a path), requirement (quotes the task), other."""
    first = next((i for i in issues if i.lstrip().lower().startswith("[must]")), issues[0] if issues else "")
    if _CRASH.search(first):
        return "crash / error"
    if re.search(r"[\"“「].{6,}[\"”」]", first):
        return "task requirement (quoted)"
    return "other"


def fix_rounds_of(hub: Path) -> list[dict]:
    """Every reviewed run with verdict `issues` that a later run resumed (the fix round), with what is needed to
    rebuild the tree before and after it."""
    runs = load_runs(hub)
    out = []
    for rid, r in sorted(runs.items(), key=lambda kv: kv[1].get("ts") or 0):
        rev = r.get("review")
        if not isinstance(rev, dict) or rev.get("verdict") != "issues" or r.get("caller") == "ccx-review":
            continue
        fixes = sorted((x for x in runs.values() if x.get("resumed_from") == rid), key=lambda x: x.get("ts") or 0)
        m = LABEL.match(r.get("label") or "")
        row = {"hub": str(hub), "run": rid, "reason": rev.get("reason") or "", "issues": rev.get("issues") or [],
               "label": r.get("label"), **({k: m.group(k) for k in ("tag", "round", "task", "arm")} if m else {})}
        if not fixes:
            out.append({**row, "fix": None})
            continue
        f = fixes[0]
        pre, pre_cut = review_prompt(runs, rid)
        post, post_cut = review_prompt(runs, f["run_id"]) if isinstance(f.get("review"), dict) else (None, False)
        out.append({**row, "fix": f["run_id"], "by": "auto" if f.get("review_of") == rid else "lead",
                    "base": base_of(runs, rid), "pre": pre, "pre_cut": pre_cut, "post": post, "post_cut": post_cut,
                    "after_from": "fix review" if post is not None else "final tree"})
    return out


# ---------------------------------------------------------------- rebuilding a tree

def _git(cwd: Path, *args: str, inp: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, input=inp, capture_output=True, timeout=120)


def final_state(repo: Path, base: str) -> tuple[bytes, dict[str, bytes]]:
    """The unit repository's final tree as (binary patch against base, {new untracked file: bytes}), read only."""
    patch = _git(repo, "diff", "--binary", base, "--", ".", ":(exclude).ccx").stdout
    names = _git(repo, "ls-files", "--others", "--exclude-standard").stdout.decode("utf-8", "replace").splitlines()
    return patch, {n: (repo / n).read_bytes() for n in names if n and not n.startswith(".ccx/") and (repo / n).is_file()}


def build_tree(repo: Path, base: str, dest: Path, patch: bytes, new: dict[str, bytes]) -> str | None:
    """dest = a fresh clone of `repo` at `base` with `patch` applied and `new` files written. None, or why not."""
    r = subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(repo), str(dest)],
                       capture_output=True, timeout=120)
    if r.returncode:
        return "clone failed: " + r.stderr.decode("utf-8", "replace")[:200]
    r = _git(dest, "-c", "advice.detachedHead=false", "checkout", "-q", base)
    if r.returncode:
        return "checkout failed: " + r.stderr.decode("utf-8", "replace")[:200]
    if patch.strip():
        r = _git(dest, "apply", "--whitespace=nowarn", "--recount", "-", inp=patch)
        if r.returncode:
            r2 = _git(dest, "apply", "--whitespace=nowarn", "--recount", "--ignore-whitespace", "-", inp=patch)
            if r2.returncode:
                return "patch does not apply: " + r.stderr.decode("utf-8", "replace")[:200]
    for n, body in new.items():
        p = dest / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return None


def state_from_prompt(diff: str, final_new: dict[str, bytes]) -> tuple[bytes, dict[str, bytes], int, str | None]:
    """(patch, new files, completed, why it cannot be rebuilt) for a review prompt's diff."""
    patch, new = split_new_files(diff)
    out, completed = {}, 0
    for n, text in new.items():
        if maybe_cut(text):
            full = final_new.get(n)
            if full is None:
                return b"", {}, 0, f"new file {n} cut at {NEW_FILE_CUT} characters and gone from the final tree"
            got = full.decode("utf-8", "replace").replace("\r\n", "\n")
            if not got.startswith(text.rstrip("\n")):
                return b"", {}, 0, f"new file {n} cut at {NEW_FILE_CUT} characters and changed later"
            out[n] = full
            completed += 1
        else:
            out[n] = text.encode("utf-8")
    return patch.encode("utf-8"), out, completed, None


def tree_key(task: str, base: str, patch: bytes, new: dict[str, bytes]) -> str:
    h = hashlib.sha256(f"{task}\0{base}\0".encode() + patch)
    for n in sorted(new):
        h.update(b"\0" + n.encode() + b"\0" + hashlib.sha256(new[n]).digest())
    return h.hexdigest()[:20]


# ---------------------------------------------------------------- scoring and the table

def default_scorer(repo: Path, task_id: str, work: Path) -> dict:
    import r5
    return r5.score(repo, r5.by_id(task_id), work)


def classify(pre: bool | None, post: bool | None) -> str:
    if pre is None or post is None:
        return "skipped"
    return {(False, True): "fail->pass", (True, False): "pass->fail",
            (True, True): "pass->pass", (False, False): "fail->fail"}[(pre, post)]


COLS = ("n", "fail->pass", "pass->fail", "pass->pass", "fail->fail", "skipped")


def table(rows: list[dict], key: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r.get("fix") is None:
            continue
        c = out.setdefault(r[key], dict.fromkeys(COLS, 0))
        c["n"] += 1
        c[r["outcome"]] += 1
    tot = dict.fromkeys(COLS, 0)
    for c in out.values():
        for k in COLS:
            tot[k] += c[k]
    out["(all)"] = tot
    return out


def render(t: dict[str, dict[str, int]], title: str) -> str:
    w = max(len(title), *(len(k) for k in t))
    lines = [f"{title:<{w}} | " + " | ".join(f"{c:>10}" for c in COLS), "-" * (w + 13 * len(COLS))]
    lines += [f"{k:<{w}} | " + " | ".join(f"{v[c]:>10}" for c in COLS) for k, v in t.items()]
    return "\n".join(lines)


def replay(workdirs: list[Path], arms: tuple[str, ...] = ("ccx2",), jobs: int = 2, scorer=default_scorer,
           cache: dict | None = None, scratch: Path | None = None, check_final: bool = False) -> dict:
    """All fix rounds under `workdirs` (r5 work dirs: <key>/ repos and h-<key>/ hubs), scored before and after."""
    cache = {} if cache is None else cache
    own = scratch is None
    scratch = Path(tempfile.mkdtemp(prefix="fixreplay-")) if own else scratch
    scratch.mkdir(parents=True, exist_ok=True)
    rows, finals, todo = [], [], {}

    def want(task: str, repo: Path, base: str, patch: bytes, new: dict[str, bytes]) -> str:
        k = tree_key(task, base, patch, new)
        if k not in cache:
            todo[k] = (task, repo, base, patch, new)
        return k

    for wd in workdirs:
        for hub in sorted(wd.glob("h-*")):
            key = hub.name[2:]
            if not any(key.endswith("-" + a) for a in arms):
                continue
            repo = wd / key
            if not (repo / ".git").exists():
                continue
            for fr in fix_rounds_of(hub):
                fr["workdir"], fr["unit"] = wd.name, key
                fr["reason_bucket"], fr["issue_kind"] = reason_bucket(fr["reason"]), issue_kind(fr["issues"])
                fr["completed"] = 0
                if fr.get("fix") is None:
                    rows.append(fr)
                    continue
                base, task = fr.get("base"), fr.get("task") or key.split("-", 1)[1].rsplit("-", 1)[0]
                fr["task"] = task
                why = None if base else "no start commit (undo.json) found"
                fpatch, fnew = final_state(repo, base) if base else (b"", {})
                if not why and (fr["pre"] is None or fr["pre_cut"]):
                    why = "the review prompt has no diff" if fr["pre"] is None else "review diff cut to max_diff_chars"
                if not why and fr["post"] is not None and fr["post_cut"]:
                    why = "fix review diff cut to max_diff_chars"
                if not why:
                    p1, n1, c1, why = state_from_prompt(fr["pre"], fnew)
                    if not why:
                        fr["pre_key"] = want(task, repo, base, p1, n1)
                        if fr["post"] is not None:
                            p2, n2, c2, why = state_from_prompt(fr["post"], fnew)
                            if not why:
                                fr["post_key"] = want(task, repo, base, p2, n2)
                        else:
                            c2 = 0
                            fr["post_key"] = want(task, repo, base, fpatch, fnew)
                        fr["completed"] = c1 + (c2 if not why else 0)
                fr["skip"] = why
                rows.append(fr)
            if check_final:
                runs = load_runs(hub)
                first = next((r for r in sorted(runs.values(), key=lambda x: x.get("ts") or 0)
                              if LABEL.match(r.get("label") or "")), None)
                base = base_of(runs, first["run_id"]) if first else None
                if base:
                    lm = LABEL.match(first["label"])
                    if lm:
                        fpatch, fnew = final_state(repo, base)
                        finals.append({"unit": key, "workdir": wd.name, **lm.groupdict(),
                                       "key": want(lm.group("task"), repo, base, fpatch, fnew)})

    def score_one(item):
        k, (task, repo, base, patch, new) = item
        d = scratch / k
        shutil.rmtree(d, ignore_errors=True)
        try:
            why = build_tree(repo, base, d / "repo", patch, new)
            if why:
                return k, {"ok": None, "error": why}
            sc = scorer(d / "repo", task, d)
            return k, {"ok": bool(sc.get("ok")), "pytest": sc.get("pytest")}
        except Exception as e:  # noqa: BLE001 — recorded, the round is then skipped
            return k, {"ok": None, "error": f"{type(e).__name__}: {e}"[:300]}
        finally:
            shutil.rmtree(d, ignore_errors=True)

    try:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            for k, v in ex.map(score_one, list(todo.items())):
                cache[k] = v
    finally:
        if own:
            shutil.rmtree(scratch, ignore_errors=True)

    for fr in rows:
        if fr.get("fix") is None:
            continue
        pre = cache.get(fr.get("pre_key") or "", {})
        post = cache.get(fr.get("post_key") or "", {})
        fr["pre_ok"], fr["post_ok"] = pre.get("ok"), post.get("ok")
        if not fr.get("skip") and (pre.get("ok") is None or post.get("ok") is None):
            fr["skip"] = pre.get("error") or post.get("error") or "not scored"
        fr["outcome"] = classify(fr["pre_ok"], fr["post_ok"]) if not fr.get("skip") else "skipped"
        for k in ("pre", "post"):
            fr.pop(k, None)
    for f in finals:
        f["replayed_ok"] = cache.get(f["key"], {}).get("ok")
    return {"rows": rows, "finals": finals, "cache": cache}


def final_agreement(finals: list[dict], results: list[dict]) -> dict:
    """The second method: the final tree re-scored here against the recorded hidden-test result in results.jsonl."""
    rec = {(r.get("tag"), str(r.get("round")), r.get("task"), r.get("arm")): r.get("ok") for r in results}
    same = diff = missing = 0
    off = []
    for f in finals:
        k = (f["tag"], str(f["round"]), f["task"], f["arm"])
        if k not in rec or f.get("replayed_ok") is None:
            missing += 1
        elif bool(rec[k]) == bool(f["replayed_ok"]):
            same += 1
        else:
            diff += 1
            off.append({"unit": f"{f['workdir']}/{f['unit']}", "recorded": bool(rec[k]), "replayed": f["replayed_ok"]})
    return {"same": same, "different": diff, "missing": missing, "different_units": off}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdirs", nargs="+", required=True, help="r5 work dirs (e.g. %%TEMP%%/r5e)")
    ap.add_argument("--arms", default="ccx2")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--cache", default="", help="a JSON file of scores by tree hash, read and updated")
    ap.add_argument("--json", default="", help="write the per-round rows here")
    ap.add_argument("--check-final", action="store_true",
                    help="also re-score every unit's final tree and compare with results.jsonl")
    ap.add_argument("--results", default="", help="results.jsonl for --check-final (default: .ccx/eval/r5/)")
    a = ap.parse_args(argv)
    cpath = Path(a.cache) if a.cache else None
    cache = json.loads(cpath.read_text(encoding="utf-8")) if cpath and cpath.exists() else {}
    out = replay([Path(w) for w in a.workdirs], tuple(x for x in a.arms.split(",") if x), a.jobs, cache=cache,
                 check_final=a.check_final)
    if cpath:
        cpath.write_text(json.dumps(out["cache"], indent=1), encoding="utf-8")
    rows = out["rows"]
    print(render(table(rows, "reason_bucket"), "review reason"))
    print()
    print(render(table(rows, "issue_kind"), "first [must] kind"))
    print()
    print(render(table(rows, "by"), "fix round by"))
    print()
    print(render(table(rows, "after_from"), "after = "))
    no_fix = sum(r.get("fix") is None for r in rows)
    skipped = [r for r in rows if r.get("outcome") == "skipped"]
    print(f"\nreviews with issues and no later run: {no_fix}; new files completed from the final tree: "
          f"{sum(r.get('completed', 0) for r in rows)}; skipped: {len(skipped)}")
    for r in skipped:
        print(f"  skipped {r['workdir']}/{r['unit']} {r['run']}: {r.get('skip')}")
    if a.check_final:
        import r5
        res = [json.loads(x) for x in Path(a.results or r5.results_file("r5")).read_text(encoding="utf-8").splitlines()
               if x.strip()]
        print("\nfinal tree re-scored vs results.jsonl:", json.dumps(final_agreement(out["finals"], res)))
    if a.json:
        Path(a.json).write_text(json.dumps({"rows": rows, "finals": out["finals"]}, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
