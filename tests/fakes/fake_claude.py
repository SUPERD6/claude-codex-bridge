"""Stand-in for `claude -p` used by tests (Claude Code 2.1.309 shapes).

--output-format stream-json (+ --verbose): system/init event first, then a final type=result event.
FAKE_STATUS: done | blocked | blocked_then_done | quota | hang
"""
import json
import os
import sys
import time
import uuid

argv = sys.argv[1:]
prompt = sys.stdin.read() if "-p" in argv else ""
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"agent": "claude", "argv": argv, "prompt": prompt,
                            "env_claudecode": os.environ.get("CLAUDECODE"),
                            "depth": os.environ.get("CCX_DEPTH"),
                            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                            "auth_token": bool(os.environ.get("ANTHROPIC_AUTH_TOKEN")),
                            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
                            "host_auth": [k for k in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH")
                                          if k in os.environ]}) + "\n")
if argv[:1] == ["--version"]:
    print("2.1.309 (Claude Code, fake)"); sys.exit(0)
if argv[:2] == ["auth", "status"]:
    out = os.environ.get("FAKE_CLAUDE_AUTH")
    print(out if out else json.dumps({"loggedIn": True, "authMethod": "claude.ai"})); sys.exit(0)
if argv[:2] == ["mcp", "get"]:
    sys.exit(1)
if argv[:2] == ["mcp", "add-json"]:
    sys.exit(0)

mode = os.environ.get("FAKE_STATUS_CLAUDE") or os.environ.get("FAKE_STATUS", "done")
resuming = "--resume" in argv
sid = argv[argv.index("--resume") + 1] if resuming else str(uuid.uuid4())
stream = "stream-json" in argv
if stream:
    if "--verbose" not in argv:
        print("Error: When using --print, --output-format=stream-json requires --verbose", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"type": "system", "subtype": "init", "session_id": sid, "model": "fake"}), flush=True)
if mode == "hang":
    time.sleep(30)
if mode == "quota":
    if stream:
        print(json.dumps({"type": "rate_limit_event", "session_id": sid,
                          "rate_limit_info": {"status": "rejected", "resetsAt": 1798000000}}))
    print(json.dumps({"type": "result", "subtype": "error", "is_error": True, "session_id": sid,
                      "result": "Claude usage limit reached. Your limit will reset at 6pm.",
                      "usage": {"input_tokens": 5, "output_tokens": 0}, "total_cost_usd": 0.0}))
    sys.exit(1)
for spec in filter(None, os.environ.get("FAKE_WRITE", "").split(";")):   # "path=content;path2=content"
    path, _, content = spec.partition("=")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
status = "done"
model = argv[argv.index("--model") + 1] if "--model" in argv else ""
if mode == "blocked" or (mode == "blocked_then_done" and not resuming) or         model in (os.environ.get("FAKE_BLOCK_MODELS") or "").split(","):
    status = "blocked"
split_if = os.environ.get("FAKE_SPLIT_IF")
if split_if and split_if in prompt:
    status = "blocked"
    os.environ["FAKE_SUMMARY"] = "SPLIT: too big"
res = {"status": status, "summary": os.environ.get("FAKE_SUMMARY") or f"fake claude {status}", "files_changed": [],
       "commands_run": [], "verification": os.environ.get("FAKE_VERIFY", "not-run"), "open_questions": [],
       "next_step": os.environ.get("FAKE_NEXT_STEP", "") if split_if and split_if in prompt else ""}
if "[ccx review" in prompt:   # F1 reviewer: FAKE_REVIEW="issues,pass" = the answers of successive reviews
    seq = (os.environ.get("FAKE_REVIEW") or "pass").split(",")
    cf = os.path.join(os.path.dirname(log or "."), "fake-review-count")
    n = int(open(cf).read()) if os.path.exists(cf) else 0
    open(cf, "w").write(str(n + 1))
    v = seq[min(n, len(seq) - 1)]
    res.update(status="done", summary=f"REVIEW: {v}",
               open_questions=["[must] a.py:3 — off by one in the loop"] if v == "issues" else [])
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
                  "result": json.dumps(res), "structured_output": res, "total_cost_usd": 0.0123,
                  "usage": {"input_tokens": 10, "cache_creation_input_tokens": 900,
                            "cache_read_input_tokens": 3000, "output_tokens": 200}}))
