"""A fixed, made-up memory set for L1-L3 (BM25 ranking, kinds, scene blocks): 40 notes over five projects, ten
queries with the notes that answer them, and the kind each note should get. Used by test_memory_rank.py and by
`python tests/memory_bench.py` (prints the before/after numbers quoted in the PR)."""
from __future__ import annotations

# (topic, text, expected kind)
NOTES = [
    ("general", "The person prefers answers in simple Chinese, code and paths left as they are", "preference"),
    ("general", "用户希望回复先给结论，再讲必要的限制", "preference"),
    ("general", "默认用便宜的模型做小活，失败再升档", "preference"),
    ("general", "Never touch credentials or the tools' own config files outside marked blocks", "constraint"),
    ("general", "到 2026-11-01 之前不能改开局默认注入的内容", "constraint"),
    ("billing-api", "billing-api tests run with python -m pytest; fixtures live in tests/fixtures", "fact"),
    ("billing-api", "billing-api database migrations are applied with alembic upgrade head", "fact"),
    ("billing-api", "Careful: billing-api migrations break silently when the DATABASE_URL points at sqlite", "pitfall"),
    ("billing-api", "billing-api must keep invoice numbers strictly increasing per tenant", "constraint"),
    ("billing-api", "billing-api 2026-09-14 released v2 of the invoice export", "event"),
    ("billing-api", "The invoice export job runs nightly on the worker queue", "fact"),
    ("billing-api", "billing-api 部署失败时先看 worker 日志，常见原因是迁移没跑", "pitfall"),
    ("docs-site", "docs-site is built with mkdocs; preview with mkdocs serve", "fact"),
    ("docs-site", "docs-site pages are bilingual: x.md plus x.zh.md linking to each other", "constraint"),
    ("docs-site", "注意 docs-site 的中文页面标题不要带英文括号，搜索索引会坏", "pitfall"),
    ("docs-site", "docs-site moved to the new theme on 2026-08-02", "event"),
    ("docs-site", "The person likes diagrams over long tables in the docs", "preference"),
    ("ml-train", "ml-train checkpoints are saved every 500 steps to runs/<name>/ckpt", "fact"),
    ("ml-train", "ml-train 训练前必须固定随机种子并记录到配置里", "constraint"),
    ("ml-train", "ml-train 小心：混合精度下 loss 变成 NaN 时要先降学习率", "pitfall"),
    ("ml-train", "ml-train evaluation uses the held-out split only, never the training split", "constraint"),
    ("ml-train", "ml-train 的数据预处理脚本在 scripts/prep.py", "fact"),
    ("ml-train", "ml-train run 37 finished with 81.2 accuracy yesterday", "event"),
    ("mobile-app", "mobile-app builds with gradle; the release build needs the signing step", "fact"),
    ("mobile-app", "mobile-app 的推送通知在模拟器上不生效，要用真机测", "pitfall"),
    ("mobile-app", "mobile-app only supports Android 10 and later", "constraint"),
    ("mobile-app", "mobile-app shipped 3.2 to the store last week", "event"),
    ("mobile-app", "The person wants screenshots attached to every UI change", "preference"),
    ("relayline", "relayline uses only the Python standard library, 3.11 or newer", "fact"),
    ("relayline", "relayline tests use fake CLIs in tests/fakes and never call the real ones", "constraint"),
    ("relayline", "relayline 子会话的 PR 开自动合并，CI 全绿就合", "preference"),
    ("relayline", "relayline 在 Windows 上 heredoc 里的反斜杠会被吃掉，Python 改动用文件写", "pitfall"),
    ("relayline", "relayline 0.5.0 was tagged after round-2 results", "event"),
    ("general", "The shared snapshot should stay under 3 KB", "constraint"),
    ("general", "git stash is shared between worktrees; never pop someone else's entry", "pitfall"),
    ("general", "Course notes go in the learning folder", "fact"),
    ("general", "周报每周五发给组里", "event"),
    ("general", "Token counts in reports are estimates from the ledger", "fact"),
    ("general", "The CI matrix is Linux, Windows and macOS on Python 3.11 to 3.13", "fact"),
    ("general", "The person dislikes pop-up terminal windows during runs", "preference"),
]

