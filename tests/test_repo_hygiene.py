"""No personal data in tracked files: machine paths, e-mail addresses, machine names, local-state folders.

A path like <drive>:\\Users\\<someone>\\... or /home/<someone>/... in the repo leaks who wrote it and how their machine
is laid out; so does an e-mail address or a Windows machine name (DESKTOP- or LAPTOP- plus seven characters). The check is generic on purpose:
it knows the *shape* of these things, never anyone's real name, address or machine. Placeholders (<you>, example,
runner, single letters used in tests, example.com / .invalid addresses, ...) are allowed. CI runs this file on every
push, docs-only ones included (.github/workflows/hygiene.yml).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Files being removed elsewhere; drop an entry once it is gone from main.
SKIP_FILES = {"two-way-test-log.txt"}

NAME = r"([^\\/\s\"'`<>*$%{}()\[\],;:|]+)"
SLUG_NAME = r"([^\\/\s\"'`<>*$%{}()\[\],;:|-]+)"
# Any case: Windows ignores it, and Codex writes its trust entries lowercased ([projects.'c:\users\...']).
PATTERNS = [
    # C:\Users\<name>, c:\users\<name>, C:/Users/<name>, //c/Users/<name>, /c/Users/<name> (Git Bash)
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:?[\\/]+Users[\\/]+" + NAME, re.IGNORECASE),
    # /Users/<name> (macOS), /home/<name> (Linux): only at the start of a path, not inside x/home/...
    re.compile(r"(?<![\w.~-])/(?:Users|home)/" + NAME, re.IGNORECASE),
    # C--Users-<name>-proj: Claude Code's project-folder name for a Windows path
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]--Users-" + SLUG_NAME, re.IGNORECASE),
]

# Folder names that are not a person: placeholders, CI runners, test stand-ins.
PLACEHOLDERS = {
    "you", "your", "yourname", "your-name", "user", "username", "user-name", "me", "name", "someone", "somebody",
    "example", "example-user", "alice", "bob", "carol", "jane", "john", "johndoe", "foo", "bar", "test", "tester",
    "runner", "runneradmin", "public", "default", "shared", "all", "all users", "hub", "x", "a", "b", "u",
}


def _allowed(name: str) -> bool:
    n = name.strip().lower()
    if not n.strip(".~…"):                 # "...", "…", "~"
        return True
    if n in PLACEHOLDERS or len(n) == 1:
        return True
    return n.startswith("runner")               # RUNNER~1, the 8.3 name of a CI runner's home


def find_personal_paths(text: str) -> list[str]:
    hits = []
    for pat in PATTERNS:
        for m in pat.finditer(text):
            if not _allowed(m.group(1)):
                hits.append(m.group(0))
    return hits


# An e-mail address that is not a documented placeholder. Allowed: RFC 2606 / 6761 names (example.*, *.invalid,
# *.test, *.localhost), GitHub's and git hosts' noreply addresses, and the generic user@... the board docs use.
EMAIL = re.compile(r"(?<![\w.+\\-])([\w.+-]+)@([\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,})(?![\w-])")
EMAIL_DOMAINS_OK = re.compile(
    r"^(?:(?:[\w-]+\.)*example\.(?:com|net|org)|[\w.-]+\.(?:invalid|test|localhost)|(?:[\w-]+\.)*noreply\.github\.com"
    r"|user\.com)$", re.IGNORECASE)
EMAIL_LOCAL_OK = {"noreply", "no-reply", "ci", "me", "you", "user", "someone", "example", "test"}
# Windows gives a fresh machine the name DESKTOP-<7 chars> (or LAPTOP-); such a name identifies one machine.
MACHINE = re.compile(r"(?<![\w-])(?:DESKTOP|LAPTOP)-[A-Z0-9]{6,8}(?![\w-])")


def find_personal_data(text: str) -> list[str]:
    """Paths, e-mail addresses and machine names in one line of text."""
    hits = find_personal_paths(text)
    for m in EMAIL.finditer(text):
        if not EMAIL_DOMAINS_OK.match(m.group(2)) and m.group(1).lower() not in EMAIL_LOCAL_OK:
            hits.append(m.group(0))
    hits.extend(m.group(0) for m in MACHINE.finditer(text))
    return hits


def _tracked_files() -> list[str]:
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def test_no_personal_paths_in_tracked_files():
    found = []
    for rel in _tracked_files():
        if Path(rel).name in SKIP_FILES:
            continue
        path = ROOT / rel
        try:
            data = path.read_bytes()
        except OSError:                         # deleted in the working tree, a submodule, ...
            continue
        if b"\0" in data[:8192]:                # binary
            continue
        text = data.decode("utf-8", "replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for hit in find_personal_data(line):
                found.append(f"{rel}:{lineno}: {hit}")
    assert not found, ("personal data in tracked files (a machine path, e-mail address or machine name; use <you>, "
                       "example.com or a placeholder):\n" + "\n".join(found))


# Folders and files that hold one person's local state. .gitignore lists them; this makes sure a `git add -f`
# or an older ignore file never lets one through. Not the plugin folder `.claude-plugin/`.
LOCAL_STATE = re.compile(r"^(?:\.claude|\.ccx|\.codex|_site)/|(?:^|/)[^/]*-test-log\.txt$|\.local\.(?:json|toml|cmd|sh)$")


def test_no_local_state_files_tracked():
    tracked = [p for p in _tracked_files() if LOCAL_STATE.search(p)]
    assert not tracked, "local-state files are tracked (they belong to one machine):\n" + "\n".join(tracked)


_N = "jdoe42"      # spelled through a variable so this file does not trip its own scan


@pytest.mark.parametrize("text", [
    f"C:\\Users\\{_N}\\proj", f"D:/Users/{_N}/x", f"//c/Users/{_N}/.codex", f"/c/Users/{_N}/x",
    f"see /home/{_N}/.config", f"cd /Users/{_N}/code", f"[projects.'c:\\users\\{_N}\\x']", f"C:\\USERS\\{_N}",
    f"C--Users-{_N}-proj", f"c--users-{_N}",
])
def test_detects_home_folders(text):
    assert find_personal_paths(text)


@pytest.mark.parametrize("text", [
    "C:\\Users\\<you>\\hub", "/home/<you>/.ccx-hub", "C:\\Users\\RUNNER~1\\AppData", "/home/runner/work",
    "//c/Users/a/.codex", "/Users/example/x", "C:\\Users\\...\\x", "D:/x/home/memories/MEMORY.md", "~/.ccx-hub",
    "$HOME/.agents", "%USERPROFILE%\\.codex", "C:\\Users\\All Users\\x", "c:\\users\\…\\x", "C--Users-you-proj",
])
def test_allows_placeholders(text):
    assert not find_personal_paths(text)


_D = "gmail" + ".com"      # spelled in two parts so this file does not trip its own scan
_M = "DESKTOP" + "-AB12CD3"
_L = "LAPTOP" + "-9XK2Q7PZ"


@pytest.mark.parametrize("text", [
    f"wrote to {_N}@{_D} yesterday", f"author: {_N}42@outlook.{_D.split('.')[1]}", f"<{_N}@my-company.co.uk>",
    f"machine {_M}", f"host: {_L}", f"[user]\n\temail = {_N}@{_D}",
])
def test_detects_addresses_and_machine_names(text):
    assert find_personal_data(text)


@pytest.mark.parametrize("text", [
    "ci@example.com", "t@example.invalid", "me@user.com", "@user.setter", "@pytest.mark.parametrize",
    "104068711+someone@users.noreply.github.com", "Claude <noreply@anthropic.com>", "a@b.test", "x@sub.example.org",
    "DESKTOP-x (a word, not a name)", "see the desktop-first layout", "DESKTOP-ABC",
])
def test_allows_placeholder_addresses(text):
    assert not find_personal_data(text)
