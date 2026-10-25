"""Stand-in for the GitHub CLI used by the board's fallback tests: one repository, issues with comments kept in
FAKE_GH_STATE (JSON). FAKE_GH_VISIBILITY: PRIVATE (default) | PUBLIC. Every call is logged to FAKE_LOG."""
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"agent": "gh", "argv": argv}) + "\n")
state_f = os.environ["FAKE_GH_STATE"]
st = json.load(open(state_f, encoding="utf-8")) if os.path.exists(state_f) else {"issues": {}}


def save():
    with open(state_f, "w", encoding="utf-8") as f:
        json.dump(st, f)


if argv[:2] == ["repo", "view"]:
    print(os.environ.get("FAKE_GH_VISIBILITY", "PRIVATE"))
elif argv[:2] == ["issue", "list"]:
    print(json.dumps([{"number": int(n), "title": i["title"]} for n, i in st["issues"].items()]))
elif argv[:2] == ["issue", "create"]:
    n = str(len(st["issues"]) + 1)
    st["issues"][n] = {"title": argv[argv.index("--title") + 1], "comments": []}
    save()
    print(f"https://github.com/o/r/issues/{n}")
elif argv[:2] == ["issue", "comment"]:
    st["issues"][argv[2]]["comments"].append(argv[argv.index("--body") + 1])
    save()
elif argv[:1] == ["api"]:
    n = argv[1].split("/issues/")[1].split("/")[0]
    print("\n".join(st["issues"].get(n, {}).get("comments", [])))
else:
    sys.exit(f"fake gh: unsupported {argv}")
