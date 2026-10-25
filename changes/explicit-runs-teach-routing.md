- Explicit picks can teach routing. A verdict reaches routing only with a difficulty b, and a run with `--model`
  / `--effort` but no `--minutes` (or rubric flags) has none: in the seven-cores A/B (PR #30) 63 verified luna-low
  runs left routing at n = 0, still predicting p = 0.48 where they were right 55 times out of 63. agent-delegate's
  explicit-pick line now includes `--minutes <n>` and says why, and the result of such a run says
  `route.learns: "no: give --minutes ..."`. (The A/B's 84 runs were fed back into one person's routing state with
  b from the minutes the A/B used; luna low at 5 minutes then predicts 0.94 and `--tradeoff save` picks it.)
