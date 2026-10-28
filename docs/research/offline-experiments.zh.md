# 离线实验 C1-C6、B1 预统计与 B3 预检（报告）

[English](offline-experiments.md) · 中文 · 2026-10-28 · ccx 在 main `0837da1`（#152）之后 · codex-cli 0.164.0 · Windows 11

这是什么：改进计划 C 组里便宜的实验（不花付费 CLI 的钱，或只花几美分），在第 5 轮开发集记录（r5c..r5h：180 个单元
代码树，100 个带 lead 流的 ccx2 单元）上跑；外加计划要求 B1（按原因跳过 review）动手前的 $0 统计，和 B3（按档位路由的
Codex low 档精简启动）动手前必须做的检查。B2（修复轮复审聚焦）的离线回放**没有做**，所以 PR-B2 仍然卡着（见下表）。
所有数字只来自开发集（10 个调过的任务），hold-out 还没跑过。**花费：$0.051**（只有 C6 花钱，其余 $0）。

脚本（`scripts/eval/`，只用标准库，测试在 `tests/test_eval_offline.py`，用假数据）：

| # | 脚本 | 花费 | 是否运行 |
|---|---|---|---|
| C1 | `c1_namecheck_scan.py` | $0 | 已跑 |
| C2 | `c2_lead_accept.py`（`plan` / `generate` / `score`） | 估计 $1.20（sonnet） | 只跑了 plan |
| C3 | `c3_check_reuse.py` | $0 | 已跑 |
| C4 | `c4_must_filter.py --dry-run` | 估计 $1.83（haiku）到 $5.50（sonnet） | 只跑了空跑 |
| C5 | `c5_diff_read.py` | $0 | 已跑 |
| C6 | `c6_reuse_rule.py`（借用 `review_replay.py` 的执行器） | $0.051 | 已跑，6 次 review |
| B1 | `b1_skip_count.py`（`--trees`：C1 的 `--reviewed` 目录） | $0 | 已跑 |
| B2 | （聚焦复审的离线回放） | 没估价 | **没做** |
| -  | `offline_common.py` | - | 共用工具 |

记录从系统临时目录（`%TEMP%/r5c..r5h`）或 `CCX_REPLAY_RECORDS` 读；结果行来自 `.ccx/eval/r5/results.jsonl`。

## 结论一览

| # | 问题 | 答案 | 计划的门槛 | 下一步 |
|---|---|---|---|---|
| C1 | `ccx namecheck` 会误报吗？ | 改动代码里 8 个命中 0 个误报（180 个最终树 + 183 个被审树）；681 个完整文件、28 个外部仓库文件和本仓库 214 个文件 0 误报 | 误报 = 0：通过 | 按 tiers.toml 先做前后对比，再谈 `fail` |
| C3 | ccx 能复用 builder 自己跑过的 check 吗？ | 110 次 builder 跑的正是 ccx 的命令且双方都过；4 个 builder 过、ccx 不过（全是 #147 前的引号 bug）；无 review 运行的 check 中位 4.8 s | 只测量 | 不做运行时开关 |
| B1 | `unsure` / `tests_miss_change` 经常是唯一触发吗？ | 107 次首轮 review 里：`tests_miss_change` 唯一触发 20 次（18.7%），`unsure` 唯一触发 1 次（0.9%；它的 5 次里 4 次仍会因 `tests_miss_change` 被审） | 低于约 5% 就放弃 | 计划唯一的近期候选（只跳 `unsure`）低于 5%：除非组长另有决定，放弃 PR-B1 |
| B2 | 聚焦复审能保住所有救回和 [must] 吗？ | **没跑**（没写脚本，没估价） | 10/10 救回、[must] 一个不漏、中位省 >= 10 s | PR-B2 仍然卡着 |
| C5 | "lead 没读 diff" 能区分对错吗？ | 不能：ccx2 里 85/93 个对的单元和 7/7 个错的单元都没跑 `git diff`；p = 1.0 | 必须能区分 | 放弃这个技能变体 |
| C6 | review 加一条"复用已有常量"的规则，能抓到 r5e:2 吗？ | 加规则 3/3 报成 [must]；现在的简报 0/3 报成 [must]（2/3 写成 [note]） | 必须抓到 | 候选；还要对照组 |
| C2 | lead 写验收测试 | 没跑（5 个任务有错单元，要覆盖 10 个任务，估计 $1.20） | 抓到 >= 2，误报 <= 3% | 要用户同意花钱 |
| C4 | 强评审先过滤 [must] | 没跑（52 个修复轮：9 个 fail->pass，35 个 pass->pass；估计 $1.83-5.50） | 救回的一个不丢（计划内 9/9，没判出结果的算丢） | 超出计划假设的 $0.5 |
| B3 | 精简启动会不会丢共享记忆？ | 不会：`--ignore-user-config` 下 `$CODEX_HOME/AGENTS.md` 和简报里的记忆都还在；启动到第一次请求快 3.1 s | 预检 | PR-L 可以做（默认关） |

