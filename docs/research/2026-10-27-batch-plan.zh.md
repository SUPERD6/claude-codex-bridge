# 批量 / 流水线评测：一次交出几项改动，在合并后的代码上打分（方案）

[English](2026-10-27-batch-plan.md) · 中文 · 2026-10-27 · 写于任何付费运行之前，本文没有实测数字

前一轮：[第 5 轮](2026-10-26-r5.zh.md)。第 5 轮每个组长会话只做一项改动。用户的第 7 条需求不同：“把 A、B、C……并行交出去，回来一个收一个”。这时看的是整批：总墙钟、总花费，以及全部合并之后的代码对不对。之前没有一轮在合并后的代码上打过分。

## 1. 批次（`scripts/eval/tasks_batch.py`）

批次只用 hold-out 改动（`scripts/eval/tasks_holdout.py` 及其落选候选），不用调参时用过的第 5 轮任务。一批 = **同一个**仓库的几项改动（一个组长在一个检出里干活）。

**共同起点**（`scripts/eval/batch_start.py`）：终点是 first-parent 线上第一个包含全部批内提交的提交；在它上面按从新到旧用 git 三方 revert 逐个撤销批内提交。某次 revert 在代码或测试上冲突，就把那项改动剔出（check 里写明）；只在文档上冲突时取撤销后的版本。组长拿到的是只有一个提交的新仓库（看不到历史里的答案）。

| 批次 | 仓库 | 改动 | 同文件重叠 |
|---|---|---|---|
| ho5-overlap | 本仓库 | undo-not-verdict、doctor-codex-sandbox、discuss-auto-tier、init-gitignore、send-busy-guard | `ccx/commands/delegation.py`（故意留一处） |
| ho4-disjoint | 本仓库 | 同上去掉 send-busy-guard | 无 |
| hz4-overlap | humanize | intword-carry、naturaldelta-nonfinite、naturaldate-tz、natural-list-iterables | `src/humanize/time.py` |
| hz3-disjoint | humanize | 同上去掉 naturaldate-tz | 无 |

**退而求其次的地方**：本仓库 10 个 hold-out 改动（含落选）的 252 个 5 项组合里，只有 2 个能放到同一个起点，而且都有同文件重叠（另一个有两处），所以无冲突版只有 4 项。ho5-overlap 里，send-busy-guard 不能在终点上单独撤销（undo-not-verdict 在同一文件里叠在它上面），它的隐藏节点改在“起点 + 其余四项”上找。2026-10-27 本仓库两批的 `batch.py check` 都通过；humanize 只有 4 个 hold-out 改动；itsdangerous 的两个候选都改 `timed.py`，放不到同一个起点，所以没有它的批次。设计里要的 N=8–10 无冲突批次，hold-out 集太小，做不出来。

**检查**（`python scripts/eval/batch.py check`，不调智能体）：每项改动过 holdout_check 的规模和泄漏检查（对照第 5 轮）；它的隐藏测试节点 = 它自己的测试文件里，在终点通过、只撤销它就失败的节点，再去掉在起点就已通过的；这些节点的测试函数不能原样出现在起点的测试文件里；起点能 import；声明的重叠和实际一致；终点和记录的一致。有任何问题的批次不跑。

## 2. 臂（每批一个组长会话）

组长是第 5 轮干净环境里新开的无头 Claude Code；`--lead-model` / `--lead-effort` 同第 5 轮（默认 opus medium，每行都记，也是 done-key 的一部分）。

| 臂 | 组长被告知的做法 |
|---|---|
| self | 全部自己做 |
| builtin | 交给内置 `worker` 子智能体；文件不重叠的改动可以一次开几个 Agent |
| ccx-batch | 写一份计划，用现有 `ccx batch`（并行，每个写任务一个 worktree），再合并分支 |
| ccx-pipeline | `ccx q add --plan`、`ccx q run --bg`、`ccx show <ids> --any --wait`，回来一个收一个，合并 `waiting` / `unmerged` 下的分支，`ccx q done`；遇到 backpressure 不再开新活 |
| balanced | 大且文件不重叠的改动用 `ccx run --bg --worktree --tradeoff balanced` 交出去，小的和同文件的自己做，再 `show --any --wait` 并合并 |

## 3. 指标（每个 批次 × 重复 × 臂）

- 总墙钟；组长花费和子智能体花费（builtin：组长账单里 worker 模型那部分；ccx 各臂：hub 账本）
- **组长检出里最终代码**上的隐藏测试：每项改动（它的节点全过）、全对（每项都对，且起点通过的节点没有变失败）、回归数
- 组长遇到的合并冲突（工具结果里的 `CONFLICT` 行）和留在代码里的冲突标记
- 组长的请求数、轮数、token、唤醒次数（返回了的阻塞等待）和空闲比例（这些等待的时间并集 / 墙钟，按每行输出的到达时间算）
- 额度事件：组长被拒的限流事件、ccx 任一次尝试里的 quota / 限流 / auth（不只看最后一次，换家重试会把它盖住）、backpressure 停止
- 每行都带第 5 轮的环境指纹、审计、残留和 `env_clean`；第一个单元前做 preflight，单元之间做检查

`summary` 按批次和臂给出各次重复的墙钟中位数 / p90 等，并把每两臂在同一批次的同一次重复上配对，只给带 n 的简单计数。不做 bootstrap：批次太少。

## 4. 费用

`python scripts/eval/batch.py run --dry-run --reps 2` 列出每个单元和估算。`EST_USD_PER_TASK` 里每项改动的数字是从第 5 轮推算的（self 五项约 $1.0，流水线约 $0.6–0.8），不是实测。4 批 × 5 臂 × 2 次重复，opus 组长约 $25–30。付费运行要用户点头；本次改动不花钱。

## 5. 这份方案说明不了什么

- “更快”或“一样对”都要等实测数据。
- 4 批、每批 3–5 项，不是 N=8–10；只在宽批次上才划算的流水线，这里测不到。
- humanize 两批能否撤干净、重叠是否如声明，来自之前一次检查的尝试，要在 humanize 的克隆上跑 `batch.py check` 才算确认。