# (query, numbers (1-based) of the notes that answer it)
QUERIES = [
    ("pytest fixtures billing", {6}),
    ("billing-api 部署 失败", {12, 8}),
    ("回复 中文 结论", {1, 2}),
    ("database migration sqlite", {8, 7}),
    ("ml-train loss NaN 学习率", {20}),
    ("docs bilingual zh pages", {14}),
    ("push notification simulator mobile-app 推送", {25}),
    ("worktree stash", {35}),
    ("随机种子 配置 ml-train", {19}),
    ("cheap model escalate 便宜 模型", {3}),
]

PROJECTS = ["billing-api", "docs-site", "ml-train", "mobile-app", "relayline"]


def load(p) -> list[dict]:
    """Write NOTES into the journal at `p` (a ccx Paths); returns the entries in order."""
    from ccx import memory
    memory.ensure(p)
    return [memory.add(p, text, by="codex" if i % 2 else "claude", topic=topic)
            for i, (topic, text, _k) in enumerate(NOTES)]


def old_search(es: list[dict], words: list[str]) -> list[int]:
    """`ccx mem search` before L1: every word must appear, journal order."""
    ws = [w.lower() for w in words if w.strip()]
    return [e["seq"] for e in es if all(w in e["text"].lower() for w in ws)]


def old_brief(es: list[dict], brief: str) -> list[int]:
    """The brief's pick before L1: count of shared words, newest first on ties."""
    from ccx.memory import _words
    bw = _words(brief)
    scored = [(len(bw & _words(f"{e.get('topic') or ''} {e['text']}")), e["seq"]) for e in es]
    return [s for n, s in sorted(scored, key=lambda x: (-x[0], -x[1])) if n]


def top3_hits(ranked: list[int], relevant: set[int], seqs: list[int]) -> int:
    """How many of the first 3 are relevant (`relevant` are note numbers; `seqs` maps them to seqs)."""
    want = {seqs[i - 1] for i in relevant}
    return sum(s in want for s in ranked[:3])


def run(p) -> dict:
    from ccx import memory
    es = load(p)
    seqs = [e["seq"] for e in es]
    rows = []
    for q, rel in QUERIES:
        new = [h["seq"] for h in memory.search(p, q.split()) if h.get("seq")]
        brief_new = [e["seq"] for e in memory.for_brief(p, q, k=3, budget=10_000, by_kind=True)]
        rows.append({"query": q, "relevant": len(rel),
                     "search_before": top3_hits(old_search(es, q.split()), rel, seqs),
                     "search_after": top3_hits(new, rel, seqs),
                     "brief_before": top3_hits(old_brief(es, q), rel, seqs),
                     "brief_after": top3_hits(brief_new, rel, seqs)})
    best = sum(min(3, r["relevant"]) for r in rows)
    total = {k: sum(r[k] for r in rows) for k in ("search_before", "search_after", "brief_before", "brief_after")}
    kinds_right = sum(memory.kind_of({"text": t, "topic": "general"}) == k for _t, t, k in NOTES)
    return {"rows": rows, "best": best, "total": total, "kinds_right": kinds_right, "notes": len(NOTES)}


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ccx.config import Paths
    r = run(Paths(Path(tempfile.mkdtemp())))
    for x in r["rows"]:
        print(f"{x['query']:<46} rel {x['relevant']}  search {x['search_before']}->{x['search_after']}  "
              f"brief {x['brief_before']}->{x['brief_after']}")
    t = r["total"]
    print(f"top-3 relevant, of {r['best']} possible: search {t['search_before']} -> {t['search_after']}, "
          f"brief {t['brief_before']} -> {t['brief_after']}")
    print(f"kinds guessed right from the words alone: {r['kinds_right']}/{r['notes']}")
