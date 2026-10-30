"""`ccx batch --merge` (B3 item 5, measured in M4): small independent pieces for the same folder, agent, model and
mode become one run instead of one run each. Opt-in: the flag, or `[merge] default = true`; without it `ccx batch`
is exactly what it was.

Why: a sub-agent's input is mostly a fixed prefix re-sent on every request (Codex ~18-25k, Claude ~13-15k; about 5
requests a run), so k separate runs pay that start about k times; one run doing the k pieces in a row pays it once
(round-2 PAR10: 5.7-7.4x fewer tokens, work cost about 1/5, wall clock about 2.5x). Not measured yet on mixed
difficulty: hence opt-in until M4 (plan: .ccx/plans/b3-plan-20261030.md).

What stays per piece: its own acceptance check (run by ccx after the merged run, each ~0.5 s), its own line in the
batch's `results` (the shape a lead reads is unchanged: one entry per piece, with `merged_run` / `merged_with`
added), `ccx undo <run> --piece <id>` for a piece that declared its `paths`. What is shared: one session, one ledger
row, one review (triggered by the whole diff: the 50-line threshold now counts all pieces, a known cost M4 reports
separately).

Failure handling: pieces whose check failed get one FOLLOWUP in the same session, for those pieces only; a piece
still failing is spun off as a run of its own (fresh session, in the same folder, the usual ladder and escalation).
The merged run itself never escalates (escalate=False) and never starts sub-agents of its own: one piece's trouble
must not climb the whole batch to a stronger model.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

DEFAULTS = {"default": False, "max_pieces": 5, "piece_minutes": 5.0, "total_minutes": 15.0}
STATUS_LINE = re.compile(r"^\s*\[(?P<id>[^\]\n]{1,80})\]\s*(?P<st>done|partial|failed)\b", re.M | re.I)
TAIL_CHARS = 1500
NOT_DONE = ("check_failed", "check_broken", "no_changes", "review_issues", "review_failed")            # of a failed check's output, in the follow-up

HEAD = ("[ccx merged pieces] The {n} pieces below are independent small tasks merged into this one run to save "
        "start-up cost. Do them one at a time, in this order; finish each one (its own check included, when it "
        "names one) before starting the next. Do not start sub-agents. If a piece cannot be done, say so for that "
        "piece in the summary and go on with the others.\n")
PIECE = "\n### Piece {k} of {n} - id: {id}{files}\n{brief}\n{check}"
FOOT = ("\nIn the final JSON: files_changed lists every file you changed; summary begins with one line per piece, "
        "`[id] done|partial|failed: one sentence`, then anything else.")
FIX = ("[ccx merged pieces] ccx ran each piece's acceptance check after your run. These failed:\n{failed}\n"
       "Fix only these pieces; keep the other pieces and the rest of your change as they are. Do not start sub-agents. "
       "Finish with the JSON result again, summary beginning with one `[id] done|partial|failed: ...` line per piece.")


def settings(cfg: dict) -> dict:
    c = cfg.get("merge") or {}
    out = dict(DEFAULTS)
    out["default"] = bool(c.get("default", False)) if isinstance(c.get("default", False), bool) else False
    for k in ("max_pieces", "piece_minutes", "total_minutes"):
        try:
            out[k] = max(1, int(c[k])) if k == "max_pieces" else max(0.0, float(c[k]))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def wanted(flag, cfg: dict) -> bool:
    """`--merge` given (1/0) wins; else [merge] default."""
    if flag is None:
        return settings(cfg)["default"]
    return bool(int(flag))


def _files(t: dict) -> set[str]:
    """The paths a piece declared: `paths` (a list; in a batch plan `files` is the routing rubric's count)."""
    got = t.get("paths")
    if not isinstance(got, list):
        return set()
    return {str(f).replace("\\", "/").removeprefix("./") for f in got if str(f).strip()}


def key(req, t: dict) -> tuple:
    """What two pieces must share to run as one: folder, agent, provider, mode, model rung or tier, worktree."""
    return (str(Path(req.cwd).resolve()), req.to, req.provider, req.mode, req.model, req.effort,
            req.tier if not req.model else None, bool(req.worktree))


def groups(items: list[tuple], cfg: dict) -> list[list[int]]:
    """items: [(Request, task dict)] in plan order -> groups of indexes, order kept; a piece that fits nowhere is
    a group of one. Fits: same key, no declared path (`paths`) in common with the group, its minutes <= piece_minutes (none
    given counts as piece_minutes), group <= max_pieces pieces and <= total_minutes in all."""
    s = settings(cfg)
    out: list[list[int]] = []
    open_groups: list[dict] = []
    for i, (req, t) in enumerate(items):
        try:
            minutes = float(t.get("minutes")) if t.get("minutes") is not None else s["piece_minutes"]
        except (TypeError, ValueError):
            minutes = s["piece_minutes"]
        files = _files(t)
        if minutes > s["piece_minutes"] or getattr(req, "resume_run", None):
            out.append([i])
            continue
        k = key(req, t)
        for g in open_groups:
            if g["key"] == k and len(g["idx"]) < s["max_pieces"] and g["minutes"] + minutes <= s["total_minutes"] \
                    and not (files and g["files"] & files):
                g["idx"].append(i)
                g["minutes"] += minutes
                g["files"] |= files
                break
        else:
            g = {"key": k, "idx": [i], "minutes": minutes, "files": set(files)}
            open_groups.append(g)
            out.append(g["idx"])
    return out


def _review_of(reqs: list) -> str:
    vals = {str(r.review or "auto") for r in reqs}
    return "on" if "on" in vals else "auto" if "auto" in vals else "off"


_RISK = {None: 0, "low": 0, "visible": 1, "critical": 2}


def _risk_of(reqs: list) -> str | None:
    return max((r.risk for r in reqs), key=lambda x: _RISK.get(x, 0))


def brief(reqs: list, tasks: list[dict]) -> str:
    n = len(reqs)
    parts = [HEAD.format(n=n)]
    for k, (r, t) in enumerate(zip(reqs, tasks), 1):
        files = sorted(_files(t))
        parts.append(PIECE.format(k=k, n=n, id=r.label or f"#{k}", brief=r.brief.strip(),
                                  files=(" (files: " + ", ".join(files) + ")") if files else "",
                                  check=f"Check for this piece: `{r.check}`\n" if r.check else ""))
    parts.append(FOOT)
    return "".join(parts)


def merged_request(reqs: list, tasks: list[dict]):
    """One Request for the group: the first piece's agent / model / folder, the strictest review, the highest
    risk, no check of its own (the pieces' checks run afterwards), no escalation, no sub-agents."""
    return dataclasses.replace(reqs[0], brief=brief(reqs, tasks), label="merge:" + "+".join(r.label or "?" for r in reqs),
                               check=None, escalate=False, allow_subagents=False, parallel=None, review=_review_of(reqs),
                               risk=_risk_of(reqs), route=None, task=None, step=None)


def self_reported(summary: str | None) -> dict[str, str]:
    """{piece id: done|partial|failed} from the summary's leading lines."""
    return {m.group("id").strip(): m.group("st").lower() for m in STATUS_LINE.finditer(summary or "")}


def _piece_files(t: dict, changed: list[str]) -> list[str]:
    declared = _files(t)
    if not declared:
        return list(changed)
    return [f for f in changed if _under(str(f).replace("\\", "/").removeprefix("./"), declared)]


def _under(f: str, declared: set[str]) -> bool:
    return f in declared or any(f.startswith(d.rstrip("/") + "/") for d in declared)


def finish(rec: dict, reqs: list, tasks: list[dict], p, cfg: dict) -> dict:
    """After the merged run: each piece's check in the run's folder, one follow-up for the failed pieces, a run of
    its own for each piece still failing; writes `pieces` into run.json and returns {"results": [per piece, plan
    order], "merged": {...}}."""
    from .delegate import Request, compact, run  # noqa: F401
    from .ledger import write_record
    from .workspace import run_check
    cwd = Path(rec["cwd"])
    timeout = int(cfg["defaults"].get("check_timeout_sec", 900))
    base = compact(rec)
    said = self_reported((rec.get("result") or {}).get("summary"))
    ran_ok = bool(base.get("ok")) and base.get("kind") not in NOT_DONE
    pieces: list[dict] = []
    for r, t in zip(reqs, tasks):
        pid = r.label or "?"
        row = {"id": pid, "paths": sorted(_files(t)) or None, "check_cmd": r.check, "said": said.get(pid)}
        if r.check:
            row["check"] = run_check(r.check, cwd, timeout)
            row["ok"] = bool(row["check"]["passed"]) and ran_ok
        else:
            row["ok"] = ran_ok and said.get(pid, "done") != "failed"
        pieces.append(row)
    fix_id = None
    failed = [x for x in pieces if not x["ok"]]
    if failed and rec.get("session_id") and ran_ok:
        lines = []
        for x in failed:
            if x.get("check"):
                tail = str(x["check"].get("tail") or "")[-TAIL_CHARS:]
                lines.append(f"- [{x['id']}] `{x['check_cmd']}` failed (exit {x['check'].get('exit')}):\n```\n{tail}\n```")
            else:
                lines.append(f"- [{x['id']}] you reported it as {x.get('said') or 'not done'}")
        fix = run(Request(to=rec["to"], brief=FIX.format(failed="\n".join(lines)), resume_run=rec["run_id"],
                          caller=reqs[0].caller, cwd=cwd, check=None, escalate=False, allow_subagents=False,
                          review=_review_of(reqs), risk=_risk_of(reqs), fallback=False,
                          label=rec.get("label") or "", progress=reqs[0].progress), p)
        fix_id = fix["run_id"]
        cf = compact(fix)
        fix_ok = bool(cf.get("ok")) and cf.get("kind") not in NOT_DONE
        for x in failed:
            x["fixed_in"] = fix_id
            if x.get("check_cmd"):
                x["check"] = run_check(x["check_cmd"], cwd, timeout)
                x["ok"] = bool(x["check"]["passed"]) and fix_ok
            else:
                x["ok"] = fix_ok
    spun: dict[str, dict] = {}
    for x, r in zip(pieces, reqs):
        if x["ok"]:
            continue
        # a run of its own, in the folder the merged run worked in (a worktree stays that worktree), the piece's own
        # settings and ladder; the follow-up above was its one shared chance
        own = run(dataclasses.replace(r, cwd=cwd, worktree=False, resume_run=None), p)
        x["spun_off"] = own["run_id"]
        spun[x["id"]] = own
    rec["pieces"] = []
    for x in pieces:                       # run.json keeps the verdicts, not the checks' output
        row = {k: v for k, v in x.items() if k != "check"}
        if x.get("check"):
            row["check"] = {k: x["check"].get(k) for k in ("cmd", "passed", "exit")}
        rec["pieces"].append(row)
    rec["merged"] = {"pieces": [x["id"] for x in pieces], "fix_run": fix_id,
                     "spun_off": {k: v["run_id"] for k, v in spun.items()}}
    write_record(p.runs / rec["run_id"], rec)
    results = []
    all_ids = [x["id"] for x in pieces]
    changed = list(base.get("files_changed") or [])
    for x, t in zip(pieces, tasks):
        if x["id"] in spun:
            out = compact(spun[x["id"]])
            # `ccx run` keeps exit 0 for a failed check (its old exit code); a piece whose check failed is not done
            out.update(label=x["id"], merged_run=rec["run_id"], merged_with=all_ids, spun_off=True,
                       ok=bool(out.get("ok")) and out.get("kind") not in NOT_DONE)
        else:
            out = dict(base)
            out.update(label=x["id"], ok=x["ok"], files_changed=_piece_files(t, changed), merged_run=rec["run_id"],
                       merged_with=all_ids)
            if x.get("said"):
                out["status"] = x["said"]
            if x.get("check"):
                c = x["check"]
                out["check"] = {"cmd": c["cmd"], "passed": c["passed"], "exit": c["exit"]}
                if not c["passed"]:
                    out["kind"] = "check_failed"
                    out["hint"] = (f"this piece's check failed after the merged run and its follow-up; see "
                                   f"`ccx show {rec['run_id']} --full`")
            elif not x["ok"]:
                out["kind"] = out.get("kind") or "failed"
            if x.get("fixed_in"):
                out["piece_fix"] = x["fixed_in"]
        results.append(out)
    return {"results": results, "merged": {"run_id": rec["run_id"], **rec["merged"]}}


def piece_files(rec: dict, piece: str) -> list[str]:
    """`ccx undo <run> --piece <id>`: the files that piece declared; a ValueError says why there are none."""
    rows = rec.get("pieces") or []
    if not rows:
        raise ValueError(f"run {rec.get('run_id')} is not a merged run (no pieces): undo the whole run")
    row = next((x for x in rows if x.get("id") == piece), None)
    if row is None:
        raise ValueError(f"no piece {piece!r} in run {rec.get('run_id')}: pieces are "
                         + ", ".join(str(x.get("id")) for x in rows))
    if not row.get("paths"):
        raise ValueError(f"piece {piece!r} declared no paths, so its changes cannot be told apart: undo the whole run")
    return list(row["paths"])


def restrict(paths: list[str], declared: list[str]) -> list[str]:
    d = {x.replace("\\", "/").removeprefix("./") for x in declared}
    return [f for f in paths if _under(f.replace("\\", "/").removeprefix("./"), d)]
