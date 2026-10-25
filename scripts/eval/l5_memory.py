"""L5: a fixed, rerunnable memory test (docs/research/2026-10-25-r3-plan.md §5). One side writes a preference or a
pitfall into shared memory (`ccx mem add --by <writer>`), the other side gets a task that needs it in a NEW sub-agent
session (`ccx run --new`), and a hidden test says whether the note was used. With memory: three unrelated notes plus
the one that matters; without: only the three unrelated notes. Every unit has its own throwaway hub (CCX_HUB).

  directions   claude->codex  the note is written as Claude, Codex gpt-6-luna low does the task
               codex->claude  the note is written as Codex, Claude haiku low does the task

  python scripts/eval/l5_memory.py run --reps 2 --budget 8
  python scripts/eval/l5_memory.py summary
  python scripts/eval/l5_memory.py export docs/research/data/2026-10-25-l5-memory.json

Results go to .ccx/eval/l5/results.jsonl; `run` again skips finished units. The budget counts this file AND round 3's
results, so the two stay under one cap. Tests check the cases with no model calls (tests/test_eval_r3.py).
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2  # noqa: E402
import r3  # noqa: E402
import seven_ab as S  # noqa: E402
from common import ROOT, append_jsonl, archive_hub, make_repo, read_jsonl, score  # noqa: E402
from tasks import MEMORY  # noqa: E402

OUT = ROOT / ".ccx" / "eval" / "l5" / "results.jsonl"
R3_OUT = ROOT / ".ccx" / "eval" / "r3" / "results.jsonl"
DIRECTIONS = {"claude->codex": ("claude", ["--to", "codex", "--model", "gpt-6-luna", "--effort", "low"]),
              "codex->claude": ("codex", ["--to", "claude", "--model", "haiku", "--effort", "low"])}
ARMS = ("off", "on")
# unrelated notes that share common words with the briefs, as a real journal would
DISTRACTORS = [
    ("tooling", "The release script needs Node 22 or newer; run it from the repository root."),
    ("people", "The person prefers short commit messages in English and replies in Chinese."),
    ("pitfall", "On Windows, git object files are read-only: remove a repo folder with an onerror handler that "
                "clears the flag."),
]

CASES: list[dict] = [*[{**t, "kind": "convention"} for t in MEMORY], {
    "id": "mem-dates", "kind": "pitfall",
    "brief": "Implement parse_export_date(s) in dates.py: turn a date string from our CSV exports into a "
             "datetime.date.",
    "memory": "Pitfall: dates in this project's CSV exports are day/month/year (European, e.g. 03/04/2026 is "
              "3 April 2026), never month/day.",
    "files": {"dates.py": "def parse_export_date(s):\n    raise NotImplementedError\n"},
    "visible": "import datetime\nfrom dates import parse_export_date\n\n\ndef test_basic():\n"
               "    assert isinstance(parse_export_date('01/01/2026'), datetime.date)\n",
    "hidden": "import datetime\nfrom dates import parse_export_date\n\n\ndef test_hidden():\n"
              "    assert parse_export_date('03/04/2026') == datetime.date(2026, 4, 3)\n"
              "    assert parse_export_date('25/12/2025') == datetime.date(2025, 12, 25)\n",
    "solution": {"dates.py": "import datetime\n\n\ndef parse_export_date(s):\n"
                             "    return datetime.datetime.strptime(s.strip(), '%d/%m/%Y').date()\n"},
}, {
    "id": "mem-paths", "kind": "preference",
    "brief": "Implement backup_name(path) in files.py: the path of a file's backup copy, 'name.ext' -> "
             "'name.ext.bak' in the same folder.",
    "memory": "Preference: functions in this project that take a file path accept str or pathlib.Path and always "
              "return a pathlib.Path, never a str.",
    "files": {"files.py": "def backup_name(path):\n    raise NotImplementedError\n"},
    "visible": "from files import backup_name\n\n\ndef test_basic():\n"
               "    assert str(backup_name('a/b.txt')).replace('\\\\', '/') == 'a/b.txt.bak'\n",
    "hidden": "from pathlib import Path\nfrom files import backup_name\n\n\ndef test_hidden():\n"
              "    r = backup_name('d/x.csv')\n    assert isinstance(r, Path) and r == Path('d/x.csv.bak')\n"
              "    assert isinstance(backup_name(Path('y.txt')), Path)\n",
    "solution": {"files.py": "from pathlib import Path\n\n\ndef backup_name(path):\n"
                             "    p = Path(path)\n    return p.with_name(p.name + '.bak')\n"},
}, {
    "id": "mem-json", "kind": "preference",
    "brief": "Implement save_settings(settings, path) in settings_io.py: write the settings dict to path as JSON.",
    "memory": "Preference: every JSON file this project writes uses sort_keys=True and indent=2, UTF-8, and ends "
              "with one newline (so diffs stay small).",
    "files": {"settings_io.py": "def save_settings(settings, path):\n    raise NotImplementedError\n"},
    "visible": "import json\nfrom settings_io import save_settings\n\n\ndef test_basic(tmp_path):\n"
               "    f = tmp_path / 's.json'\n    save_settings({'a': 1}, f)\n"
               "    assert json.loads(f.read_text(encoding='utf-8')) == {'a': 1}\n",
    "hidden": "import json\nfrom settings_io import save_settings\n\n\ndef test_hidden(tmp_path):\n"
              "    f = tmp_path / 's.json'\n    save_settings({'b': [1, 2], 'a': 'x'}, f)\n"
              "    want = json.dumps({'a': 'x', 'b': [1, 2]}, sort_keys=True, indent=2) + '\\n'\n"
              "    assert f.read_text(encoding='utf-8') == want\n",
    "solution": {"settings_io.py": "import json\n\n\ndef save_settings(settings, path):\n"
                                   "    with open(path, 'w', encoding='utf-8') as f:\n"
                                   "        f.write(json.dumps(settings, sort_keys=True, indent=2) + '\\n')\n"},
}]


def by_id(case_id: str) -> dict:
    return next(c for c in CASES if c["id"] == case_id)


def schedule(reps: int, seed: int) -> list[dict]:
    out = []
    for rep in range(1, reps + 1):
        rnd = random.Random(f"{seed}:l5:{rep}")
        units = [{"exp": "l5", "round": rep, "task": c["id"], "dir": d, "arm": arm}
                 for c in CASES for d in DIRECTIONS for arm in ARMS]
        rnd.shuffle(units)
        out += units
    return out


def unit_key(u: dict) -> str:
    return f"{u['tag']}:{u['round']}:{u['task']}:{u['dir']}:{u['arm']}"


def mem_add(hub: Path, cwd: Path, by: str, topic: str, text: str) -> None:
    r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), "mem", "add", "--by", by, "--topic", topic, text],
                       cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=r2.env_for(hub))
    if r.returncode:
        raise RuntimeError(f"`ccx mem add` failed: {(r.stderr or r.stdout)[-300:]}")


def run_unit(u: dict, a, work: Path) -> dict:
    case = by_id(u["task"])
    key = f"{u['round']}-{u['task']}-{u['dir'].replace('->', '2')}-{u['arm']}"
    repo, hub = work / key, work / f"hub-{key}"
    for d in (repo, hub):
        r2._rmtree(d)
    make_repo(case, repo)
    info = r3.make_hub(hub)
    writer, pick = DIRECTIONS[u["dir"]]
    for topic, text in DISTRACTORS:
        mem_add(hub, repo, writer, topic, text)
    if u["arm"] == "on":
        mem_add(hub, repo, writer, case["kind"], case["memory"])
    argv = ["run", "--mode", "write", "--new", "--no-ab", "--force", "--label", u["label"], "--minutes", "5",
            "--check", "python -m pytest -q", "--review", "off", "--no-escalate", "--no-fallback", *pick,
            case["brief"]]
    res, rc, wall, err = r2.ccx(argv, repo, hub, a.timeout)
    sc = score(repo, case)
    cost = r2.hub_cost(hub)
    rid = res.get("run_id")
    pr = hub / "ccx" / "runs" / str(rid) / "prompt.md"
    prompt = pr.read_text(encoding="utf-8", errors="replace") if pr.exists() else ""
    row = {**u, "ok": sc["ok"], "pytest": sc["pytest"], "rc": rc, "wall_s": wall, "ccx_ok": res.get("ok"),
           "status": res.get("status"), "model": res.get("model"), "agent": res.get("agent"),
           "note_in_prompt": case["memory"] in prompt, "distractors_in_prompt": sum(t in prompt for _, t in DISTRACTORS),
           "usd": cost["usd"], "tokens": cost["tokens"], "hub": info, "stderr": err if rc else ""}
    if rid:
        r2.verify(hub, rid, bool(sc["ok"]), sc["pytest"])
    row["archived_sessions"] = archive_hub(hub)
    return row


def cmd_run(a) -> int:
    out = Path(a.out) if a.out else OUT
    work = Path(a.workdir or tempfile.mkdtemp(prefix="ccx-l5-"))
    done = {unit_key(r) for r in read_jsonl(out)}
    print(f"work dir: {work}  results: {out}", flush=True)
    for u in schedule(a.reps, a.seed):
        u = {**u, "tag": a.tag}
        u["label"] = f"eval-l5:{a.tag}:{u['round']}:{u['task']}:{u['dir']}:{u['arm']}"
        if unit_key(u) in done:
            continue
        total = round(r3.spent(read_jsonl(out)) + r3.spent(read_jsonl(R3_OUT)), 4)
        if total >= a.budget:
            print(f"budget ${a.budget} reached (${total:.3f}): stopping", flush=True)
            return 2
        if a.dry_run:
            print(f"[dry] {u['label']}")
            continue
        try:
            row = run_unit(u, a, work)
        except Exception as e:  # noqa: BLE001 — one broken unit is recorded, the batch goes on
            row = {**u, "ok": False, "error": f"{type(e).__name__}: {e}"[:400], "usd": 0.0}
        row["ts"] = time.time()
        append_jsonl(out, row)
        print(f"r{u['round']} {u['task']:11} {u['dir']:14} {u['arm']:3} ok={row.get('ok')} "
              f"note={row.get('note_in_prompt')} ${row.get('usd', 0):.4f} {row.get('wall_s')}s", flush=True)
    return 0


def summarize(rows: list[dict]) -> dict:
    rows = [r for r in rows if "error" not in r]
    res: dict = {"units": len(rows), "spend_usd": r3.spent(rows), "arms": {}, "by_dir": {}, "by_case": {}}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        k = sum(bool(r["ok"]) for r in rs)
        res["arms"][arm] = {"n": len(rs), "ok": k, "ok_wilson": S.wilson(k, len(rs)) if rs else None,
                            "note_in_prompt": sum(bool(r.get("note_in_prompt")) for r in rs), "usd": r3.spent(rs)}
    for d in DIRECTIONS:
        res["by_dir"][d] = {arm: f"{sum(bool(r['ok']) for r in rows if r['dir'] == d and r['arm'] == arm)}/"
                                 f"{sum(r['dir'] == d and r['arm'] == arm for r in rows)}" for arm in ARMS}
    for c in CASES:
        res["by_case"][c["id"]] = {arm: f"{sum(bool(r['ok']) for r in rows if r['task'] == c['id'] and r['arm'] == arm)}/"
                                        f"{sum(r['task'] == c['id'] and r['arm'] == arm for r in rows)}" for arm in ARMS}
    by: dict = {}
    for r in rows:
        by.setdefault((r["tag"], r["round"], r["task"], r["dir"]), {})[r["arm"]] = r
    ps = [(d["off"], d["on"]) for d in by.values() if "off" in d and "on" in d]
    b = sum(bool(x["ok"]) and not y["ok"] for x, y in ps)
    c = sum(bool(y["ok"]) and not x["ok"] for x, y in ps)
    res["paired"] = {"pairs": len(ps), "only_off": b, "only_on": c, "mcnemar_p": S.mcnemar_p(b, c)}
    return res


def cmd_summary(a) -> int:
    print(json.dumps(summarize(read_jsonl(Path(a.file) if a.file else OUT)), ensure_ascii=False, indent=1))
    return 0


def cmd_export(a) -> int:
    rows = read_jsonl(Path(a.file) if a.file else OUT)
    keep = ("tag", "round", "task", "dir", "arm", "ok", "pytest", "rc", "wall_s", "ccx_ok", "status", "model",
            "agent", "note_in_prompt", "distractors_in_prompt", "usd", "tokens", "error")
    data = {"summary": summarize(rows), "rows": [r3.scrub({k: r[k] for k in keep if k in r}) for r in rows]}
    Path(a.dest).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {a.dest}: {len(rows)} rows")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tag", default="l5")
    r.add_argument("--seed", type=int, default=27)
    r.add_argument("--reps", type=int, default=2)
    r.add_argument("--budget", type=float, default=8.0)
    r.add_argument("--out", default="")
    r.add_argument("--workdir", default="")
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("--file", default="")
    s.set_defaults(fn=cmd_summary)
    e = sub.add_parser("export")
    e.add_argument("dest")
    e.add_argument("--file", default="")
    e.set_defaults(fn=cmd_export)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
