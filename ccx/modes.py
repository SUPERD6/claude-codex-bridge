"""Read-only or write? Inferred from the task text when the caller gives no --mode.

A wrong "write" lets an analysis task edit files; a wrong "read" stops a real change (the sub-agent then says
NEEDS_WRITE and the lead decides). So: an explicit read-only phrase wins, then any edit verb means write, then
analysis verbs mean read; with no clear signal we keep the old default (write) and say so."""
from __future__ import annotations

import re

# "do not modify", "只读" ... — the caller says outright that nothing may change
_READ_ONLY = re.compile(
    r"\bread[- ]only\b|\bdo(?:n't| not) (?:modify|change|edit|touch)\b|\bwithout (?:modifying|changing|editing)\b"
    r"|\bno (?:edits|changes)\b|只读|不要改|不要修改|别改|不改动|不修改|不动(?:代码|文件)", re.I)

# edit verbs; the Chinese ones are whole verbs, so "改进建议" / "写法" / "修养" don't count
_WRITE = re.compile(
    r"\b(?:modify|delete|remove|refactor|implement|create|rename|replace|migrate|reformat|bump|rewrite|add)\b"
    r"|改成|改为|改掉|改一下|改好|改名|修改|修复|修好|修正|修一下|重构|实现|新增|添加|增加|加上|加一个|删除|删掉|去掉|"
    r"替换|编写|写入|写一个|写个|写成|改写|创建|新建|迁移|格式化", re.I)    # not 提交: "审查这次提交" is a noun

# English words that are as often nouns ("review the change", "explain this fix"): an edit only when they
# don't follow an article or a determiner
_WEAK = re.compile(r"\b(fix|change|update|edit|write|patch|commit)\b", re.I)
_DET = {"the", "this", "that", "these", "those", "a", "an", "my", "your", "its", "our", "their", "of", "each",
        "every", "last", "latest", "recent", "previous", "next"}

_READ = re.compile(
    r"\b(?:analy[sz]e|analysis|review|explain|find|search|look (?:at|up|into)|compare|inspect|read|summari[sz]e|"
    r"assess|evaluate|investigate|diagnose|list|report|audit|check|why|what|which|where|how does)\b"
    r"|分析|审查|审阅|评审|解释|说明一下|查找|找出|找到|对比|比较|检查|阅读|看一下|看看|总结|评估|调查|诊断|列出|报告|"
    r"建议|为什么|是什么|怎么回事|哪里|哪些", re.I)


def _weak_edit(t: str):
    for m in _WEAK.finditer(t):
        before = re.findall(r"[A-Za-z']+", t[:m.start()])
        if not before or before[-1].lower() not in _DET:
            return m
    return None


def infer_mode(text: str) -> tuple[str, str]:
    """-> (mode, why). mode is "read" or "write"; why names the words that decided it (or that none did)."""
    t = text or ""
    m = _READ_ONLY.search(t)
    if m:
        return "read", f"says read-only ({m.group(0)!r})"
    m = _WRITE.search(t) or _weak_edit(t)
    if m:
        return "write", f"asks for a change ({m.group(0)!r})"
    m = _READ.search(t)
    if m:
        return "read", f"analysis only ({m.group(0)!r}), no edit verb"
    return "write", "no clear read or edit verb: kept the default (write)"


def resolve_mode(explicit: str | None, text: str) -> dict:
    """{mode, source: explicit|inferred|default, why}. An explicit --mode always wins."""
    if explicit:
        return {"mode": explicit, "source": "explicit", "why": "--mode given"}
    mode, why = infer_mode(text)
    return {"mode": mode, "source": "default" if why.startswith("no clear") else "inferred", "why": why}
