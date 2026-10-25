"""Public benchmark data for task-routing: fetched at most once a week, cached on this machine, always credited.

Standard library only. Three open sources (licences checked 2026-10-24):
  epoch     Epoch AI benchmarking hub, https://epoch.ai/benchmarks — CC BY 4.0 for Epoch's own runs and the
            Epoch Capabilities Index; files marked _external are other projects' data and keep their licences.
  lmarena   LMArena leaderboard dataset, https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset — CC BY 4.0.
  modelsdev models.dev price and model database, https://models.dev — MIT.
Nothing is redistributed: the cache stays next to the routing state on the user's machine.

Cache layout (benchmarks.json):
  {"fetched_at": ts, "sources": {name: {"ok", "fetched_at", "url", "credit", "error"?}},
   "scores": [{"source", "benchmark", "model", "effort", "harness", "score", "lo", "hi", "date"}],
   "prices": {"<provider>/<model>": {"input", "output", "cache_read", "tiers"?}}}
Model names stay as each source writes them; matching them to routing rungs is the merge step's job."""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

MAX_AGE_DAYS = 7
TIMEOUT = 30
UA = "task-routing/1 (+https://github.com/SUPERD6/relayline)"

EPOCH_ZIP = "https://epoch.ai/data/benchmark_data.zip"
# file in the zip -> (benchmark name, score column)
EPOCH_FILES = {
    "epoch_capabilities_index/eci_scores.csv": ("eci", "eci"),
    "gpqa_diamond.csv": ("gpqa_diamond", "Best score (across scorers)"),
    "swe_bench_verified.csv": ("swe_bench_verified", "Best score (across scorers)"),
    "simpleqa_verified.csv": ("simpleqa_verified", "Best score (across scorers)"),
    "frontiercode_external.csv": ("frontiercode", "Main score"),
    "terminalbench_external.csv": ("terminal_bench", "Accuracy mean"),
    "metr_time_horizons_external.csv": ("metr_time_horizon_min", "Time horizon"),
    "webdev_arena_external.csv": ("webdev_arena", "Arena Score"),
    "hle_external.csv": ("hle", "Accuracy"),
}
LMARENA_ROWS = ("https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset"
                "&config={config}&split=latest&offset={offset}&length=100")
LMARENA_CONFIGS = ("text", "text_factuality", "agent_task_outcome_explicit", "agent_tool_hallucination",
                   "agent_bash_reliability", "search_factuality")
MODELSDEV = "https://models.dev/api.json"
MODELSDEV_PROVIDERS = ("anthropic", "openai", "deepseek", "google")

CREDITS = {
    "epoch": "Epoch AI, 'Capabilities & benchmarking', epoch.ai/benchmarks (CC BY 4.0; *_external files keep "
             "their original licences)",
    "lmarena": "LMArena leaderboard dataset, huggingface.co/datasets/lmarena-ai/leaderboard-dataset (CC BY 4.0)",
    "modelsdev": "models.dev (MIT)",
}


RETRY_FAILED_HOURS = 6       # a source that failed is tried again sooner than the weekly refresh


