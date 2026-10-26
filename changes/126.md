- `ccx ui`: a refused POST (bad Origin, token or Host) reads the request body before answering, so Windows no longer
  resets the connection and the client gets the 403 instead of ConnectionAbortedError (a flaky CI test, now also 10 s
  faster).
