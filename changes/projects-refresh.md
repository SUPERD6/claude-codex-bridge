- The project catalog stays fresh by itself: at session start (`ccx mem delta`, the start-up hook) ccx rescans
  `projects.roots` in a detached, windowless process when the catalog is older than `[projects] refresh_hours`
  (24; 0 = off), or when roots are set and nothing was scanned yet. The start never waits; one scan at a time
  (a start within 10 minutes of the last one leaves it). `ccx projects scan` is still the full manual rescan
  (`ccx/projects.py` `refresh_later`).
