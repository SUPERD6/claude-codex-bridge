# 第 5 轮（r5e–r5h）的编排层审计：ccx 自己该做的事做到了吗？

[English](2026-10-28-harness-audit.md) · 中文 · 2026-10-28 · 只用磁盘上已有的数据，没有新的付费运行

前文：[第 5 轮](2026-10-26-r5.zh.md)。第 5 轮只评一件事：单元的隐藏测试过没过。这次审计在同一批单元上评另一件独立的事：
不管结果对不对，**ccx**（编排层）在智能体周围该做的事有没有做到。思路和七个组成部分来自 "Trial by Trace"
（arXiv 2610.32285，2026-10-28 核对过元数据；只读了摘要，没读全文）。下面的判据是我们为 ccx 写的，不是论文的原表，
而且是被评的项目自己写的。

脚本：`scripts/eval/harness_audit.py`。数据：`data/2026-10-28-harness-audit.json`（每个单元哪些判据没过；去掉了本机路径和说明）。

## 1. 评什么

- **智能体层**：单元的隐藏测试（结果行的 `ok`），和第 5 轮一样。
- **编排层**：7 个部分共 28 条二元判据。每条都是对单元留在磁盘上的东西（run.json、账本、events.N.log、stderr、
  shared-context.md、undo.json、archived.jsonl、组长的 stream）的确定性规则，给出 pass / fail / not_exercised
  和能证明它的文件。一个部分里只要有一条执行到的判据没过，这个部分就算没过；单元的编排层分数 = 执行到的部分里通过的比例（宏平均）。
- **机制链**：一张小表"编排层判据 → 智能体层条件"（例如：共享上下文里有写给组长的话 → 实现者提前停下）。
  只对做错的单元，把编排层判据没过且智能体条件成立的链列为"被触发"。这只是可能的机制，从不当成已证实的原因。
  在做对的单元里，同样的组合只单独记为"同时出现"（见第 5 节），不做归因。
- **LLM 评分表**：三条需要判断的项目（提示里有写给组长的指令；审查结论是否基于它真的查过的东西；总结是否被检查结果否定），
  默认关，用最便宜的模型（haiku），`--dry-run` 先给出费用。**本报告没有运行**（干跑：506 次调用，约 $1.42）。

| 部分 | 判据（简写） |
|---|---|
| Context 上下文 | 记录了/要求了共享上下文就真的送到 · 其中没有只写给组长的派活句子（用 ccx 现在的规则，`ccx/context_share.py`）· 没有假开局（实现者 20 秒内 blocked/partial 且没改文件）· 没读本人的私有记忆 / 工具主目录 |
| Execution 执行 | 运行以最终状态结束且有 final.lock · 失败的最后一次尝试不报成 ok · kind 与检查、审查、账本一致 |
| Governance 管控 | 改动在工作区/worktree 内 · 只读运行（审查）不改文件 · 不碰凭据路径 · 运行自己的子智能体不超上限 · 子智能体里不再起 ccx 运行 |
| Lifecycle 生命周期 | 没有残留锁 / running 状态 · 每个写入运行（含修复轮和续跑）都有自己的 undo.json · 续跑沿用原会话 · 结束的运行已归档 · 停止请求被执行 |
| Observability 可观测 | 每个运行一行账本 · 账本金额 = 各次尝试之和、审查计入、结果行金额 = 账本合计 · 每次尝试有事件日志 · run id 唯一 |
| Tools 工具 | --check 真的测了东西（不是退出码 4/5、不是 "not found"）· 沙箱/系统拒绝没让尝试中断 · Claude 子智能体没有被拒用工具（permission_denials）· 工具调用出错后恢复 |
| Verification 验证 | 子智能体说 done 后 ccx 自己重跑检查 · 证据弱时有带结论的审查 · ccx 最后的结论与隐藏测试一致 |

## 2. 结果（r5e–r5h，120 个单元）

| 臂 | 单元 | 智能体层（隐藏测试对） | 编排层宏平均 | 七部分全过 | 任务对但至少一条编排判据没过 |
|---|---|---|---|---|---|
| ccx2 | 80 | 76/80 | 0.67 | 0/80 | **76/76** |
| direct | 20 | 18/20 | 0.76 | 3/20 | 15/18 |
| builtin | 20 | 17/20 | — | — | 未执行到（没有 ccx 运行） |

另外两种看法（谁造成的见第 3 节）：

| 看法 | 去掉的判据 | ccx2：宏平均 / 全过 / 任务对但编排没过 | direct |
|---|---|---|---|
| 去掉**评测环境**造成的判据 | `ctx.no_private_context`（评测用了真实 CODEX_HOME） | 0.67 / 0/80 / 76/76 | 0.76 / 3/20 / 15/18 |
| 再去掉一条**这批运行之后已修的 ccx 缺陷** | 加上 `ctx.no_lead_only_lines`（#149 已修；不是环境造成的） | 0.80 / 20/80 / 56/76 | 0.76 / 3/20 / 15/18 |

