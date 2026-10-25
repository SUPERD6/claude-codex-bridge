"""L7 `ccx skills stats`: how often each shared skill was loaded in Claude Code and in Codex, and when last, read from
the tools' own session files (read only; nothing is deleted, the output only suggests).

What counts as a load (checked against real files, Claude Code 2.1.309 and Codex 0.164, 2026-10-25):
  Claude Code projects/**/*.jsonl — an assistant tool_use named "Skill" (input.skill, "plugin:name" counts as name),
    or a user record with <command-name>/name</command-name> (the person typed /name).
  Codex sessions/**/rollout-*.jsonl — a response_item custom_tool_call / function_call whose command reads
    skills/<name>/SKILL.md (Codex loads a skill by reading its file). The skill list Codex puts into its prompt
    names every SKILL.md too, so only tool calls count.
The library is the hub's skills folder plus this repo's skills/. A skill's name and description are what both tools
list to the model every turn; its share is estimated from characters (about 4 per token for ASCII text, 1 per token
for other scripts), so it is an estimate, not a tokenizer count."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

_CMD = re.compile(r"<command-name>/?([A-Za-z0-9_.:-]+)</command-name>")
_READ = re.compile(r"skills[\\/]+([A-Za-z0-9_.-]+)[\\/]+SKILL\.md", re.I)


def _frontmatter(text: str) -> dict:
    """name / description from a SKILL.md front matter (one line, or a folded/indented block)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out, key = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("\"'")
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def library(roots: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for root in roots:
        for f in sorted(root.glob("*/SKILL.md")) if root.exists() else []:
            name = f.parent.name
            if name in out:
                continue
            try:
                fm = _frontmatter(f.read_text(encoding="utf-8", errors="replace")[:6000])
            except OSError:
                continue
            out[name] = {"name": fm.get("name") or name, "description": fm.get("description", "")}
    return out


def est_tokens(text: str) -> int:
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return round(ascii_n / 4 + (len(text) - ascii_n))


def _when(rec: dict) -> float | None:
    ts = rec.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _files(root: Path, pattern: str, since: float) -> list[Path]:
    """Files under root matching pattern, changed since `since`. os.walk skips a folder that vanishes or whose path is
    too long for Windows, where Path.rglob raises (seen on a real hub: a sub-agent's folder removed while walking)."""
    import fnmatch
    out = []
    for d, _, names in os.walk(root):
        for n in fnmatch.filter(names, pattern):
            f = Path(d) / n
            try:
                if f.stat().st_mtime >= since:
                    out.append(f)
            except OSError:
                continue
    return out


def _lines(f: Path, needles: tuple[str, ...]):
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if any(n in line for n in needles):
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except OSError:
        return


def claude_loads(home: Path, since: float) -> list[tuple[str, float]]:
    out = []
    for f in _files(home / "projects", "*.jsonl", since):
        for rec in _lines(f, ('"Skill"', "<command-name>")):
            t = _when(rec)
            if t is None or t < since:
                continue
            content = (rec.get("message") or {}).get("content")
            if rec.get("type") == "assistant" and isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill":
                        s = str((c.get("input") or {}).get("skill") or "")
                        if s:
                            out.append((s.rsplit(":", 1)[-1], t))
            elif rec.get("type") == "user" and isinstance(content, str):      # the CLI's own record of a /name
                out += [(m.rsplit(":", 1)[-1], t) for m in _CMD.findall(content)]
    return out


def codex_loads(home: Path, since: float) -> list[tuple[str, float]]:
    out = []
    for f in _files(home / "sessions", "rollout-*.jsonl", since):
        for rec in _lines(f, ("SKILL.md",)):
            pl = rec.get("payload") or {}
            if rec.get("type") != "response_item" or pl.get("type") not in ("custom_tool_call", "function_call"):
                continue
            t = _when(rec)
            if t is None or t < since:
                continue
            call = str(pl.get("input") or pl.get("arguments") or "")
            out += [(n, t) for n in dict.fromkeys(_READ.findall(call))]      # one call reading a file twice = once
    return out


def stats(roots: list[Path], claude_home: Path, codex_home: Path, days: float = 7, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    since = now - days * 86400
    lib = library(roots)
    rows = {n: {"skill": n, "claude": 0, "codex": 0, "last": None,
                "listing_tokens_est": est_tokens(f"- {n}: {v['description']}")} for n, v in lib.items()}
    for tool, loads in (("claude", claude_loads(claude_home, since)), ("codex", codex_loads(codex_home, since))):
        for name, t in loads:
            r = rows.get(name)
            if r is None:
                continue              # not a shared skill (a plugin's or the tool's own)
            r[tool] += 1
            r["last"] = max(r["last"] or 0, t)
    for r in rows.values():
        r["last"] = datetime.fromtimestamp(r["last"]).strftime("%Y-%m-%d %H:%M") if r["last"] else None
    used = sorted((r for r in rows.values() if r["claude"] or r["codex"]),
                  key=lambda r: -(r["claude"] + r["codex"]))
    unused = sorted((r for r in rows.values() if not (r["claude"] or r["codex"])),
                    key=lambda r: -r["listing_tokens_est"])
    per_turn = sum(r["listing_tokens_est"] for r in rows.values())
    idle = sum(r["listing_tokens_est"] for r in unused)
    return {"days": days, "skills": len(rows), "used": used, "unused": unused,
            "listing_tokens_est": per_turn, "unused_listing_tokens_est": idle,
            "note": "token counts are estimates from characters (~4 ASCII chars or 1 other char per token); "
                    "each tool lists every installed skill's name and description to the model every turn",
            "suggestion": (f"{len(unused)} shared skill(s) were not loaded in {days:g} days; together their "
                           f"descriptions are about {idle} tokens a turn. Keep the ones you still want, or uninstall "
                           "or merge the rest yourself; ccx deletes nothing.") if unused else
                          "every shared skill was loaded at least once"}


def render(s: dict) -> str:
    lines = [f"Shared skills loaded in the last {s['days']:g} days (Claude Code / Codex session files):", ""]
    w = max([len(r["skill"]) for r in s["used"] + s["unused"]] + [5])
    lines.append(f"  {'skill'.ljust(w)}  claude  codex  last")
    for r in s["used"]:
        lines.append(f"  {r['skill'].ljust(w)}  {r['claude']:>6}  {r['codex']:>5}  {r['last']}")
    if s["unused"]:
        lines += ["", f"Never loaded ({len(s['unused'])}), with the estimated tokens its description takes each turn:"]
        lines += [f"  {r['skill'].ljust(w)}  ~{r['listing_tokens_est']}" for r in s["unused"]]
    lines += ["", f"All {s['skills']} shared skills' listings: ~{s['listing_tokens_est']} tokens a turn "
                  f"(never loaded: ~{s['unused_listing_tokens_est']}). Estimate from characters.", s["suggestion"]]
    return "\n".join(lines)
