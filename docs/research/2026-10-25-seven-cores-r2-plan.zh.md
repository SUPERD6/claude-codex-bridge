# 七个核心第 2 轮：分工合作是否比单个模型更好、更省（方案）

[English](2026-10-25-seven-cores-r2-plan.md) · 中文 · 2026-10-25 · 写于任何真跑之前

第 1 轮报告：[2026-10-24-seven-cores-ab.zh.md](2026-10-24-seven-cores-ab.zh.md)。本轮测核心 4（分工更好）、5（省、高效）、6（越用越准）、7（不丢不乱可控），用第 1 轮之后合并的新默认值：`tradeoff = save`、验收没过会升档（#34）、审查用另一家最便宜一档并逐条对照要求（#31）、弱证据自动补审（#41/#65）、被杀运行记账（#54）、`--to auto` 提速（#57）、子智能体带共享记忆（#36）。

## 0. 通用规则

- 脚本：`scripts/eval/r2.py`（任务在 `scripts/eval/tasks_r2.py`，复用第 1 轮的 `common.py`、`seven_ab.py` 的统计函数）。
- **每个单元一个全新临时 hub**（`CCX_HUB`）：`ab_self_rate = 0`；DeepSeek 上限调到 $1000（用户已定暂不设上限，但所有花费照样记账）；Codex 的 tiers T2–T4 都改成 `gpt-6-luna low`，路由里 `gpt-6.1-sol`、`gpt-6-astra` 标记为不可用；`CCX_NO_QUOTA_PROBE=1`（每个新 hub 都会重新探测 Claude 额度，会给每个单元加同样的噪声）。
- 所有 `ccx run` 带 `--no-ab`，标签 `eval-r2:<tag>:<组>:<轮>:<任务>:<臂>`；`ccx way` 本轮新加 `--label`，让构建步骤也带 `eval-` 标签。
- **已知偏差**：路由只能按模型标记不可用，不能按推理强度，所以自动路由的臂仍可能选到 `gpt-6-luna high`。出现就照报次数。
- 做没做对由隐藏验收测试决定（智能体看不到），结果用 `ccx verify` 记进该单元的 hub。
- 每轮内任务顺序和臂的先后随机（种子 26）。**每组都在同一版代码上重跑自己的基线臂，报告里不跨轮直接和第 1 轮比较。**
- 花费 = 账本里 API 等价美元（Codex、Claude 按 API 价，DeepSeek 是真钱）。脚本在每个单元前累加全部结果，**达到 $6 就停**；超过 $6 要用户在聊天里点头。每组跑完报一次累计花费。
- 统计：独立实验单元是任务（同一任务各轮的配对差先取平均）；做对用精确 McNemar，花费/token/用时用配对差中位数、自助法 95% 区间和符号检验；主检验（4-C on vs off、4-B single vs way、single vs draft 的做对率）做 Holm 校正。n 小的组只作描述，不下“显著”结论。负结果照写。
- 时间：全部在 10/31 前跑完（11/1–11/7 是 J0 后测窗口，不真跑）。脱敏数据（不含路径、会话 id）放 `docs/research/data/`。

## 1. 任务

- **陷阱任务（10 个，`TRAPS`）**：中等任务，说明里写了几条要求，可见测试只查主路径，隐藏测试查容易漏的那条（四舍五入方式、不改输入、顺序、边界、错误情况）。`inventory` 沿用第 1 轮（luna low 在第 1 轮 6/6 次都错在同一处），新加 merge、version、wrap、groupby、cart（两文件、half-up 取整）、ini、coerce（邮编前导零）、bytes、retry。`tests/test_eval_tasks.py` 检查每个任务起始代码过不了隐藏测试、参考解能过。
- **小任务**：第 1 轮的 slugify、duration、intervals、cli-json、csvstats、lru。
- **PAR10**：10 个互不相关的小模块（m01–m10），每个一个函数、一个隐藏测试，并要求各写 `tests/test_mNN.py`。
- **QUEUE**：4 块有依赖的活（b 用 a，c 用 b，d 独立）。

## 2. 各组设计（按优先级）