第二种看法并不是对这批运行更干净的度量：写给组长的话确实送到了每个 ccx2 实现者。它只说明把所有 ccx2 单元共有的那条失败放到一边后还剩什么。

论文的 31%（任务成功但至少一条编排判据失败）不能直接对比：判据、编排工具、任务都不同。能借鉴的是现象本身：答案对了会掩盖编排问题。
按标签看，ccx2 的编排层宏平均每天都差不多（r5e、r5f、r5g、r5h 都是 0.66–0.67），这次审计分不出四天之间的差别。

**各判据的失败数**（失败单元 / 执行到的单元；只列有失败的）：

| 判据 | ccx2 | direct | 来源（按运行） |
|---|---|---|---|
| ctx.no_lead_only_lines | 80/80 | — | 每个 ccx2 实现者的共享上下文里都带着本人消息中的 "Do not edit files yourself: hand the implementation to a sub-agent through ccx" |
| ctx.no_false_start | 5/80 | 0/20 | 5 个 Codex 实现者运行在 7–9 秒内 blocked/partial 且没改文件：3 个卡在"要开子智能体"与"不许转交"的矛盾，2 个卡在共享上下文 / 工作区 |
| ctx.no_private_context | 27/80 | 0/20 | 28 个 Codex 实现者运行读了工作区外本人的 Codex 记忆文件（它自己的指令让它读的）；2 个 direct 运行只是把 CODEX_HOME 设成测试自己的临时目录，不算 |
| life.undo_snapshot | 50/80 | 12/20 | 82 个写入运行没有自己的 undo.json：全部 51 个修复轮和全部 31 个续跑（`ccx undo <它们的 id>` 会拒绝） |
| tool.check_ran | 5/80 | — | 5 次检查 pytest 退出码 4（测试文件不存在）；ccx 按设计报成 `check_broken` |
| tool.no_permission_denials | 37/68 | 14/20 | 142 个 Claude 审查运行里有 65 个被拒用 Bash（"don't ask" 模式），只能靠读代码审查 |
| ver.claim_matches_hidden | 15/80 | 8/20 | ccx2：4 次误报通过，11 次误报失败（对的工作被报成 6 次 `ok/partial`、4 次 `review_failed`、1 次 `check_broken`）；direct：1 次误报通过，7 次误报失败（`review_failed`） |

执行到的地方全部通过：运行状态和 final.lock、kind 与检查/审查/账本一致、改动在工作区内、审查不改文件、不碰凭据路径、
子智能体花费上限（Codex 子会话按路由先验价格计算）、账本行与金额（尝试、审查、结果行合计）、事件日志、run id、
续跑沿用会话、归档、停止请求、done 后 ccx 重跑检查、弱证据有审查。
本数据里没执行到：深度保护（没有子智能体的命令调用 ccx；这条规则只按 caller 区分嵌套运行，组长同厂商的子智能体起的嵌套运行会被放过）、
worktree、超时、残留进程（r5e–r5h 的行早于逐单元进程审计）。

**做错的单元与被触发的链**（被触发，不等于已证实）：

| 单元 | 链 | 解读 |
|---|---|---|
| r5e 2-quota-stop-log ccx2 | M1, M2, M4, M5, M7 | 写给组长的话 +"要开子智能体" → 假开局；审查者被拒用 Bash；ccx 最后说 ok |
| r5h 1-q-killed-spend ccx2 | M1, M2, M7 | 假开局（"规则在工作区外"），之后一次运行被 ccx 报成 ok |
| r5g 1-mem-report ccx2 | M7 | 只有误报通过 |
| r5g 2-q-resume-session ccx2 | M7 | 只有误报通过 |
| r5e 2-quota-stop-log direct | M4, M5, M7 | 审查者被拒用 Bash；误报通过 |
| r5e 1-q-resume-session direct | 无 | 没有挂在链上的编排判据失败 |
| r5f builtin × 3 | — | 没有 ccx 运行可审 |

ccx2 做错的 4 个单元，ccx 最后都说了 ok（M7）。这是本次最有用的一条：ccx2 做错时，ccx 自己的最终结论没有给组长任何提醒（组长之后有没有再查，这里没有读）。其中两个一开始还有假开局。

## 3. 哪些是 ccx 的，哪些是评测的，哪些已修

