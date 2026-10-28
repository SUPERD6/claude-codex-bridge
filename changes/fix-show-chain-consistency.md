- Queue lock (`ccx q`, Windows CI flake in `test_threads_never_lose_a_write`): threads of one process now take turns on
  an in-process lock before the lock file (polling was unfair: a writer that had just released took it again before
  a sleeping waiter woke, and one waiter gave up after 20 s while the others wrote); a waiter's deadline (2 x timeout)
  now counts from the last time it saw the lock file change hands, with a hard cap of 30 x timeout; waits are short
  and jittered. The "can this folder be written at all" probe got a unique name per call (two threads in one 15 ms
  clock tick on Windows < 3.13 drew the same name, and one hit the other's delete-pending probe and failed with a bare
  PermissionError). A denied release is retried for about 2 s instead of 0.2 s (a lock left behind stalls everyone
  until it is stale). Locally: max wait for one write 7.1 s -> 0.2 s (6 threads, 10 ms writes).
