- Tests: the queue-lock tests that waited out other writers with a real thread run on a fake clock instead, the
  other writers replacing the lock file on the waiter's own thread. On PR #207's CI (windows 3.12) that thread's
  last unlink met the waiter's read of the lock file (WinError 32), the thread died and the waiter gave up; now
  no runner speed or file-sharing timing decides them. Added: a direct test of how a lock file's holder is told
  apart, and one that a lock file that stops changing hands still fails after 2 * timeout. No code change.