| 发现 | 归属 | 状态 |
|---|---|---|
| 写给组长的话送到了实现者 | ccx（共享上下文照抄了本人的派活句子）和评测（组长提示里这么写） | 这批运行之后已修：#149 整句去掉只写给组长的子句（`drop_lead_only`），子任务提示说明转交已经完成 |
| "要开子智能体"与"不许转交"导致的假开局 | ccx 提示 | 这批运行之后已修：#149（F14）只有 `--parallel` 才加子智能体那句 |
| 修复轮和续跑没有 undo.json | ccx | 这批运行之后已修：#149（链式快照） |
| 实现者读本人的 Codex 记忆 | 评测环境（真实 CODEX_HOME） | 后续轮次已由干净环境修好（`scripts/eval/preflight.py`）；这些行不是 `env_clean` |
| Claude 审查者被拒用 Bash | ccx（审查者权限） | 未修；待办"Claude 审查者按 vendor 写权限说明，并记 permission_denials" |
| 误报失败（对的工作报成 `review_failed`、`ok/partial`） | ccx 结论 | 未修；代价是组长多做事，不是单元做错 |
| ccx2 做错的 4 个单元被误报通过 | ccx 结论 + 智能体 | 未修；编排审计说不出是哪一环失守，只知道检查和审查都过了 |

所以用今天的 ccx 重跑，Context 和 Lifecycle 应该会好很多；这是预测，这里没有测。

## 4. [must] 的类别（只记录，待办 build 第 11 项）

每条审查的 `[must]` 按它提到的所有 file:line 和单元的 diff 打类别：**diff 内**（每个引用都在改动行 3 行以内；没写行号的引用，只要它的文件有改动就算 diff 内；新的未跟踪文件整个算改动）、
**diff 外**（至少一个引用在 diff 外）、**吞异常**（明确写了 吞 / 静默 / swallow；裸 "except" 或 "silent" 不算）、
**只涉及测试**（提到的文件全是测试）。ccx 本身什么都不改；`r5.py` 现在在每个新结果行里存同样的字段（`must_categories`），
以后 hold-out 运行就能按类别测救回率。

| 类别 | [must] 条数 | 有这类的单元 | 其中对 / 错 |
|---|---|---|---|
| diff 内 | 50 | 35 | 30 / 5 |
| diff 外 | 43 | 34 | 31 / 3 |
| 吞异常 | 8 | 7 | 6 / 1 |
| 只涉及测试 | 4 | 4 | 4 / 0 |

（ccx2 和 direct，已去重：修复轮的 first_review 重复它要修的那次审查。）这些数说明不了哪类能救回单元：按这一项的说法，那需要每类在第一次审查后的结果和 hold-out 集。

**这里用的是最终代码树的 diff，而且有偏差。** 这批运行没有记录每次审查当时看到的代码树，所以上面每一条都是对照单元的最终状态归类的
（`diff_basis: final_tree`）。如果修复轮改了某条 diff 外 [must] 指的那一行，那一行就进了最终 diff，这条就被算成 diff 内：
被修好的 [must] 会从 diff 外漂到 diff 内，偏的正是这份记录要测的按类别救回率。今天的 ccx 会记录每个写入运行结束时的代码树
（undo.json 的 `after`，在审查之后写入）；有它时脚本就用那棵树（`diff_basis: review_tree`：运行的 `review` 对照它自己的结束树，
修复轮的 `first_review` 对照它要修的那个运行的结束树）。hold-out 单元会被 r5 的清理删掉，所以 r5 在清理前把类别存进结果行；之后就没法再从磁盘审计它们。

## 5. 注意事项

- **开发集数据。** r5e–r5h 是调 ccx 时用过的单元，早于干净环境；ccx2 80 个、direct 20 个、builtin 20 个。不能推到别的任务或仓库。
- **判据是我们自己的。** 本项目为自己的职责写的，借了论文的七个部分，没用它的判据或任务；阈值（假开局 20 秒、diff 内 3 行容差、私有路径的模式）都是人为选择。
  判据本身可能错；每条失败都列出证据文件，可以手工核对。
- **近似。** 这批行的 [must] 用的是最终代码树的 diff（对修好的条目偏向 diff 内，见第 4 节）。写文件只从编辑工具的事件里读；
  shell 重定向和 Codex 子会话里的改动看不到。预算检查只覆盖 Codex 子会话。这些行查不了残留进程。
- **机制链是假设。** 被触发只说明两件事在一个做错的单元里同时出现。同样的组合在做对的单元里也会出现（ccx2：M4 36 个、M1 3 个；
  direct：M4 13 个），所以它们不是原因；JSON 里把这些单独记在 `chains_co_occurring_not_wrong`。
- **builtin** 没有 ccx 运行，这里完全没测它的编排层；这不是编排工具之间的比较。
- LLM 评分表没有运行。

复现方法：

```
python scripts/eval/harness_audit.py audit <work>/r5e <work>/r5f <work>/r5g <work>/r5h --results .ccx/eval/r5/results.jsonl --json audit.json
python scripts/eval/harness_audit.py audit ... --skip ctx.no_private_context
python scripts/eval/harness_audit.py audit ... --skip ctx.no_private_context --skip ctx.no_lead_only_lines
python scripts/eval/harness_audit.py audit ... --llm-rubric --dry-run
```
