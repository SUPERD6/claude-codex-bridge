"""No console windows popping up on Windows.

A console program started by a process that has no console of its own (a detached `ccx run --bg`, the start-up
hook a desktop app runs, ccx's background benchmark refresh) gets a brand-new visible console window. Every git,
codex or claude call ccx makes then flashes a terminal on the person's screen (reported 2026-10-25). Two rules:

- background processes ccx starts get a hidden console (`BACKGROUND`), which their own children share;
- when ccx itself runs without a console, every child it starts gets `CREATE_NO_WINDOW` (`install`).

A process that has a console (a terminal, or the hidden pseudo-console of an agent's shell) is left alone: its
children share that console and print to it as before."""
from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NEW_CONSOLE = 0x00000010
DETACHED_PROCESS = 0x00000008

# for background processes: a console with no window (not DETACHED_PROCESS, whose children would each pop one)
BACKGROUND = {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP} if os.name == "nt" \
    else {"start_new_session": True}


def has_console() -> bool:
    """True when this process is attached to a console, visible or not (GetConsoleProcessList counts its users)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        buf = (ctypes.c_uint32 * 1)()
        return ctypes.windll.kernel32.GetConsoleProcessList(buf, 1) > 0
    except Exception:  # noqa: BLE001 — can't tell: leave subprocess as it is
        return True


_installed = False


def install() -> None:
    """Without a console of our own, start children with no window (unless the caller asked for a console)."""
    global _installed
    if _installed or os.name != "nt" or has_console():
        return
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        flags = kwargs.get("creationflags", 0) or 0
        if not flags & (CREATE_NEW_CONSOLE | DETACHED_PROCESS):
            kwargs["creationflags"] = flags | CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    _installed = True
