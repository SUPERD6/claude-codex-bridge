"""`ccx stop <run_id>`: stop a running delegation and keep it resumable.

Stop asks, it does not take over: it writes <run>/stop.request and kills the sub-agent's process tree. The run's own
ccx process sees its child end with the request present and writes the final state itself (state=stopped,
kind=user_stopped), with everything it parsed so far. Only when that process is gone (killed, crashed, closed
window) does stop close the record and write the ledger row in its place. ledger.claim_final makes sure only one
of the two ever does.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time

from . import ledger, recover
from .config import Paths
from .runners import kill_tree, pid_alive


def _same_image(pid: int, child: str | None) -> bool:
    """With its ccx process gone, is `pid` still the sub-agent it recorded (pids get reused)? Windows only: on POSIX
    the process group stop kills is the sub-agent's own (start_new_session)."""
    if os.name != "nt" or not child:
        return True
    want = child.lower()
    if want.endswith((".cmd", ".bat")):
        want = "cmd.exe"                      # a .cmd shim runs as cmd.exe
    elif "." not in want:
        want += ".exe"
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=20, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip().strip('"').split('","')[0].lower() == want


def stop(p: Paths, run_id: str, wait: float = 15.0) -> dict:
    run_dir = p.runs / run_id
    rec = ledger.load_run(p, run_id)
    if rec.get("state") != "running":
        return {"run_id": run_id, "stopped": False, "state": rec.get("state"), "kind": rec.get("kind"),
                "why": "not running: nothing to stop"}
    host = socket.gethostname()
    (run_dir / "stop.request").write_text(json.dumps({"ts": time.time(), "pid": os.getpid(), "host": host}),
                                          encoding="utf-8")
    if rec.get("host") and rec["host"] != host:
        # the run's own ccx sees the request within a second and stops its sub-agent itself
        return {"run_id": run_id, "requested": True, "host": rec["host"],
                "why": "runs on another machine: its own ccx stops it within a second", "check": f"ccx show {run_id}"}
    parent = pid_alive(rec.get("ccx_pid"))
    killed = bool(rec.get("pid")) and (parent or _same_image(rec["pid"], rec.get("child"))) and kill_tree(rec["pid"])
    if parent:
        end = time.time() + wait
        while time.time() < end:              # its own ccx writes the final state
            rec = ledger.load_run(p, run_id)
            if rec.get("state") != "running":
                break
            time.sleep(0.2)
        out = {"run_id": run_id, "stopped": rec.get("state") != "running", "state": rec.get("state"),
               "kind": rec.get("kind"), "killed": killed, "closed_by": "its own ccx process"}
        if rec.get("state") == "running":
            out["why"] = "stop requested; its ccx process has not closed the run yet (it will within a second)"
    else:
        closed = recover.close_dead(p, run_id, "user_stopped", "stopped",
                                    "stopped by `ccx stop` (its ccx process was already gone)", "ccx stop")
        rec = closed or ledger.load_run(p, run_id)
        if not closed:
            out = {"run_id": run_id, "stopped": rec.get("state") != "running", "state": rec.get("state"),
                   "kind": rec.get("kind"), "killed": killed, "closed_by": "its own ccx process"}
        else:
            out = {"run_id": run_id, "stopped": True, "state": "stopped", "kind": "user_stopped", "killed": killed,
                   "closed_by": "ccx stop (its ccx process was gone)"}
    if out.get("kind") == "user_stopped" and rec.get("session_id"):
        out["resume"] = f"ccx resume {run_id}"
    return out
