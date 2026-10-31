"""Stand-in for `dsh --profile headless --json` (DeepSeek Harness 0.2.1-rc.3 event shapes, from
packages/bundle/headless/src/json-stream.ts).

FAKE_STATUS(_DSH): done | blocked | blocked_then_done | quota | auth
"""
import json
import os
import sys
import uuid
from fake_log import locked_append  # noqa: E402  (several fakes may append at once)

argv = sys.argv[1:]
if argv[:1] in (["--version"], ["-V"]):
    print("0.2.1-rc.3"); sys.exit(0)
task = sys.stdin.read() if argv[-1:] == ["-"] else ""
patch = argv[argv.index("--patch") + 1] if "--patch" in argv else None
log = os.environ.get("FAKE_LOG")
if log:
    with locked_append(log) as f:
        f.write(json.dumps({"agent": "dsh", "argv": argv, "prompt": task, "depth": os.environ.get("CCX_DEPTH"),
                            "patch": json.loads(open(patch, encoding="utf-8").read()) if patch else None,
                            "permission": os.environ.get("DSH_PERMISSION_MODE"),
                            "telemetry": os.environ.get("DSH_TELEMETRY_MODE"),
                            "deepseek_key": os.environ.get("DEEPSEEK_API_KEY")}) + "\n")

mode = os.environ.get("FAKE_STATUS_DSH") or os.environ.get("FAKE_STATUS", "done")
resuming = "--session-id" in argv
sid = argv[argv.index("--session-id") + 1] if resuming else f"session-{uuid.uuid4()}"
ev = lambda **k: print(json.dumps(k), flush=True)  # noqa: E731
ev(type="session", sessionId=sid, cwd=os.getcwd())
ev(type="status", phase="turn_start", turn=1)
if mode in ("quota", "auth"):
    msg = {"quota": "429 Too Many Requests: rate limit exceeded", "auth": "401 invalid api key"}[mode]
    ev(type="status", phase="turn_end", turn=1, reason="error")
    ev(type="final", text="")
    print(f"dsh: LLM_ERROR: {msg}", file=sys.stderr)
    sys.exit(1)
status = "blocked" if mode == "blocked" or (mode == "blocked_then_done" and not resuming) else "done"
res = {"status": status, "summary": f"fake dsh {status}", "files_changed": [], "commands_run": [],
       "verification": "not-run", "open_questions": [], "next_step": ""}
ev(type="status", phase="step_start", turn=1, step=1)
ev(type="thinking", text="reading the task")
ev(type="tool_call", callId="c1", tool="read", input={"path": "a.py"})
ev(type="tool_result", callId="c1", status="completed", result="x = 1")
ev(type="status", phase="step_end", turn=1, step=1,
   usage={"inputTokens": 1200, "outputTokens": 100, "cacheReadTokens": 3000, "totalTokens": 4300})
ev(type="status", phase="step_start", turn=1, step=2)
ev(type="text", text=json.dumps(res))
ev(type="status", phase="step_end", turn=1, step=2,
   usage={"inputTokens": 300, "outputTokens": 200, "cacheReadTokens": 4200, "cacheWriteTokens": 50})
ev(type="status", phase="turn_end", turn=1, reason="completed")
ev(type="final", text=json.dumps(res))
