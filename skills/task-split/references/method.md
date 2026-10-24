# Method: quantifying how to split a task

English · [中文](method.zh.md)

## 1. Success vs piece length (METR time horizons)

Kwa et al. (METR, 2025) fit agent success as a logistic function of log task length:

```
p(t) = σ(β · (ln h50 − ln t)) = 1 / (1 + (t / h50)^β)
```

- t is task length in human-minutes. h50 is the length the agent completes 50% of the time.
- They report 80% horizons about 4–6× shorter than 50% horizons. Taking 5×, solving σ(β·ln 5) = 0.8 gives β = ln 4 / ln 5 ≈ 0.86.
- The longest piece that still succeeds with probability p* is t_max = h50 · ((1 − p*) / p*)^(1/β). At p* = 0.8 that is about h50 / 5.
- Horizons double roughly every 7 months, so the h50 values in `data/horizons.toml` are dated guesses to be replaced by measured ones.

## 2. How many pieces: cost per success

Split a task of T minutes into n pieces of t = T/n. Each piece pays an overhead o for the brief, startup, review and handoff.

**Checkable pieces** (a test tells success from failure). A failed piece is retried, up to 3 tries:

```
p_piece = 1 − (1 − p)^3
tries   = p_piece / p
cost(n) = n · (o + t) · tries
P(task) = p_piece^n
pick n  = argmin cost(n) / P(task)   subject to p(t) ≥ 0.8
```

**Uncheckable pieces**. There is no retry, and errors go unnoticed and compound:

```
P(task) = p(t)^n
```

With β < 1, as n grows, P(task) ≈ exp(−n^(1−β) · (T/h50)^β) → 0. **Splitting uncheckable work finer makes the whole task less likely to succeed.** This is the quantitative reason for rule 2 ("only cut where you can check").

## 3. Where to cut: coupling and handoffs

Anchan & Sen (2026) model decomposition with two costs:
- An *attention tax*: a single agent's per-step error rises as its context grows.
- A *handoff tax*: each piece starts from a summary instead of the full workspace.

Decomposition pays only past the depth where the attention tax avoided exceeds the handoff tax. Practical reading:
- Cut where few facts must cross the boundary, i.e. low coupling. This is the classic modularity / design-structure-matrix criterion.
- Flag pieces with many inputs.

Parallel pieces that edit the same files would also have to merge their changes, so they are flagged.

## 4. When to cut: as needed

ADaPT (Prasad et al., NAACL Findings 2024) first tries a task as a whole. It decomposes into 3–5 sub-tasks with AND/OR logic only when the executor fails, and recurses up to a max depth. It beat plan-everything-first baselines by up to 28–33 points on ALFWorld, WebShop and TextCraft.

E3 (Yin & Feng, 2026) reaches the same conclusion for coding agents: estimate the minimum sufficient scope, take the lean path, and expand only when verification fails.

Hence the rules here: 3–5 milestones, recursive splitting only on failure or when a piece is over the horizon, and depth ≤ 3.

## 5. Parallel time (work / span)

The plan's dependencies form a DAG, which `check` processes like this:

- It groups the pieces into waves; each wave can run in parallel.
- It computes total work W and the critical path S.
- It reports the wall-time bounds max(S, W/w) ≤ T_w ≤ W/w + S for w lanes (Brent's theorem).
- Speedup = W / max(S, W/w). A long critical path means more lanes won't help; shorten the chain instead.

## 6. Calibration (automatic)

After each verified piece (`split_plan.py record`, or automatically when `ccx run --minutes M` is verified):

```
ln h50 ← ln h50 + 0.3 · β · (y − p(t))
```

This is one gradient step of the logistic log-likelihood in ln h50: a success on a piece the model "should" have
failed raises its horizon, and a failure on an easy one lowers it. The learned value is shared by both agents
through the hub.

## Sources

- Kwa et al., *Measuring AI Ability to Complete Long Tasks* (METR), 2025 — https://arxiv.org/html/2503.14499v3
- Prasad et al., *ADaPT: As-Needed Decomposition and Planning with Language Models*, NAACL Findings 2024 — https://ar5iv.labs.arxiv.org/html/2311.05772
- Anchan & Sen, *Attention Tax, Handoff Tax: A Stylised Model of When Multi-Agent LLM Systems Help*, 2026 — https://arxiv.org/html/2610.06069v1
- Asthana et al., *Runtime-Structured Task Decomposition for Agentic Coding Systems*, 2026 — https://arxiv.org/html/2605.15425v1 (decomposed runs cost more up front but 35–52% less on retries; the net gain depends on real failure rates)
- Yin & Feng, *Do AI Agents Know When a Task Is Simple?* (E3), 2026 — https://arxiv.org/abs/2607.13034
- Brent, *The parallel evaluation of general arithmetic expressions*, JACM 1974 (work/span bound)