## C1 namecheck 扫描

用本 checkout 的 `ccx namecheck` 扫：(a) 每个单元自 `start` 提交以来的改动，和 `ccx run` 查的范围一样；(b) 183 个
reviewer 在修复轮之前看到的树（用 review 简报里的 diff 重建；修复轮会覆盖这个状态，review 抓到的 bug 只在这里）；
(c) 180 个最终树里每个不同的 `.py` 文件整份；(d) 外部仓库源码（humanize 13 个文件、itsdangerous 15 个）和本仓库（214 个）。
每个命中都人工读过并标注（标注写在脚本里）。

| 扫描 | 文件 | 命中 | 真 | 误报 | 在吞异常的宽泛 `except` 里 |
|---|---|---|---|---|---|
| 改动，最终树 | 180 个单元 | 1 | 1 | 0 | 1 |
| 改动，被审树 | 183 个树（跳过 0 个） | 7 | 7 | 0 | 6 |
| 整份文件，最终树 | 681 个不同文件 | 1（同一个 bug） | 1 | 0 | 1 |
| 外部仓库 + 本仓库 | 242 | 0 | - | - | - |

8 个改动命中是 5 个单元里的 5 个 bug（r5g:2 把没绑定的 `cfg` 用了两次：一个 bug 两个命中；r5c:2 在最终树和两个被审树里各出现一次）：`cmd_mem` 里用了从没绑定的 `load_config` / `cfg`（projects-refresh，4 个单元；
都在会话启动路径的 `except Exception: pass` 里，测试看不到 NameError，只会少一次刷新），以及 `delegate.py` 没导入
`_caller`（r5g:1 mem-report；不在任何 try 里，只要简报带记忆就会崩）。只有 r5c:2 projects-refresh-ccx2 的 bug 留到了最后
（这个单元是错的）；另外四个在修复轮后消失。有命中的 6 个被审树里 reviewer 点名了未定义的名字 2 次，漏了 4 次。

被审树：脚本现在会记下没能重建的树（JSON 里的 `reviewed_skipped`，输出时和总数放在一起）。`--reviewed` 用短目录时 183 个
全部重建（跳过 0 个）。用长目录（会话 scratchpad，约 110 个字符）时，有一个树在 Windows 上因路径太长失败：r5e:2
projects-refresh-direct 的 review 95aa（`FileNotFoundError`），总数变成 182；在短目录下重建，这个树没有命中，所以上面的
总数不变。`--reviewed` 请用短路径。

按计划的规则：没有任何误报，所以下一步是 `config/tiers.toml` 已经写明的、改成 `namecheck = "fail"` 之前的前后对比。
不需要 `swallow` 模式（它是为"误报都在吞异常块外"准备的，这里没有误报）。`warn` 是否已经能让 lead 或 reviewer 修掉命中，
r5 看不出来（那时还没有 namecheck），要等 hold-out 记录。

