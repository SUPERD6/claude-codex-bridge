"""Batches for the batch / pipeline eval (scripts/eval/batch.py): hold-out changes (scripts/eval/tasks_holdout.py,
never used while ccx was tuned) put on one common start per batch (scripts/eval/batch_start.py).

A batch is several changes of ONE repository (one lead session works in one checkout), so the five external
hold-out tasks split by repository: humanize has four, itsdangerous one. Which combinations can share a start was
tried with git's three-way revert of every batch commit on the first commit that has all of them
(`python scripts/eval/batch.py check` repeats it):

- this repository, all 252 five-of-ten combinations of the hold-out set and its dropped candidates (re-run
  2026-10-27): only two revert onto one start, ho5-overlap below (one same-file overlap, ccx/commands/delegation.py)
  and undo-not-verdict + discuss-auto-tier + init-gitignore + leads-from-adapters + send-busy-guard (two overlaps,
  delegation.py and records.py); none is conflict-free. The dropped candidates are as unseen as the kept ones (they
  were left out of the hold-out set for size and cost only).
- humanize: all four are meant to revert onto ca892b3 (the intword fix, the newest of them); this needs a clone of
  humanize, so it is confirmed only when `batch.py check` runs there (a different end or a dropped change is a
  problem and the batch does not run).
- itsdangerous: its one hold-out task and the dropped its-future-timestamp both change src/itsdangerous/timed.py,
  and the older one's revert conflicts there (found on an earlier try; it also needs a clone to repeat): no batch of
  two can be built, so itsdangerous has no batch.

Each batch says the same-file overlap it is meant to have (`overlap`: code files two of its changes both change;
the check compares it with the real one): the N=5 batch of this repository has exactly one on purpose, its
conflict-free variant none; the humanize batch of four has one (time.py), its variant of three none. `end` is the
commit the check found as the common end (a different one is a problem: the history moved).
"""
from __future__ import annotations

import tasks_holdout

REPOS = tasks_holdout.REPOS
B: list[dict] = []


def batch(id: str, tasks: list[str], overlap: list[str], end: str, note: str, repo: str | None = None) -> None:
    B.append({"id": id, "tasks": list(tasks), "overlap": sorted(overlap), "end": end, "note": note,
              **({"repo": repo} if repo else {})})


def task_by_id(task_id: str) -> dict:
    """A hold-out task, or one of its dropped candidates (unseen as well)."""
    for t in tasks_holdout.T + tasks_holdout.DROPPED:
        if t["id"] == task_id:
            return t
    raise KeyError(f"unknown task: {task_id}")


batch("ho5-overlap", ["undo-not-verdict", "doctor-codex-sandbox", "discuss-auto-tier", "init-gitignore",
                      "send-busy-guard"], ["ccx/commands/delegation.py"], "5b68121",
      "five changes of this repository; undo-not-verdict and send-busy-guard both change ccx/commands/delegation.py "
      "(different functions): the one deliberate same-file overlap. One of the two five-of-ten sets that revert onto one start (the other has "
      "two overlaps). send-busy-guard alone does not revert on the end (undo-not-verdict is on top of it), so its "
      "hidden nodes come from the start with the other four put back.")
batch("ho4-disjoint", ["undo-not-verdict", "doctor-codex-sandbox", "discuss-auto-tier", "init-gitignore"], [],
      "5b68121",
      "the conflict-free variant: ho5-overlap without send-busy-guard. No five-change set of this repository is both "
      "conflict-free and revertible on one start, so this is the largest feasible one.")
batch("hz4-overlap", ["hz-intword-carry", "hz-naturaldelta-nonfinite", "hz-naturaldate-tz",
                      "hz-natural-list-iterables"], ["src/humanize/time.py"], "ca892b3",
      "all four humanize changes; naturaldelta-nonfinite and naturaldate-tz both change src/humanize/time.py (and "
      "tests/test_time.py)", repo="humanize")
batch("hz3-disjoint", ["hz-intword-carry", "hz-naturaldelta-nonfinite", "hz-natural-list-iterables"], [],
      "ca892b3", "the conflict-free humanize variant: one file each", repo="humanize")

IDS = [b["id"] for b in B]


def by_id(batch_id: str) -> dict:
    return next(b for b in B if b["id"] == batch_id)
