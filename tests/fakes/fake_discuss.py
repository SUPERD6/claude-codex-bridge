"""What the fake CLIs answer to a `ccx discuss` brief. FAKE_DISCUSS="objections,agree" = the critic's answers in
successive rounds (default agree); FAKE_DISCUSS_FAIL=judge makes that role's turn fail."""
import os
import re


def way(prompt: str) -> dict | None:
    """`ccx way` steps: the planner's plan, the judge's pick (FAKE_PICK=A|B, default B)."""
    m = re.search(r"\[ccx way \S+: (plan|pick)\]", prompt)
    if not m:
        return None
    base = {"status": "done", "files_changed": [], "commands_run": [], "verification": "not-run", "next_step": ""}
    if m.group(1) == "plan":
        return {**base, "summary": "add a helper, then call it", "open_questions": [
            "[step] add helper in util.py", "[step] call it from main.py", "[accept] main.py uses the helper"]}
    return {**base, "summary": f"PICK: {os.environ.get('FAKE_PICK', 'B')} — smaller change",
            "open_questions": ["[reason] fewer lines"]}


def answer(prompt: str, agent: str, log: str | None) -> dict | None:
    w = way(prompt)
    if w:
        return w
    m = re.search(r"\[ccx discuss \S+ role=(\w+) round=(\d+)", prompt)
    if not m:
        return None
    role, rnd = m.group(1), int(m.group(2))
    if os.environ.get("FAKE_DISCUSS_FAIL") == role:
        return {"status": "blocked", "summary": "could not", "files_changed": [], "commands_run": [], "verification": "not-run", "open_questions": [], "next_step": ""}
    base = {"status": "done", "files_changed": [], "commands_run": [], "verification": "not-run", "next_step": ""}
    if role == "proposer":
        return {**base, "summary": f"{agent} proposal r{rnd}: keep one queue file",
                "open_questions": [f"[point] one file keeps writes atomic (r{rnd})", "[point] cheaper to read"]}
    if role == "critic":
        seq = (os.environ.get("FAKE_DISCUSS") or "agree").split(",")
        v = seq[min(rnd - 1, len(seq) - 1)]
        return {**base, "summary": f"CRITIQUE: {v}. r{rnd}",
                "open_questions": ["[must] two writers can lose an update"] if v == "objections"
                else ["[note] name the lock file"]}
    return {**base, "summary": "RECOMMEND: one queue file with a lock",
            "open_questions": ["[consensus] one file is simpler", "[disagreement] lock vs append-only log",
                               "[reason] the lock answers the lost-update objection"]}