## C3 复用 builder 的 check

176 个带 `--check` 的写入运行（builder 全是 Codex；不含 review 子运行）。builder 在最后一次改文件之后有没有跑 ccx 的
check 命令？"一致"的意思是：ccx 的命令是 builder 命令里完整的一条语句。先去掉外层 shell（`powershell -Command '...'`），
按 `;` `&&` `||` `|` 和换行拆开，某一条语句去掉引号和空白差异后要和 ccx 的命令相同。更窄的运行（`file.py::Test::one`、
`-k ...`）或更宽的运行（多加文件）都不算一致。复合命令的退出码是最后一条语句的，所以结果改从输出里唯一的 pytest
汇总行读；一条命令里跑了几次测试时算"看不清"。

| builder 最后一次 | 运行数 | ccx 的 check 通过 | 失败 |
|---|---|---|---|
| 同一命令，通过 | 114 | 110（一致） | 4 |
| 同一命令，失败 | 10 | 7 | 3 |
| 同一命令和别的测试在一条命令里（看不清） | 2 | - | - |
| 别的测试命令通过（含更窄 / 更宽的运行） | 37 | - | - |
| 最后一次改动后没跑测试 | 13 | - | - |

（这份报告的上一版按子串匹配，数出 125 / 121 / 11：它把 10 次更窄或更宽的运行（比如只跑一个 `::test`）当成了 ccx 的
命令，并按最后的退出码读了 2 条跑了两次测试的复合命令。）

4 个"builder 过、ccx 不过"全是 `ERROR: file or directory not found: or`：ccx 自己在 Windows 上跑带引号的 `-k "a or b"`
出错，#147 已修（r5 记录都在它之前）。7 个"builder 失败、ccx 通过"有两个原因：5 个是 builder 的沙箱
（`tests/test_recover.py::TestSweep` 的 kill 测试在 Codex 沙箱里会失败）；2 个是 PowerShell 没有展开 check 命令里的
通配符（r5e:2 q-resume-session 的 `tests/test_q*.py`、r5f:1 quota-stop-log 的 `tests/test_quota*.py`：
`file or directory not found`），而 ccx 自己跑时展开了。所以 builder 的失败也不是信号，而且同样的命令文本换个 shell
不一定是同一次运行。秒数：无 review 的运行 check 中位 4.8 s（56 次，合计 474 s；按单元中位 2.5 s）；其中能复用的 27 次
合计 281 s，分摊在 100 个单元上。按计划：只测量，不做运行时开关（要 #147 后不一致为 0、且无 review 运行 check 中位
超过 30 s 才考虑）。

## B1 预统计：`unsure` 或 `tests_miss_change` 是不是唯一触发？

`b1_skip_count.py`，$0。ccx 只记录第一个触发的 review 原因，顺序按 `ccx/review.py`（asked、risk、>= 50 行代码改动、
unsure、声称的文件对不上、没报文件；再往后是证据弱的几种原因，最后一个是 `tests_miss_change`）。所以只要记录的是
`tests_miss_change`，它就是唯一触发。对 `unsure`，脚本检查它后面的触发：文件对不上 / 没报文件（声称的文件对比被审的
diff）、改了已有测试、没有 check，以及在 reviewer 看到的树上跑 `check_gap`（用 C1 重建的被审树）。没有模拟 `weak_daily`
每日上限。

| | review 数 | asked | 行数 | `tests_miss_change`（唯一） | `unsure` | `unsure` 唯一 |
|---|---|---|---|---|---|---|
| 首轮 review | 107 | 39 | 43 | 20（18.7%） | 5 | 1（0.9%） |
| 全部 review（含修复轮） | 179 | 98 | 51 | 23 | 6 | 1 |

