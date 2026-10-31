"""Stand-in for `gemini -p ... -o stream-json` (Gemini CLI 0.65.0 event shapes).

FAKE_STATUS(_GEMINI): done | blocked | blocked_then_done | quota
"""
import json
import os
import sys
import uuid
from fake_log import locked_append  # noqa: E402  (several fakes may append at once)

argv = sys.argv[1:]
stdin = sys.stdin.read() if "-p" in argv else ""
log = os.environ.get("FAKE_LOG")
if log:
    with locked_append(log) as f:
        f.write(json.dumps({"agent": "gemini", "argv": argv, "prompt": stdin, "depth": os.environ.get("CCX_DEPTH")}) + "\n")
if argv[:1] in (["--version"], ["-v"]):
    print("0.65.0"); sys.exit(0)

mode = os.environ.get("FAKE_STATUS_GEMINI") or os.environ.get("FAKE_STATUS", "done")
resuming = "--resume" in argv
sid = argv[argv.index("--resume") + 1] if resuming else argv[argv.index("--session-id") + 1]
ev = lambda **k: print(json.dumps(k), flush=True)  # noqa: E731
ev(type="init", timestamp="t", session_id=sid, model="gemini-3.8-flash")
ev(type="message", role="user", content=stdin[:50])
if mode == "quota":
    ev(type="error", severity="error", message="429 RESOURCE_EXHAUSTED: You have exhausted your capacity")
    ev(type="result", status="error", error={"type": "ApiError", "message": "RESOURCE_EXHAUSTED"},
       stats={"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "cached": 0, "input": 0})
    sys.exit(1)
status = "blocked" if mode == "blocked" or (mode == "blocked_then_done" and not resuming) else "done"
res = {"status": status, "summary": f"fake gemini {status}", "files_changed": [], "commands_run": [],
       "verification": "not-run", "open_questions": [], "next_step": ""}
from fake_discuss import answer as _discuss  # noqa: E402
res = _discuss(stdin, "gemini", log) or res
text = "```json\n" + json.dumps(res) + "\n```"
for i in range(0, len(text), 40):
    ev(type="message", role="assistant", content=text[i:i + 40], delta=True)
ev(type="result", status="success", stats={"total_tokens": 9300, "input_tokens": 9000, "output_tokens": 300,
                                          "cached": 6000, "input": 3000, "duration_ms": 1200, "tool_calls": 1})
