"""Stand-in for the GitHub CLI used by the board's fallback and the intake tests: one repository, issues with
comments kept in FAKE_GH_STATE (JSON). A comment is a string (the board's tests) or {"author", "body", "createdAt"};
an issue may carry "author", "body", "labels", "state". FAKE_GH_VISIBILITY: PRIVATE (default) | PUBLIC.
FAKE_GH_LOGIN: the signed-in account (default "me"). Every call is logged to FAKE_LOG."""
import json
import os
import sys
from fake_log import locked_append  # noqa: E402  (several fakes may append at once)

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with locked_append(log) as f:
        f.write(json.dumps({"agent": "gh", "argv": argv}) + "\n")
state_f = os.environ["FAKE_GH_STATE"]
st = json.load(open(state_f, encoding="utf-8")) if os.path.exists(state_f) else {"issues": {}}
ME = os.environ.get("FAKE_GH_LOGIN", "me")


def save():
    with open(state_f, "w", encoding="utf-8") as f:
        json.dump(st, f)


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def comment(c, i):
    if isinstance(c, str):
        return {"author": {"login": ME}, "body": c, "createdAt": f"2026-10-25T00:00:{i:02d}Z"}
    return {"author": {"login": c.get("author", ME)}, "body": c["body"], "createdAt": c.get("createdAt", "")}


if argv[:2] == ["repo", "view"]:
    print(os.environ.get("FAKE_GH_VISIBILITY", "PRIVATE"))
elif argv[:2] == ["api", "user"]:
    print(ME)
elif argv[:2] == ["issue", "list"]:
    label, state = opt("--label"), opt("--state", "open")
    rows = []
    for n, i in st["issues"].items():
        if label and label not in i.get("labels", []):
            continue
        if state != "all" and i.get("state", "open") != state:
            continue
        rows.append({"number": int(n), "title": i["title"], "body": i.get("body", ""),
                     "author": {"login": i.get("author", ME)}, "url": f"https://github.com/o/r/issues/{n}",
                     "createdAt": "2026-10-25T00:00:00Z"})
    print(json.dumps(rows))
elif argv[:2] == ["issue", "view"]:
    cs = st["issues"][argv[2]].get("comments", [])
    print(json.dumps({"comments": [comment(c, k) for k, c in enumerate(cs)]}))
elif argv[:2] == ["issue", "create"]:
    n = str(len(st["issues"]) + 1)
    st["issues"][n] = {"title": opt("--title"), "comments": []}
    save()
    print(f"https://github.com/o/r/issues/{n}")
elif argv[:2] == ["issue", "comment"]:
    st["issues"][argv[2]]["comments"].append(opt("--body"))
    save()
elif argv[:2] == ["issue", "close"]:
    st["issues"][argv[2]]["state"] = "closed"
    save()
elif argv[:1] == ["api"]:
    n = argv[1].split("/issues/")[1].split("/")[0]
    print("\n".join(comment(c, k)["body"] for k, c in enumerate(st["issues"].get(n, {}).get("comments", []))))
else:
    sys.exit(f"fake gh: unsupported {argv}")