首轮 5 次 `unsure` 里有 4 次即使跳过也仍会因 `tests_miss_change` 被审；唯一的那次是 r5h:1 waiting-evals。两种原因
合计在 107 次首轮 review 里唯一触发 21 次（19.6%，review 花费 $0.29），但计划已经排除了跳过 `tests_miss_change`
（约每 100 个单元少对 1 个），而近期候选、只跳 `unsure` 的唯一触发是 1/107（0.9%），低于计划的约 5% 线。结论：按计划
（只跳 `unsure`）PR-B1 放弃，除非组长另有决定。（计划里的"120 次里 6 次"口径不同；这里数的是有 review 运行记录的首轮 review。）

## B2：没做

B2 的门槛（聚焦式修复轮复审的离线回放：保住 10/10 个救回、首轮全量复审标过的 [must] 一个不漏、中位节省 >= 10 s）
需要回放脚本和付费 review；这次两者都没写、也没估价。回放跑过之前 PR-B2 仍然卡着。

## C5 "lead 没读 diff" 的基数

每个单元 lead 在第一次派活之后的调用。严格口径：没有输出内容的 `git diff` / `git show` / `git log -p`。宽口径：也没读
任何改过的文件。

| 臂 | 对的单元 | 没读 diff（严格） | 错的单元 | 没读 diff（严格） | p | 没读（宽口径）对 / 错 |
|---|---|---|---|---|---|---|
| ccx2 | 93 | 85（91%） | 7 | 7（100%） | 1.0 | 64 / 4，p = 0.68 |
| builtin | 17 | 0 | 3 | 1 | 0.15 | 0 / 1 |
| builtin2 | 17 | 17 | 3 | 3 | 1.0 | 17 / 3 |

ccx2 的 lead 几乎从不读 diff，对错都一样，所以"没读 diff"分不出那 7 个失败。按计划规则放弃"条件式读 diff"技能变体
（没有证据说明这个信号能区分什么）。

## C6 review 规则"复用代码库里已有的东西"

r5e:2 quota-stop-log-ccx2 没过 hidden test，因为 builder 在 `ccx/quota.py` 里自己写了一份 `QUOTA_HINTS`，而 ccx 判断
额度停止用的是 `ccx/runners.py: QUOTA_HINTS`（词不一样），真正的额度停止可能被记成 `{"by": "unknown"}`。当时的首轮
review（haiku low）没点出来。在同一个树上重放，用现在的 reviewer 简报，以及加一条规则的简报（"(e) 改动新定义了一个常量、
列表或辅助函数，而代码库里已有同用途的……"），haiku low，各 3 次，第 5 轮的干净环境：

| 简报 | 把重复定义报成 [must] | 提到了就算 | 花费 |
|---|---|---|---|
| 现在的 | 0/3 | 2/3（作为 [note]） | $0.028 |
| + 规则 (e) | 3/3 | 3/3 | $0.023 |

这一例能抓到，但单例 n = 3，说明不了它在对的代码上会不会多出 [must]（每条 [must] 都会启动修复轮，而 39 个修复轮里
已有 25 个在"修"对的代码）。放进 reviewer 简报之前，要先用 review_replay 的对照组（通过的 review）确认它不会在那里
新增 [must]。

## C2、C4：脚本已写好，没跑

- **C2** `c2_lead_accept.py plan --dry-run`：ccx2 有 7 个错单元，分属 5 个任务（mem-report、projects-refresh、
  q-killed-spend、q-resume-session、quota-stop-log）；统计误报要用 93 个对的单元，所以 10 个任务都要写测试文件：
  sonnet 估计 $1.20（每个任务一次只看 brief 的会话）。`generate` 让每个会话都在第 5 轮的干净环境里跑（自己的空 hub，
  没有用户的 CLAUDE.md、技能、MCP 或自动记忆），ccx 不会往写测试者的简报里塞共享笔记；简报里真带了笔记的文件会被标出
  （`shared_notes`）且不保留。`score` 不花钱，每个文件在仓库外的临时 cwd 里跑，`CCX_REPO`
  放进 `PYTHONPATH`。
