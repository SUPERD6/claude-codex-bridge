# 设计说明（通用版）

[English](DESIGN.md) · 中文

本文档只描述**机制**，不包含任何个人路径或个人数据。安装时由 `ccx init --hub <path>` 指定你自己的 hub。

## 分层

| 层 | 内容 | 位置 |
|---|---|---|
| 工具层 | ccx 代码、默认配置、四个技能（agent-delegate、task-routing、task-split、task-checkpoint）、测试 | 本仓库 |
| 个人层（hub） | 你的技能、MCP 登记表、个人记忆、账本、学到的参数、设置、改进记录 | `ccx init --hub` 指定的目录（默认 `~/.ccx-hub`） |
| 项目层 | 项目背景 `context.md`、项目日志 `journal.jsonl`、`inbox/`、断点任务 `tasks/` | 每个项目的 `.ccx/` |

原则：**机制属于项目，内容属于个人**。任何人安装后都能得到相同的机制；具体内容只在自己的电脑上。

## 组成

1. **委派**（`ccx/delegate.py`、`ccx/runners.py`）：以无界面模式调用另一个工具：
   - Codex：`codex exec --json`；
   - Claude Code：`claude -p --output-format stream-json --verbose`；
   - Gemini CLI：`gemini -p -o stream-json`。

   子智能体必须按 JSON schema 交回结果，主智能体只读这一段压缩结果，完整日志留在硬盘上。
   - 会话 ID 一出现就写盘，崩溃或超时后可以 `ccx resume`。
   - 失败分为 ok / quota / auth / timeout / error 五类：额度用完时换另一个智能体重试一次；`blocked` 或 `failed` 时在同一会话里升一档。
   - “模型来源”（provider）＝同一个工具换一个 API，比如 DeepSeek 通过 Claude Code，或通过 Codex（用 `-c model_providers.<id>` 覆盖），密钥只从环境变量读取。
   - DeepSeek 自成一家，不管走哪条路：`dsh`（DeepSeek Harness：`dsh --profile headless --patch <run>/dsh.patch.yml --json -`，模型写在 patch 里，沙箱用 `DSH_PERMISSION_MODE`）、`deepseek`、`deepseek-codex` 的厂商都是 deepseek，所以审查和换边把它们当成 Claude、Codex 之外的“另一家”，`ccx report` 把它们算成一条 DeepSeek 线。
   - 按 token 付费的智能体（provider 和 `dsh`）有 `daily_usd` 上限；没有价格的模型拒绝运行；除非你在配置里指定，它们不会被选为额度用完时的接班者或审查者。
2. **选模型**（技能 task-routing，`ccx/learn.py` 接入）：
   - 按 5 项打分得到难度 b，用 IRT 公式 P = 1/(1+e^(−1.2(θ−b))) 算每个“智能体:模型:强度”的成功率。
   - 按“每成功一次的花费”和级联规则挑出起点和升级路线。
   - 每次结果按 Elo 方式更新 θ，并按实际花费修正成本系数。
   - 省钱↔快的旋钮 k∈[0,1]：成功率门槛 = 0.70 + 0.20k。
3. **拆任务**（技能 task-split）：
   - 按 METR 时间跨度 p(t) = 1/(1+(t/h50)^0.86)，每块定在 80% 成功率的长度。
   - 只在能检查的地方切；先分 3–5 个里程碑，失败了再往下拆（ADaPT）。
   - h50 按实际结果在线校准。
4. **断点续跑**（技能 task-checkpoint）：
   - 状态记录：`plan.json`、只追加且每次落盘的 `progress.jsonl`、心跳锁。
   - 代码快照：`git stash create` 存到 `refs/checkpoints/`，不碰当前分支。
   - `ccx run --task --step` 会自动登记开始、会话 ID 和失败原因；`ccx verify` 把这一步标成完成。
5. **增量记忆**（`ccx/memory.py`、`ccx/project.py`）：快照 + 追加日志 + 每个智能体一个游标。
   - 两边的 SessionStart hook 只输出对方新增、自己没见过的条目，还会提示未完成的任务；没有新内容就什么都不输出。
   - 子智能体（不论哪个工具）不收增量；它的任务说明里附上最多 4 条和任务有共同词的记忆（`memory.for_brief`，最多约 300 token），没有共同词就不附。
   - 项目层（`.ccx/`）同理；用户交给一边的文件或邮件，经 `ccx inbox` 存档，另一边只多读一行。
6. **同步**（`ccx/sync.py`）：
   - 技能只保留一份原件，另一边用目录链接（Windows 用 junction，其他系统用 symlink）；MCP 通过各自官方 CLI 注册。
   - 所有改动默认先预演，并自动备份；`ccx uninstall` 只删 ccx 自己加的东西。
   - 已有共享配置时用外部模式接入，不重复造。
7. **记账与看板**（`ccx/ledger.py`、`ccx/usage.py`、`ccx/report.py`）：
   - token 统一成 4 类（新输入、写缓存、读缓存、输出），按价格表折算成 API 等价美元（AE$）。
   - 主智能体自己的用量从工具自带的会话记录里读，并排除子智能体会话。
   - 节省有两个来源：每个任务的估算（附置信区间），以及约 10% 的 A/B 实测。
   - `ccx report` 生成离线单文件看板；`--publish` 提交到私有仓库。

## 自动校准的回路

```
ccx run（按打分选模型）→ 子智能体执行 → 结果写进账本
   → 明确失败 / 子智能体自己检查过的成功：马上记回 task-routing（θ、成本系数）和 task-split（h50）
   → 主智能体 ccx verify：以它为准；和之前的自动记录不一致时纠正，一致时不重复记
   → 下一次选模型、拆任务用的就是更新后的参数（两边共用同一份）
```

价格表超过 30 天没更新会提醒；Gemini 用模型别名，新型号不用改配置。

## 验收

在你自己的电脑上：

| # | 检查 | 怎么做 |
|---|---|---|
| A1 | 体检 | `ccx doctor` 全部 ok 或说明了原因 |
| A2 | Claude → Codex 委派 | `ccx selftest --agents codex`，再在 Claude Code 里真派一个小任务 |
| A3 | Codex → Claude 委派 | `ccx selftest --agents claude`，再在 Codex 里真派一个小任务 |
| A4 | 增量记忆只推新增 | 一边 `ccx mem add`，另一边新开会话只看到这一条 |
| A5 | 项目层两边可见 | `ccx inbox "…" --file 邮件.eml`，另一边新会话看到一行 |
| A6 | 技能两边可用 | 两边都能列出同一个技能 |
| A7 | MCP 两边可用 | 两边都能列出同一个 MCP 服务器 |
| A8 | 看板 | `ccx report` 打开后能看到主/子、Claude/Codex 的 token 和 AE$ |
| A9 | 断点续跑 | 跑一个 `--task --step` 的任务时关掉窗口，`ccx resume` 接着做 |
| A10 | 额度回退 | 用 `--to` 指向额度已用完的一边，自动换到另一边 |
