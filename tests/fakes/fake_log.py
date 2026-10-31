"""Appending to a log several fake CLIs share. `ccx batch` runs pieces at the same time, so fakes write one log from
several processes; on Windows "a" mode seeks to the end and then writes, which is not atomic across processes: a line
was lost and another came out empty (#196, windows 3.13). The whole write happens under a lock on the file."""
import contextlib
import os


@contextlib.contextmanager
def locked_append(path):
    with open(path, "a", encoding="utf-8") as f:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)      # waits (retries up to ~10 s) for the other writers
            try:
                f.seek(0, os.SEEK_END)
                yield f
                f.flush()
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield f
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