- **C4** 在修复轮回放行上 `c4_must_filter.py --dry-run`：52 个带 [must] 的修复轮（9 个 fail->pass，35 个 pass->pass，
  8 个 fail->fail）；简报中位 1.01 万字符；sonnet 估计 $5.50，haiku $1.83（不算 prompt 缓存，每次 review 另算 2.5 万 token
  读文件）。第 10 个救回（r5e:2 projects-refresh）没有 [must]，任何对 [must] 的过滤都碰不到它：门槛实际是 9/9。门槛按计划里的每个救回算：过滤 review 失败、超时、
  没解析出来、树没建好或被 `--budget` 截掉的，都算没保住，所以只看解析出来的那部分没法通过。计划里
  "约 $0.5"的估计偏低。

## B3 预检（不改 ccx/）

1. **`--ignore-user-config` 和 `$CODEX_HOME/AGENTS.md`。** `codex exec --help`（codex-cli 0.164.0）："Do not load
   `$CODEX_HOME/config.toml`; auth still uses `CODEX_HOME`"。$0 实测：起一个本地 HTTP 服务当模型提供方（`-c model_provider=...
   base_url=http://127.0.0.1:<端口>/v1`），截下 codex 要发出的请求。`CODEX_HOME` 里放一个带标记的 `AGENTS.md`，
   `config.toml` 里放带标记的 `developer_instructions`：不加这个参数，两个标记都在请求里；加了，只剩 AGENTS.md 的标记。
   **AGENTS.md 照样加载**；config.toml（MCP、hooks、memories、插件、developer_instructions）不加载。
2. **Codex sub-agent 怎么拿到共享记忆。** 不是靠 `ccx mem delta` 这个 SessionStart hook：ccx 给每个 sub-agent 设了
   `CCX_ROLE=subagent`，这时 `mem delta` 什么都不输出（`ccx/commands/memory.py`）；每轮的 hook 对 sub-agent 也返回空
   （`CCX_DEPTH` > 0，`ccx/commands/board.py`）。真正的来源是：(a) prompt 里的记忆索引行和简报里的共享笔记
   （`ccx/delegate.py` 的 `_brief_notes`，I6），跟 Codex 配置无关；(b) `ccx sync` 写进 `$CODEX_HOME/AGENTS.md` 的记忆块
   （`ccx/sync.py`），或者快照在外部时用户自己的 AGENTS.md。两者在精简启动下都保留（见 1）。
3. **精简启动必须另外注入什么：** 记忆方面不用再加。要保留 `CODEX_KEEP`（现在只有 `windows.sandbox`；里面没有任何认证
   相关的键，认证仍走 `CODEX_HOME`）。PR-L 仍要加计划里写的测试：lean 模式下简报带着笔记，按档位路由和 `--model`
   路由的 argv 一致。
4. **实测（本机，$0，每种 3 次，维护者真实的 Codex 配置目录：config.toml 87 KB）：**

| 启动方式 | 进程启动到第一次模型请求 | 请求体 | 工具数 |
|---|---|---|---|
| 完整配置 | 3.9-4.3 s | 814 KB | 33 |
| `--ignore-user-config` | 0.8-1.0 s | 790 KB | 31 |
| `--ignore-user-config --disable apps` | 0.8-0.9 s | 55 KB | 9 |

精简启动在第一次请求前省约 3.1 s（不再启动 MCP 服务和 hooks），也去掉了 Codex memories 段（约 20 KB）和两个 MCP 工具。
请求体几乎没变小，因为约 750 KB 是 ChatGPT 应用连接器的工具定义（Gmail、Drive、Canva……），它们跟着登录来，不在
config.toml 里。这些字节每次调用是否按输入 token 计费（可能被缓存）这里没测：B3 的 token 门槛仍要 10 次的微基准。
给写代码的 sub-agent 加 `--disable apps` 是另一个值得进同一个微基准的新选项，和其他提速开关一样默认关。
