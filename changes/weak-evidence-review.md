- H13, a review when the evidence is weak: in `--review auto` (the default) a write run is also reviewed once, by the
  cheapest rung of another vendor (about $0.005), when its acceptance command is `weak` (it passed wrong work before,
  J7) or there is no acceptance command and only the sub-agent checked itself. At most `[review] weak_daily` (20) a
  day, counted from `weak_review` ledger events; `[review] weak = false` or `--review off` switches it off. Whether
  this catches more wrong work is left to the next evaluation round.