| # | 组 | 臂 | 任务 × 轮 | 判定规则（事先定） | 预估花费 |
|---|---|---|---|---|---|
| 1 | 4-A `ccx way` 冒烟 | visible、critical（`--yes`） | inventory、cart、merge × 各 1 次 = 6 次 | 每次检查：plan 至少 1 条 `[step]` 和 1 条 `[accept]`；accept 判定解析成 pass/issues；critical 的 `PICK: A/B` 解析成功。任何一项不守格式 → 在 `ccx/ways.py` 的解析部分加宽松解析，再补跑失败的那几次（单独标注） | ~$0.6 |
| 2 | 筛选 | luna low 单独做 | 10 个陷阱 × 2 | 不计入任何对比；只用来挑 4-B 的任务：错得最多的 ≥7 个（不足 7 个就取错得最多的 7 个，并照写） | ~$0.05 |
| 3 | 4-C 审查重测 | off / on / auto（都是 luna low、不升档） | 10 陷阱 + slugify、duration、lru = 13 × 3 轮 | 主检验：on vs off 的做对率（McNemar，39 对，Holm）。只有 on 更高且 Holm p < 0.05 才说“审查让结果更对”。另报：花费比、第一次审查判 issues 的次数、修一轮把错变对的次数、“ccx 说通过但隐藏测试失败”的次数；auto 臂报触发了几次补审 | ~$0.8 |
| 4 | 4-B 分工 vs 单个模型 | single（luna low 直接做）/ way（`ccx way --risk visible`：claude 规划、codex 实现、规划者验收，最多修一轮）/ draft（claude sonnet 出分工草案 → codex luna low 只读审草案 → codex luna low 按草案和审查意见实现，不再验收） | 筛出的 ≥7 个任务 × 2 轮 | 主检验：single vs way、single vs draft 做对率（McNemar，Holm）。“分工更好”要 Holm p < 0.05 且方向为正；否则只报方向和区间。另报返工率（way 修一轮的次数）、总 token、总花费（比值 + 任务层符号检验）、用时。**偏差说明**：任务是按“便宜模型会错”挑的，single 臂在正式跑里会向均值回归（看起来比筛选时好），这对分工臂不利，不是有利 | ~$2.1 |
| 5 | 并行规模 | p1（一个 Codex 一次做 10 个，`--no-subagents`）/ p3、p10（`ccx batch` 3、10 路并行，每路一个 worktree，跑完逐个合并回来）/ native（一个 Codex，`--parallel`：明确要求用自带子智能体并行） | PAR10 × 2 轮 | 只作描述（n = 2）：墙钟时间、总 token、总花费、10 个里做对几个、合并冲突数。用 p1/p3/p10 拟合 token = a + b × 运行数，外推 100 路时启动开销（b × 100）占总 token 的比例。“更快”= 两轮都更快；“更省”= 两轮都更少 | ~$0.15 |
| 6 | 4-H 自带子智能体开/关 | Codex：p1 vs native（同上）；Claude haiku low：c_off（`--no-subagents`）vs c_on（`--parallel`） | PAR10 × 2 轮 | 记录到底开没开（Codex 子会话文件数、Claude `subagents/*.jsonl` 数）；比花费、用时、做对（描述） | ~$0.05 |
| 7 | (b') 路由 | fixed（claude sonnet medium，不升档）/ warm（`--to auto`，hub 里是用户默认 hub 的 routing-state 的**拷贝**，开跑前记 SHA-256）/ cold（`--to auto`，空 hub） | 12 个（4 小 + csvstats、lru + 前 6 个陷阱）× 1 轮 | 做对率（McNemar）、花费比、用时、选了哪些档位、升档次数，“验收过了、隐藏测试失败”的次数。n = 12 只作描述 | ~$0.8 |
| 8 | 4-D 按难度分层 | `ccx route`（不调模型）5 / 15 / 30 分钟 × 3 个说明 × warm/cold | — | warm 下 3 个说明里至少 2 个在三档难度上选出 ≥2 个不同档位，算“分层有效” | $0 |
| 9 | 越用越准 | 一个持续学习的 hub（从同一份拷贝开始）：同 12 个任务跑两遍（phase1、phase2），每次用隐藏测试 `ccx verify`；冻结臂 = 第 7 组的 warm 臂（同一份状态、同一版代码、每个单元重新拷贝） | 12 × 2 | phase2（继续学习）vs 冻结：Brier（路由预测成功率 vs 隐藏结果）和做对率。Brier 更低且做对率不更低才说“越用越准”；n = 12，只作描述 | ~$0.4 |
| 10 | F11 + 4-I | F11：claude sonnet + `--parallel --budget 0.0001`，看 Claude 侧花费上限是否真的触发；4-I：QUEUE 用 `ccx q run`，有一块做完就杀掉进程树，再 `ccx q resume` | 各 1 次 | F11：`kind = over_budget` 且确实开了子智能体才算触发；4-I：resume 后 4 块都 done、隐藏测试通过、已做完的块没被重做 | ~$0.1 |

合计预估约 $5.0；按优先级跑，到 $6 停下问用户。

## 3. 不在本轮

- Gemini（本机没装）；DeepSeek 当组长（ccx-vendors 会话在测）。
- 长对话里的主会话省多少（第 1 轮只做了外推；本轮也不测）。
- H5 共享记忆写入（要写用户真实的 hub）。

## 4. 变更记录（跑之前的设计改动，按时间）

- **10/25，第 1 组跑完、筛选之后**：第一批 10 个陷阱任务 luna low 19/20 做对，太容易。又写了两批：`TRAPS2`（陷阱放在要配合的现有代码里：重复实现、缓存、舍入方式不对的旧工具函数、子类覆盖、bool 是 int、先分页后过滤，8 个 + inventory）18 次对 16 次（只错 inventory 2/2）；`COMPOUND`（照 inventory 的结构：3 条编号要求分布在 3 个文件，4 个）8/8 对。三批合计 luna low 49 次对 47 次，只有 inventory 会错。
- 因此：4-B 按第 2 节事先写好的后备规则，用 `screen2` 里错得最多的 7 个（inventory + dupparse、cache、rounding、exporter、tags、config）；4-C 的任务改为 `TRAPS2` 的 9 个 + 第一批里 3 个作对照（merge、version、ini），共 12 × 3 轮；(b') 和“越用越准”的 12 个任务里的 6 个陷阱改为 `TRAPS2` 的前 6 个。可以预期这几组的做对率接近天花板，主要看花费和用时；这一点在报告里写明，不当作“分工没用”的一般结论。
- 4-A 6/6 格式都对，没有改 `ccx/ways.py` 的解析。
