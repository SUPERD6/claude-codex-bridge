"""Stand-in for the CLI in ccx/agents/_template.py (`example run --json --model M [--resume id]`, task on stdin).
Copy it to fake_<name>.py with a new adapter and make it print what the real CLI prints (the event shapes you
checked), so tests never call the real tool. FAKE_STATUS: done | blocked | quota."""
import json
import os
import sys
import uuid
from fake_log import locked_append  # noqa: E402  (several fakes may append at once)

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print("example 1.4.0"); sys.exit(0)
stdin = sys.stdin.read()
log = os.environ.get("FAKE_LOG")
if log:
    with locked_append(log) as f:
        f.write(json.dumps({"agent": "example", "argv": argv, "prompt": stdin}) + "\n")
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else str(uuid.uuid4())
ev = lambda **k: print(json.dumps(k), flush=True)  # noqa: E731
ev(type="session", id=sid)
mode = os.environ.get("FAKE_STATUS", "done")
if mode == "quota":
    ev(type="error", message="429 rate limit: usage limit reached")
    sys.exit(1)
res = {"status": mode, "summary": f"fake example {mode}", "files_changed": [], "commands_run": [],
       "verification": "not-run", "open_questions": [], "next_step": ""}
ev(type="usage", input=1200, cached=800, output=150)
ev(type="final", text=json.dumps(res))