def _get(url: str, tries: int = 3, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310 — fixed https URLs above
                return r.read()
        except OSError as e:          # 5xx and timeouts are often brief (seen: HF datasets-server 502)
            code = getattr(e, "code", None)
            if k == tries - 1 or (code is not None and code < 500):
                raise
            time.sleep(2 * (k + 1))
    raise OSError("unreachable")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_epoch(blob: bytes) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = set(z.namelist())
    out = []
    for f, (bench, col) in EPOCH_FILES.items():
        if f not in names:
            continue
        for r in csv.DictReader(io.StringIO(z.read(f).decode("utf-8"))):
            model = r.get("Model version") or r.get("Model") or ""
            score = _num(r.get(col))
            if not model or score is None:
                continue
            lo = _num(r.get("eci_ci_low") or r.get("CI_low"))
            hi = _num(r.get("eci_ci_high") or r.get("CI_high"))
            if lo is None and _num(r.get("stderr")) is not None:
                se = _num(r.get("stderr"))
                lo, hi = score - 1.96 * se, score + 1.96 * se
            out.append({"source": "epoch", "benchmark": bench, "model": model,
                        "display": r.get("Display name") or "",
                        "effort": r.get("Reasoning effort") or r.get("Reasoning level") or "",
                        "harness": r.get("Harness") or r.get("Agent") or "",
                        "score": score, "lo": lo, "hi": hi,
                        "date": r.get("Release date") or r.get("date") or ""})
    return out


def parse_lmarena(pages: dict[str, list[dict]]) -> list[dict]:
    out = []
    for config, rows in pages.items():
        for r in rows:
            score = _num(r.get("rating") if r.get("rating") is not None else r.get("score"))
            if score is None:
                continue
            lo = _num(r.get("rating_lower") if r.get("rating_lower") is not None else r.get("score_ci_lower"))
            hi = _num(r.get("rating_upper") if r.get("rating_upper") is not None else r.get("score_ci_upper"))
            out.append({"source": "lmarena", "benchmark": f"lmarena_{config}", "model": r.get("model_name") or "",
                        "display": "", "effort": "", "harness": "", "score": score, "lo": lo, "hi": hi,
                        "date": "", "votes": r.get("vote_count") or r.get("observation_count")})
    return out


def parse_modelsdev(blob: bytes) -> dict:
    d = json.loads(blob)
    out = {}
    for prov in MODELSDEV_PROVIDERS:
        for mid, m in ((d.get(prov) or {}).get("models") or {}).items():
            c = m.get("cost") or {}
            if c.get("input") is None:
                continue
            out[f"{prov}/{mid}"] = {k: c[k] for k in ("input", "output", "cache_read", "cache_write", "tiers")
                                    if k in c}
    return out


def _lmarena_pages(get) -> dict[str, list[dict]]:
    pages = {}
    for config in LMARENA_CONFIGS:
        rows, offset = [], 0
        while offset < 1000:
            d = json.loads(get(LMARENA_ROWS.format(config=config, offset=offset)))
            batch = [x["row"] for x in d.get("rows", [])]
            rows += batch
            if len(batch) < 100:
                break
            offset += 100
        pages[config] = rows
    return pages


def load_plugins(dirs) -> list:
    """Extra sources the user adds on their own machine: any <dir>/*.py with NAME, CREDIT, fetch(get) -> score rows
    and optionally KIND_WEIGHTS {kind: {benchmark: weight}}. For data whose terms allow only the user's own use
    (e.g. a key-based API): it stays on that machine, nothing of it is in this repository."""
    import importlib.util
    out = []
    for d in dirs:
        for f in sorted(Path(d).glob("*.py")) if Path(d).is_dir() else []:
            try:
                spec = importlib.util.spec_from_file_location(f"bench_source_{f.stem}", f)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                if getattr(m, "NAME", None) and callable(getattr(m, "fetch", None)):
                    out.append(m)
            except Exception:  # noqa: BLE001 — a broken plugin never stops the built-in sources
                continue
    return out


def refresh(dest: Path, get=_get, plugin_dirs=()) -> dict:
    """Fetch all sources; a failing source keeps its previous data and records the error."""
    old = load(dest)
    now = time.time()
    plugins = load_plugins(plugin_dirs)
    data = {"fetched_at": now, "sources": {}, "scores": [], "prices": old.get("prices", {}), "kind_weights": {}}
    names = ("epoch", "lmarena", *(m.NAME for m in plugins))
    prev_scores = {s: [x for x in old.get("scores", []) if x["source"] == s] for s in names}
    jobs = {"epoch": (EPOCH_ZIP, lambda: parse_epoch(get(EPOCH_ZIP))),
            "lmarena": ("huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
                        lambda: parse_lmarena(_lmarena_pages(get))),
            "modelsdev": (MODELSDEV, lambda: parse_modelsdev(get(MODELSDEV)))}
    for m in plugins:
        CREDITS.setdefault(m.NAME, getattr(m, "CREDIT", m.NAME))
        if callable(getattr(m, "available", None)) and not m.available():
            # not set up on this machine (e.g. no key): not a failure, so it doesn't trigger early retries
            data["sources"][m.NAME] = {"ok": True, "skipped": "not configured", "fetched_at": now,
                                       "url": getattr(m, "URL", "plugin"), "credit": CREDITS[m.NAME], "n": 0}
            continue
        jobs[m.NAME] = (getattr(m, "URL", "plugin"), lambda m=m: [{**r, "source": m.NAME} for r in m.fetch(get)])
        for kind, ws in (getattr(m, "KIND_WEIGHTS", None) or {}).items():
            data["kind_weights"].setdefault(kind, {}).update(ws)
    for name, (url, job) in jobs.items():
        try:
            got = job()
            if name == "modelsdev":
                data["prices"] = got
                n = len(got)
            else:
                data["scores"] += got
                n = len(got)
            data["sources"][name] = {"ok": True, "fetched_at": now, "url": url, "credit": CREDITS[name], "n": n}
        except Exception as e:  # noqa: BLE001 — network, format change: keep the old copy, say why
            prev = (old.get("sources") or {}).get(name) or {}
            data["sources"][name] = {"ok": False, "fetched_at": prev.get("fetched_at"), "url": url,
                                     "credit": CREDITS[name], "error": f"{type(e).__name__}: {e}"[:200]}
            if name != "modelsdev":
                data["scores"] += prev_scores.get(name, [])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(dest)
    return summary(data)


def load(dest: Path) -> dict:
    try:
        return json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def age_days(dest: Path) -> float | None:
    t = load(dest).get("fetched_at")
    return None if not t else (time.time() - t) / 86400


def is_stale(dest: Path, days: float = MAX_AGE_DAYS) -> bool:
    d = load(dest)
    a = age_days(dest)
    if a is None or a >= days:
        return True
    failed = any(not v.get("ok") for v in (d.get("sources") or {}).values())
    return failed and a * 24 >= RETRY_FAILED_HOURS


def summary(data: dict) -> dict:
    return {"fetched_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(data.get("fetched_at") or 0)),
            "sources": {k: {"ok": v["ok"], "n": v.get("n"), **({"error": v["error"]} if v.get("error") else {})}
                        for k, v in (data.get("sources") or {}).items()},
            "credit": [v["credit"] for v in (data.get("sources") or {}).values()]}
