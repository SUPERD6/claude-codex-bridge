"""Difficulty routing.

The orchestrating model should judge difficulty itself with the rubric in
skills/agent-delegate/references/rubric.md (it has read the code; a keyword
scorer has not). This module is the cheap, deterministic second opinion used
when --tier auto is given, and it always explains its reasons so the caller can
overrule it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# (pattern, points). Chinese and English, because the user mixes both.
SIGNALS: list[tuple[str, int, str]] = [
    # mechanical -> pull down
    (r"\b(typo|rename|reformat|format|lint|docstring|comment|boilerplate|bump version)\b|改名|重命名|格式化|错别字|加注释|补注释|样板", -2, "mechanical"),
    (r"\b(summari[sz]e|grep|find where|list all|locate)\b|总结|找出|列出|定位在哪", -1, "lookup/summary"),
    # a one-line edit ("add a line ... at the end of README.md"): its "add" alone scored it standard dev (T2, a
    # mid-price model) in the 2026-10-29 new-user walkthrough. Only the edit verb directly followed by a/one/the
    # line|sentence|word; "line-by-line" does not count, and any other signal in the brief still adds up as before
    (r"\b(?:add|append|insert|remove|delete|change|replace|edit)\s+(?:a|one|the|this|that)\s+(?:single\s+)?"
     r"(?:line|sentence|word)\b(?![-\w])|\bone[- ]line (?:fix|change|edit)\b|加一行|删一行|改一行|加一句",
     -2, "one-line edit"),
    # standard work
    (r"\b(add|implement|write|fix|test|script|endpoint|function)\b|实现|新增|修复|写一个|补测试|脚本|函数", 1, "standard dev"),
    # hard
    (r"\b(refactor|migrat\w*|performance|optimi[sz]e|flaky|intermittent|race|deadlock|memory leak|across (the )?(repo|codebase|modules))\b|重构|迁移|性能|优化|偶发|竞态|死锁|内存泄漏|跨模块|整个仓库", 2, "hard/multi-module"),
    (r"\b(design|architecture|trade-?off|root cause|why does)\b|设计|架构|方案|权衡|根因|为什么会", 2, "design/diagnosis"),
    # critical
    (r"\b(security|vulnerab\w*|auth\w*|crypto\w*|prove|proof|correctness|production|data loss|concurren\w*|novel algorithm)\b|安全|漏洞|鉴权|加密|证明|正确性|生产环境|数据丢失|并发|新算法|论文|科研结论", 3, "critical"),
]

UNCERTAIN = re.compile(r"\b(not sure|unknown|somehow|sometimes)\b|不知道|不确定|有时候|莫名", re.I)


@dataclass
class Route:
    tier: str
    score: int
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"tier": self.tier, "score": self.score, "reasons": self.reasons}


def classify(text: str, files: int = 0) -> Route:
    """Map a task description to T0..T4 with human-readable reasons."""
    score, reasons = 0, []
    low = text.lower()
    for pat, pts, name in SIGNALS:
        hits = len(re.findall(pat, low, flags=re.I))
        if hits:
            add = pts * min(hits, 2)
            score += add
            reasons.append(f"{name} ({add:+d})")
    if UNCERTAIN.search(low):
        score += 1
        reasons.append("unclear cause (+1)")
    if files >= 8:
        score += 2
        reasons.append(f"{files} files (+2)")
    elif files >= 3:
        score += 1
        reasons.append(f"{files} files (+1)")
    words = len(re.findall(r"\w+", text)) + len(re.findall(r"[一-鿿]", text)) // 2
    if words < 12 and score <= 0:
        reasons.append("very short, mechanical -> do it yourself")
        return Route("T0", score, reasons)
    if score <= -1:
        tier = "T1"
    elif score <= 2:
        tier = "T2"
    elif score <= 5:
        tier = "T3"
    else:
        tier = "T4"
    if not reasons:
        reasons.append("no strong signal -> standard")
    return Route(tier, score, reasons)
