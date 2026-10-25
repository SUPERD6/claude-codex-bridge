<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="relayline（命令 ccx）：几个编码智能体互为主智能体和子智能体；Claude Code、Codex、Gemini CLI；一次真实运行：选了 Codex luna/low，一次完成，已验收，$0.0023" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/relayline/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/relayline/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/relayline/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/relayline"></a>
</p>

<p align="center"><a href="README.md">English</a> · 中文 · <a href="https://superd6.github.io/relayline/zh/">网站</a></p>

# relayline

**让几个编码智能体互相当主智能体和子智能体：共享记忆、按难度分工、每块活有人验收、花了多少有账可查。**
Claude Code 和 Codex 谁当主都行；Gemini CLI 和 DeepSeek（经 Claude Code、经 Codex，或 DeepSeek 自己的 DeepSeek Harness）也能接活，几家较新的 API（Kimi、GLM、Qwen、OpenRouter）也能经 Claude Code 接活。命令是 `ccx`，只用 Python 标准库。

```bash
pipx install git+https://github.com/SUPERD6/relayline
ccx setup                    # 向导：每一步都说明，改东西前先问
ccx run --to codex --mode read "用三行总结 README.md"
```

<p align="center"><img alt="演示动画：ccx route 选出 codex:gpt-6.1-sol:medium，ccx run 一次完成并由 ccx 重跑验收命令，ccx verify 记下结论" src="docs/assets/demo.svg" width="100%"></p>

> **仍在开发中（v0.4，2026 年 10 月）。** 每天在一台 Windows 电脑上真实使用，两个方向、终端和桌面端都跑通了。
> - **省没省钱，第一批实测结论是“看情况”**（见下一节）：只在主智能体信 ccx 的验收结果时，小任务才省；一周的正式对比（`ccx trial`）还在收集。选模型的初始参数还没校准。
> - **只用模拟命令行测过的：** 待办队列（`ccx q`）、长期岗位、worktree 和 `ccx batch`、真实额度用完时换另一边。Gemini CLI 从没真跑过。macOS 和 Linux 只在 CI 里跑过。
> - **还没做的：** `ccx stop`、更完整的共享记忆（见 [STATUS](docs/STATUS.zh.md)“接下来”）。网站还没发布。
>
> 旧记录（CHANGELOG、docs/STATUS）里早期的提交号指的是公开前压缩掉的私有历史。哪些功能验证过、怎么验证的，见 [STATUS](docs/STATUS.zh.md)。

## 七件事

| | 做什么 | 现在的状态 |
|---|---|---|
| **1. 互为主子** | Claude Code 当主、Codex 干活，或者反过来；Gemini CLI、DeepSeek（经 Claude Code、经 Codex，或 DeepSeek Harness `dsh`）可以接活。每家一个适配器，`ccx agents` 列出每家能做什么、测过哪个版本、官方还是社区。 | 两个方向真机跑通；DeepSeek 经 Claude Code 和经 Codex 真跑过；Gemini 和 `dsh` 只有模拟测试 |
| **2. 两个模型直接对话** | `ccx ask` 让另一家快速给个第二意见；`ccx resume` 在同一个子会话里追问；`ccx send` 把消息发进正在运行的 Codex 会话；`ccx discuss` 让 2–3 家不同厂商的模型把选错代价高的决定讨论清楚（出方案、挑错、裁判，最多 3 轮），在 `ccx ui` 里显示成对话。 | 前三个真机可用；`ccx discuss` 真跑过两次，先两家、后三家（Codex、Claude、DeepSeek；[记录](docs/research/2026-10-25-discuss-three-vendors.zh.md)） |
| **3. 共享记忆** | 个人层（你的 hub：记忆、技能、MCP、账本）和项目层（`.ccx/`：背景、日志、交接、断点）。开局 hook 只推对方新写的几行；`ccx handoff` 换主智能体接力，`ccx fresh` 把长对话交给同一工具的新对话。 | 真机可用；更完整的共享记忆在做 |
| **4. 分工合作** | 5 个问题打出难度 → 选智能体、模型、强度并给出成功率；算下来自己做更划算或该先拆，就直接说不派。`ccx batch` / `ccx q` 并行，长任务断了 `ccx task resume` 接着做。 | 选模型真机可用，但先验没校准；队列只有模拟测试 |
| **5. 省和高效** | 子智能体精简启动；`ccx lead` 看主智能体每轮重读多少（`--breakdown` 拆开看、`--cache` 找缓存断在哪、`--suggest` 给主智能体自己的档位建议）；`ccx sum` 只把大段输出里要紧的给主智能体。 | 工具都在；省多少取决于主智能体怎么用（见实测） |
| **6. 不掉质量** | ccx 自己重跑验收命令（`--check`）；另一家的模型独立审查改动（`--review`）；每次记对错（`ccx verify --ok 0 --reason wrong`），没人判的 12 小时后按证据记“大概对/错”；`ccx trial` 做一周正式对比。 | 真机可用；自动结论还没被抽查过 |
| **7. 不丢可控** | 改配置先预演、真改前备份；`ccx undo` 撤回某次运行的改动；`--mode read` / `--worktree` 不动工作区；子智能体不能再派子智能体；`ccx ui` 在本机只读地显示谁在干什么、什么等你拍板。 | 真机可用；`ccx ui` 只在 Edge 里开过 |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture-dark.svg">
  <img alt="架构图：Claude Code、Codex、Gemini CLI 都连到 ccx，谁当主都可以把简报交给另一家在后台跑、交回 JSON；ccx 选模型、重跑验收、请另一家审查、记对错和花费；下面是个人层（hub：记忆、技能、MCP、账本）、项目层（.ccx：背景、日志、交接、断点、撤回快照）和本机只读页面 ccx ui" src="docs/assets/architecture-light.svg" width="100%">
</picture>

## 实测（2026-10-24，ccx 0.4.0）

全部来自真机上的真实运行，方法、原始表格和局限见[实测报告](docs/research/2026-10-24-h11-e8-f9-measurements.zh.md)。**有利的和不利的都列在这里。**

| 问题 | 结果 | 把握 |
|---|---|---|
| 小任务派给 Codex，主智能体省没省？（8 个小 Python 任务，同一任务自己做 / 派出去配对） | **看主智能体信不信 ccx 的验收结果。** sonnet 当主：每个任务少 1 次请求（3 → 2，6/6，p = 0.031），总花费持平。haiku 当主：派完还会自己再跑一遍测试，请求数不变，总花费反而多（中位数 $0.0024 → $0.0056，p = 0.008）。两种都**慢约 16–18 秒**。做对率两边都是 14/14。 | 对“几分钟的小任务”有把握；样本小 |
| 换到真实的长对话主智能体会怎样？ | 少 1 次请求 ≈ 少读约 22 万 token ≈ 按 Opus 缓存读价每个小任务**约省 $0.04，多等约 16 秒**；主智能体不省请求时，只是多花约 $0.003。 | **外推，不是测量** |
| 钱到底花在哪？（本机真实会话，7 天） | Claude 主智能体每次请求中位数 **35.2 万 token、$0.11**，缓存读占 99%；同期 ccx 子任务一共 $0.42。所以最该省的是主智能体每轮重读的上下文。 | 读数，有把握 |
| Codex 自带的子智能体会被用上吗？ | gpt-6-luna low 上 **5/5 次都没启动**，连明确要求的那次也没有；开 / 关的花费和用时差别在噪声以内。更高档的模型没测。 | 只对 luna low 有把握 |
| 只凭交接，接手方能说对“做到哪、下一步”吗？ | 受控场景 3/3 说对（含中途被杀）；真实长会话第一次说错（计划读成了过期状态），修好后说对。 | 真实会话只有 1 个 |
| 精简启动一个 Claude 子智能体 | 每次请求的固定上下文 4.6 万 → **1.36 万** token | 单次实测 |
| 记账和 Codex 自己的周额度对照 | 每 1% 额度折算 **$2.8–4.4**，4 个时段都稳定 | 4 个时段 |
| 测试 | 268 个，Linux、Windows、macOS × Python 3.11–3.13 | 只证明逻辑，不证明真机 |

设计说明：[docs/DESIGN.zh.md](docs/DESIGN.zh.md) · 进度：[docs/STATUS.zh.md](docs/STATUS.zh.md) · 决策记录：[docs/DECISIONS.md](docs/DECISIONS.md) · 变更：[CHANGELOG.md](CHANGELOG.md)

**和同名项目不是一个东西：** relayline 原名 `claude-codex-bridge`，但不是 [CCB](https://github.com/SeemSeam/claude_codex_bridge)（`SeemSeam/claude_codex_bridge`，同时看、同时指挥多个代理的可见终端工作区），也不是 OpenAI 官方的 [codex-plugin-cc](https://github.com/openai/codex-plugin-cc)（只把活从 Claude Code 交给 Codex）。见[同类项目对比](#同类项目对比)。

## 实时看：`ccx ui`

`ccx ui` 在本机打开一个只读页面：有什么等你处理（红框 = 要你拍板，橙框 = 要你 review）、谁在干什么（每个智能体一列，新加的自动多一列）、额度按现在的速度够不够。点任何一块，右边显示原因、依据和可以复制的 `ccx` 命令。它只读 ccx 和各工具本来就写下的文件，不调用任何模型；只监听 127.0.0.1，页面关掉一分钟后自己退出。`ccx ui --export 快照.html` 生成静态副本；`ccx config set ui.lang zh|en` 选语言。

<img alt="ccx ui 总览：等你处理的 9 件事、现在的主智能体、两个项目和额度预测（演示数据）" src="docs/assets/ui/overview-zh.png" width="100%">

<img alt="ccx ui 任务页：一件任务画成组织图，每个干活的一列，右边是为什么要你拍板（演示数据）" src="docs/assets/ui/task-zh.png" width="100%">

<details><summary>英文界面、深色</summary>

<img alt="ccx ui in English, dark theme: the same task page (demo data)" src="docs/assets/ui/task-en-dark.png" width="100%">

</details>

截图是用 `python scripts/ui_demo.py --plain` 生成的：临时 hub、模拟命令行跑出的真实 ccx 运行，不含任何人的真实工作。

## 它怎么工作（一个例子）

你在 Claude Code 里说："把 `loader.py` 支持自定义分隔符，并补测试。"

1. Claude（主）按 5 项给任务打分（改 2 个文件、单模块、目标清楚、风险低、有现成写法），写一段不到 200 字的简报，只写目标、要看的文件、怎样算完成。
2. 执行 `ccx run --from claude --files 2 --coupling one --clarity goal "…"`。ccx 调用 task-routing 技能，算出每个“智能体:模型:强度”的成功率和每次成功的花费，挑出 `codex:gpt-6.1-sol:medium`。如果算下来自己做更划算、或者应该先拆开，就直接告诉主智能体，不派。
3. ccx 在后台调用 `codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" …`。会话 ID 一出现就存盘。Codex 自己读文件、改代码、跑测试，这部分 token 花的是 Codex 账号的额度。
4. Codex 必须按 JSON schema 回报：`status / summary / files_changed / verification / …`。Claude 只读这一小段，再自己看一眼 `git diff`，确认测试真的跑过，然后 `ccx verify <run_id> --ok 1`。
5. 如果 Codex 回报 `blocked`，ccx 会在**同一个 Codex 会话**里升一档（high）继续，不用重新喂背景。如果 Codex 额度用完，自动换 Claude 做；超时或崩溃，`ccx resume <run_id>` 接着做。想让它停：`ccx stop <run_id>` 结束子智能体和它开的所有进程，之后 `ccx resume` 能接上。
6. 每次运行都写进账本，结果自动记回 task-routing / task-split，下次选得更准。`ccx report` 生成看板网页：谁花了多少 token、什么类型的 token、额度用了多少、估计省了多少。

反过来，在 Codex 里用同样的命令加 `--to claude`，就是 Codex 当主、Claude Code 当子。
能不能用要看 Codex 的沙箱：ccx 要把运行记录写进 hub，子智能体要联网。`ccx doctor` 会检查这一点（“Codex as lead (sandbox)”那一行）。在 Windows 上真跑只有 `danger-full-access` 能用（codex-cli 0.164）：`workspace-write` 下命令用一个单独的沙箱账号运行，在里面启动的 Claude 子智能体每次改文件都被拒，把 hub 和 `~/.claude` 加进可写目录、打开网络也一样。**安全提醒：**完全访问意味着 Codex 组长跑的每条命令都带着你的全部权限、没有沙箱（你的文件、网络、凭据）；只在你愿意让它像你本人一样操作电脑时用。更窄的做法（按 Codex 官方文档可行，**还没真跑验证**）：保持 `workspace-write`，用一条 Codex 规则只让 ccx 派活的命令（`run`、`ask`、`resume`、`discuss`）在沙箱外运行：`ccx doctor --codex-rule >> ~/.codex/rules/ccx.rules`（Codex 的 rules 还是实验功能；装上后 `ccx doctor` 显示 Unknown 而不是 ok）。

**子智能体知道你和主智能体聊过什么吗？** 不直接知道：把一长段对话塞给每个子智能体太贵，而且 Claude 和 Codex 本来就不能共享上下文。子智能体拿到的是简报（主智能体浓缩的结论）、项目背景、共享记忆和原文件。连续性靠**子会话**：同一个对话、同一个目录、同一个智能体，1 小时内的下一个任务会自动接回上一个子会话，它记得已经读过、做过什么（`--new` 强制新开）。从 Claude Code 派给 Claude 子智能体时，还可以用 `--fork` 让它从你整段对话的副本开始。

## 共享的东西放在哪

全部放在你自己的 hub 文件夹里（第一次运行 `ccx init --hub <路径>` 指定，记在本机 `~/.ccx/config.toml`；不指定就用 `~/.ccx-hub`；也可以用环境变量 `CCX_HUB` 临时改）。仓库里不放任何个人内容：

| 内容 | 位置 | 两边怎么读到 |
|---|---|---|
| 记忆快照"1" | `memory/MEMORY.md` | Claude：`~/.claude/CLAUDE.md` 里 `@导入`；Codex：`AGENTS.md` 里的托管块 |
| 记忆增量"+2" | `memory/journal.jsonl` + `ccx/cursors.json` | 两边的 SessionStart hook 运行 `ccx mem delta --as <自己>`，只推送对方新增、自己没见过的条目 |
| skill | 一个 skill 只放一份（Codex 的 `skills/`、Claude 的 `skills/` 或 `hub/skills/`） | 另一边用目录链接（junction）指向它 |
| MCP | `mcp/servers.json` | `ccx sync` 用 `claude mcp add-json` / `codex mcp add` 分别注册 |
| 项目背景 | `<项目>/.ccx/context.md` | 每个子任务的简报都会指向它，子智能体开局自己读 |
| 运行记录/账本 | `ccx/runs/`、`ccx/ledger.jsonl` | `ccx show` / `ccx stats` / `ccx report` |
| 学到的参数 | `ccx/routing-state.json`、`ccx/split-state.json` | 两边共用，每次验收后自动更新 |
| 设置 | `ccx/settings.toml` | `ccx config set ...` |
| 待办队列 | `<项目>/.ccx/queue/` | `ccx q tree`；开局会提示还没做完的活 |

**什么记忆放哪里。** 用户提出的长期要求（比如“每次修改都提交”）写进用户自己的共用规则文件，要等用户同意才写。项目里的事实用 `ccx mem add --project` 记下（用 `--source` 写明从哪来的）。不再成立的记忆要替换（`--supersedes N`），不要和新的并排留着；30 天没人核对的会标成“待核对”（`ccx mem stale`、`ccx mem verify N`）；更早的记忆用 `ccx mem search` 找；开局时新增的记忆最多带约 600 token。两个工具各自的自动记忆归各自所有，ccx 不会把一边的复制到另一边。

## 安装

需要 Python 3.11+（只用标准库），并且 `codex` 和 `claude` 两个 CLI 都已登录（`gemini` 可选）。

**不克隆仓库**（技能和配置都打在包里）：

```bash
pipx install git+https://github.com/SUPERD6/relayline
ccx init --hub <你的个人hub路径>
ccx doctor
```

**从克隆的仓库装**（要改代码，或者想让 `git pull` 直接升级接进 hub 的技能）：

```powershell
git clone https://github.com/SUPERD6/relayline
cd relayline
.\install.ps1 -Hub <你的个人hub路径>     # Windows；macOS/Linux：./install.sh <hub路径>
```

安装脚本会：有 pipx 就 `pipx install --editable .`（之后直接用 `ccx`），没有就提示把 `bin\` 加进 PATH；然后 `ccx init`（只新建，不改已有文件）和 `ccx doctor`（体检：CLI、登录、接线，不确定的写 Unknown）。接着运行向导 `ccx setup`（每一步都说明、改东西前先问），或者一步步来：

```powershell
ccx sync            # 预演：列出将要做的改动，不改任何文件
ccx sync --apply    # 真改；被改的文件自动备份为 *.ccx-backup-YYYYMMDD
ccx selftest        # 每个已安装的智能体用最便宜的模型跑一个小任务：登录、解析、启动开销一次看清
```

之后在 Codex 里打开 `/hooks`，信任 "ccx: shared memory delta" 这个 hook（只需一次）。

已经有自己的共享配置（比如一个 AGENTS.md 两边都读、自己的同步脚本）？用 `ccx init --hub <路径> --snapshot AGENTS.md --external-sync "<你的同步命令>"` 接进去，ccx 不再改两边的说明文件，技能和 MCP 交给你的脚本。

## 常用命令

```text
ccx run "任务" --from claude --files 3 --coupling cross --clarity goal   # 按打分自动选（推荐）
ccx run "任务" --model gpt-6.1-sol --effort high                       # 自己指定模型和强度
ccx run "任务" --tier T2                                               # 按固定分级
ccx run "任务" --check "pytest -q" --review on                        # ccx 自己重跑验收；另一家的模型独立审查改动
     [--mode read] [--check CMD] [--review auto|on|off] [--worktree] [--task <id> --step <n>] [--minutes 60] [--no-fallback] [--force] [--no-ab]
ccx verify <run_id> --ok 1|0 [--note "说明"]  # 主智能体验收结论：校准选模型/拆分，并关掉 checkpoint 这一步
ccx resume <run_id> "追问"          # 在同一个子会话里继续；中断后也用它接着做
ccx stop <run_id>                   # 停掉正在跑的委派（连同它开的所有进程）；resume 能接上
ccx task status | resume <任务>     # 长任务：一条命令接着做中断的那一步（额度用完时自动换另一边）
ccx handoff --by claude --to codex "做完了什么/定了什么/接下来做什么" [--next "任务5" ...]   # 换主智能体接力
ccx lead                                     # 主会话每一轮要重读多少 token、花多少钱
ccx lead --breakdown | --cache | --suggest   # 每轮重读的东西逐项拆开 / 缓存断在哪 / 主智能体自己该用哪档
ccx sum -- python -m pytest -q               # 跑命令，只给主智能体看要紧的（测试只看失败），完整输出留在 .ccx/sum/
ccx fresh [--launch]                         # 长对话交给同一工具的新对话：从这段对话的文件生成交接
ccx propose --lead claude:opus:high --minutes 30 "…"  # 提议派活前：估算、一句话怎么说、记一笔（--no ID、--stats）
ccx trial start | stop | report              # 一周正式对比：一半可派的活主智能体自己做，一半派出去，同样口径量
ccx trial tag --arm native --session ID      # 把用了 Claude Code 自带子智能体 / workflow 的对话记为第三组
ccx agents                                   # 每家命令行：厂商、能做什么、测过的版本、官方还是社区
ccx way "任务" --risk low|visible|critical   # 按风险选合作方式：一家做 / 规划+实现+验收 / 两版比较（--yes）
ccx way --stats [--include-evals]           # 每类活每家（分档位）的一次做对率和返工率，默认不算评测
ccx discuss "问题" [--dry-run]              # 2-3 家不同厂商讨论选错代价高的决定：出方案、挑错、裁判
ccx verify <run_id> --ok 0 --reason wrong     # 你的判断（没人判断的，12 小时后按证据自动记“大概率对/错”）
ccx verify --sample 5                        # 抽查本周 5 个自动判定：看改动，回答对 / 错
ccx handoff --from-transcript codex --to claude   # 原主智能体写不了（额度用完）：从它的会话文件生成交接
                                                  # （先用代码提取；格式认不出时交给自动选出的子智能体整理，--no-model 不用模型）
ccx undo <run_id> [--apply] [--wrong]   # 撤回某次可写运行改动的文件（新建的挪到一边）；--wrong 同时记成做错
ccx ask "问题"                       # 让另一个模型快速给个第二意见（只读、低强度）
ccx archive [--apply] | --restore <run>   # 归档用完的子会话（2 小时后也会自动归档）
ccx batch plan.json                 # 互不依赖的任务并行；多个写任务自动分到不同 worktree
ccx route --files 3 --coupling cross ... [--lead claude:opus:high --ctx-files 日志.txt]  # 只看推荐；加 --lead 还会比较自己做 vs 派出去
ccx plan size --minutes 240 --rung codex:gpt-6.1-sol:medium   # 大任务拆几块（task-split）
ccx show <run_id> [--full]          # 默认只显示压缩结果
ccx stats [--summary]               # 按 agent×级别统计；--summary 给出花费、省了多少、缓存占比
ccx report [--days 30] [--publish]  # 看板网页（离线单文件）；--publish 提交到你的私有用量仓库
ccx ui [--project 文件夹] [--no-open] [--export 文件]   # 本机只读实时页面（127.0.0.1，不调用模型）
ccx config set ui.lang zh          # ccx ui 和 ccx 写进会话的提示用中文
ccx config set defaults.tradeoff 0.3   # 省钱↔快 的旋钮：save / balanced / fast，或 0..1
ccx ab done <id> --ok 1             # 结束一次 A/B 抽样（主智能体自己做的那 10%）
ccx run "任务" --to gemini --tier T2                       # 派给 Gemini CLI
ccx run "任务" --to deepseek      # 通过 Claude Code 用 DeepSeek flash（密钥放环境变量 DEEPSEEK_API_KEY），思考强度按难度选
ccx run "任务" --provider deepseek-codex   # 同一个模型经 Codex（用 -c 设 model provider，密钥从环境变量读）
ccx run "任务" --to dsh --tier T2          # DeepSeek 自己的智能体 DeepSeek Harness（无头模式）
ccx run "任务" --provider glm              # 较新的 API 经 Claude Code：kimi、glm、qwen、openrouter（要有密钥）
ccx run "任务" ... --bg             # 后台跑，马上返回 run_id；用 ccx show 查看
ccx send --list | --thread <id> "消息"   # 发消息给正在运行的 Codex 桌面/交互会话（只有 Codex：Claude Code 的终端
                                        # 和桌面会话都没有接收外部消息的入口；Claude 子智能体用 ccx resume <run_id> 追问）
ccx skills find pdf 表格             # 先在共享技能库里找，别重复写
ccx skills install [--replace] [--apply]   # 把仓库里的技能链接进 hub（默认先预演），以后 git pull 就是升级
ccx improve add <技能> "遇到的具体问题" --fix "怎么改"   # 只记真实遇到的问题
ccx mem add "一句话" --by claude     # 写入共享记忆
ccx mem delta --as codex            # 拿对方新增的条目（hook 会自动运行）
ccx mem compact                     # 把日志合并进快照
ccx ctx init | add "…" | show       # 项目背景文件
ccx sync [--apply] [--only skills,memory,hooks,mcp]
ccx doctor
```

## 分级（`config/tiers.toml`，可在 `hub/ccx/tiers.toml` 覆盖）

固定分级是后备方案；带打分参数时由 task-routing 按成功率和每次成功的花费来选，并且会根据实际结果自动校准。

| 级 | 任务 | Codex | Claude Code | Gemini CLI |
|---|---|---|---|---|
| T0 | 两三步就做完 | 不派 | 不派 | 不派 |
| T1 | 机械活 | gpt-6-luna · low | haiku · low（不加载 MCP） | flash-lite |
| T2 | 常规开发 | gpt-6.1-sol · medium | sonnet · medium | flash |
| T3 | 困难 | gpt-6.1-sol · high | opus · high | pro |
| T4 | 关键/研究级 | gpt-6-astra · xhigh | opus · max | pro |

Gemini 用的是 CLI 的别名，新型号出来不用改配置；Gemini CLI 没有推理强度参数。
DeepSeek Harness（`--to dsh`）：T1–T3 用 deepseek-flash 的 low / high / max，T4 用 deepseek-v4-pro · max。

**按 token 付费的智能体**（`[providers.*]` 里的各家和 `dsh`）花的是真钱，所以每家都有 `daily_usd` 上限（默认 $1）；环境变量里没有密钥的 provider 不参与任何选择（`ccx agents` 里看 `ready`）。没有价格的模型会被拒绝运行，因为它花了多少算不出来，上限就守不住。它们不会被自动拿来在额度用完时接班，也不会自己被选为审查者；自动选模型只考虑经 Claude Code 的 DeepSeek（有标定和价格），其余几家标定之前要用 `--provider` / `--to` 指定。

## 安全边界

- 子智能体默认**可以改文件**（Codex `workspace-write` 沙箱；Claude `acceptEdits` 加工具白名单，只放行 git/python/pytest/npm/node 命令）。只想让它分析时加 `--mode read`。多个并行写任务自动放进不同 git worktree。
- 子智能体不能再派子智能体（`CCX_DEPTH`）。
- `ccx sync` 默认只预演。真改时每个被改的文件当天先备份一次。Codex 的 `config.toml` 只追加一个带标记的 hook 块，写入前先用 TOML 解析器检查。MCP 一律通过两边官方 CLI 添加。
- 不读取、不复制任何账号凭据。

## 测试

```bash
python -m pytest -q tests        # 或 python -m unittest discover -s tests
```

测试用模拟的 codex/claude/gemini（`tests/fakes/`）检查：命令参数、流式解析、升级、续会话、额度回退、超时、防套娃、增量记忆、同步的幂等和备份、学习回路、看板。GitHub Actions 在 Linux/Windows/macOS × Python 3.11–3.13 上跑。
**测试只证明这些逻辑本身是对的，不能证明在真实 CLI 和你的电脑上跑通**。在你自己的电脑上请跑 `ccx selftest`，验收清单见 [docs/DESIGN.zh.md](docs/DESIGN.zh.md) 的“验收”。

## 省了多少，怎么算

- **AE$（API 等价美元）**：token × 官方价格表，按 4 类分别计价（新输入、写缓存、读缓存、输出）。订阅制不按 token 收费，所以用它做统一尺子。实测与 Claude 自报费用差 1.5%。
- **估计节省**：每个派出去的任务 = 同样的 token 按主智能体模型的价格算 − 子智能体实际花费 − 写简报和验收的开销；附 95% 置信区间。
- **A/B 实测**：约 10% 本可以派的任务，随机让主智能体自己做（`defaults.ab_self_rate`，可设为 0 关掉），按同样难度对比实际花费，用来检验上面的估算。
- 主智能体自己的用量从两边工具自带的会话记录里读（Claude `~/.claude/projects`，Codex `~/.codex/sessions`），子智能体的会话会排除，避免重复计算。

## 已核对的外部事实（2026-10-22/24）

- codex-cli 0.164.0 `exec --help`：`--json`、`-m`、`-c`、`--output-schema`、`-o`、`--ignore-user-config`、`--ephemeral`、`exec resume <id>`（resume 不接受 `-s`，所以沙箱统一用 `-c sandbox_mode=…`）；精简启动（`--ignore-user-config`）必须带上用户的 `windows.sandbox`，否则 Windows 上只读模式会拒绝所有命令
- Claude Code 2.1.309 `--help`：`-p --output-format json|stream-json`（stream-json 必须加 `--verbose`）、`--model`、`--effort low..max`、`--json-schema`、`--resume`、`--strict-mcp-config`；实测：第一条事件带 session_id，最后的 result 事件带 `structured_output`、`usage`、`total_cost_usd`；`--resume` 报的是单次用量；默认参数无头启动约 4.6 万 token，写入 1 小时缓存；用 ccx 的精简参数约 2 万，一小时内再次启动（哪个项目都行）只新写入约 650–2000 token
- OpenAI GPT-6 文档：`gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-luna`；6.1-sol 的 effort 为 low/medium/high/xhigh/max
- Codex hooks 文档：`[[hooks.SessionStart]]`，stdout 作为开发者上下文注入，新 hook 需要在 `/hooks` 里信任
- Gemini CLI 0.65.0 `--help` 与内置源码：`-p`（无头，附加在 stdin 之后）、`-o stream-json`（init / message / tool_use / tool_result / error / result 事件）、`--approval-mode plan|auto_edit`、`--session-id`、`--resume <uuid>`、模型别名 `flash-lite / flash / pro`
- DeepSeek Harness（`dsh`，github.com/deepseek-ai/deepseek-harness，标签 dsh-v0.2.1-rc.3，2026-10-24 读源码，本机未安装）：`dsh --profile headless "任务"`（或用 `-` 从 stdin 读）跑一个任务；`--json` 输出 session / status（step_end 带用量、turn_end 带结束原因）/ text / tool_call / tool_result / final / error 事件；`--session-id <id>` 续接。token 计数互不重叠（input 不含缓存命中）。rc.3 没有模型和权限参数：模型写在 `--patch` 覆盖文件里（`agent-default-model` 行），沙箱用 `DSH_PERMISSION_MODE`。基础配置默认会把会话日志随请求上传给 DeepSeek，ccx 跑它时关掉。
- Codex 自定义 model provider（Codex 配置参考，2026-10-24 读）：`model_provider` 加 `[model_providers.<id>]`，字段 `base_url`、`env_key`、`wire_api`（只支持 `"responses"`）；`openai`、`ollama`、`lmstudio` 是保留名。DeepSeek 的 Codex 接入页用 `base_url = "https://api.deepseek.com/"`、`wire_api = "responses"`。codex-cli 0.164 实测：走自定义 provider 时 `apps` 和 `plugins` 会把所有连接器的工具定义整份发出去（“回复 OK”首请求 21.9 万输入 token，加 `--disable apps --disable plugins` 后 1 万），所以 ccx 经 provider 跑 Codex 时关掉这两项和 Codex 自带子智能体。Codex 会提示找不到 `deepseek-flash` 的模型元数据、改用默认元数据，但能跑完。
- 较新的 API（Claude Code 用的 Anthropic 兼容端点，2026-10-24 读，都没真跑过）：
  - Kimi：`https://api.moonshot.ai/anthropic`，`kimi-k3.1-pro`；价格表是网页脚本渲染的，没读到数字，所以在你写上价格之前 ccx 拒绝运行它；
  - GLM（Z.ai）：`https://api.z.ai/api/anthropic`；GLM-5.3-Flash $0.15 / $0.03 / $0.50，GLM-5.3 $1.4 / $0.26 / $4.4；
  - Qwen（阿里云百炼按量付费）：地址是 `https://{WorkspaceId}.<地域>.maas.aliyuncs.com/apps/anthropic`，所以 ccx 从 `DASHSCOPE_ANTHROPIC_BASE_URL` 读；qwen3.7-plus $0.4 / $1.6，qwen3.7-max $2.5 / $7.5（新加坡，没给缓存价，按输入价算）；
  - OpenRouter：`https://openrouter.ai/api`；没有默认模型，要给 `--model` 和它的价格。
  - 各家文档把密钥放在 `ANTHROPIC_AUTH_TOKEN`；ccx 用 `--bare` 跑 Claude Code，只认 `ANTHROPIC_API_KEY`（以 `x-api-key` 发送）。DeepSeek 接受这种方式，其他几家还没确认。
- DeepSeek 文档：Claude Code 用 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` 加密钥；ccx 用 `ANTHROPIC_API_KEY` 加 `--bare` 传入，调用方自己的 Claude 登录不会被发到 DeepSeek（2026-10-24）；闲时半价；价格（高峰）deepseek-flash 输入 $0.30 / 缓存 $0.006 / 输出 $1.20，deepseek-v4-pro $1.32 / $0.044 / $3.96（每百万 token）
- Gemini 价格（ai.google.dev/pricing）：3.5-flash-lite $0.30 / $0.03 / $2.50，3.8-flash $0.75 / $0.075 / $3.75（到 2026-12-31），3.1-pro-preview $2.00 / $0.20 / $12.00

## 同类项目对比

2026-10-24 查看（星数和日期来自 GitHub API，会变）。细节、来源和哪些还没确认：
[docs/research/landscape.zh.md](docs/research/landscape.zh.md)。

| 项目 | 做什么 | 星数 · 最近推送 · 许可证 | 和 ccx 的区别 |
|---|---|---|---|
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | OpenAI 官方的 Claude Code 插件（2026-03-30）：让 Codex 审查、接活、把会话转给 Codex、管后台任务 | 3.45 万 · 2026-07 · Apache-2.0 | 只做 Claude → Codex，不选模型、不记花费。ccx 两个方向都做，另有按成本选模型、账本和主智能体成本。按设计可以一起用（命令和 hook 各是各的），但还没实测过一起用；装了它时 `ccx doctor` 会提示。 |
| [PAL MCP](https://github.com/BeehiveInnovations/pal-mcp-server)（`clink`） | MCP 服务器，把多家模型接进一个 CLI；`clink` 能启动另一个 CLI 当子智能体 | 1.18 万 · 2025-12 · Apache-2.0 | PAL 用 API key 接更多模型和工具；ccx 用两个 CLI 的订阅额度，按成功率和成本选，并用实际结果校准。 |
| [CCB](https://github.com/SeemSeam/claude_codex_bridge)（`SeemSeam/claude_codex_bridge`） | 可见的多智能体终端工作区，支持 16 类 CLI，代理间有消息队列，可随时接管 | 3,595 · 2026-10 · AGPL-3.0 | CCB 重在一起看、一起指挥多个代理；ccx 是无界面的派活工具，重在成本。名字相近，但是不同的项目。 |
| [sendbird/cc-plugin-codex](https://github.com/sendbird/cc-plugin-codex) | 跑在 Codex 里调 Claude Code 的插件（官方插件的反方向） | 226 · 2026-10 · Apache-2.0 | 只做 Codex → Claude。 |
| [umum-ai](https://github.com/umum-ai/claude-codex-bridge) / [Jayden-X-L](https://github.com/Jayden-X-L/claude-codex-bridge) 的 `claude-codex-bridge` | 在 Claude 里调 Codex 并可中途追加指令 / 双向互相审查 | 10 / 16 · 2026 · MIT | 各做一部分（插话、审查），不选模型、不记账。 |
| [claude-codex-memory-sync](https://github.com/DaizeDong/claude-codex-memory-sync)、[mycelium](https://github.com/conradomateu/mycelium)、[memorize](https://github.com/shakystar/memorize) | 在工具之间同步技能、指令、MCP 和记忆 | 1–31 · 2026 · MIT | 只管配置和记忆；ccx 的共享记忆是为派活服务的。 |

ccx 没有的：可见的分屏界面、任务运行中追加指令、多家模型共识、把整段对话搬进 Codex。ccx 还欠的：省了多少还没实测
（见本页开头）。

## 常见问题

**多一个智能体，不是更费 token 吗？** 有可能。实测里，小任务派出去只有在主智能体看到 ccx 的验收通过就直接答复时才省（每个任务少 1 次请求）；主智能体如果再自己跑一遍测试，就是多花子任务的钱、还多等十几秒。很小的任务 ccx 会直接让你自己做（`delegated: false`）。钱主要花在主智能体每轮重读自己的对话上，所以 `ccx lead`、`ccx sum`、`ccx fresh` 管的是这一块。`ccx report` 用你自己的运行算差多少；`ccx trial` 做一周的正式对比。

**我用的是订阅，不是 API。** 花费按 API 价格折算，方便互相比较；看板也会显示每个工具的额度用在了哪里。一边额度用完了，任务会换到另一边。

**让子智能体改文件安全吗？** 只能改任务所在的文件夹；每次可写运行都会拍快照，可以 `ccx undo`；`--mode read` 或 `--worktree` 不会动你的工作区。详见 [SECURITY.zh.md](SECURITY.zh.md)。

**只读还是可以改文件？** 不加 `--mode` 时，ccx 按任务描述判断：说的是分析、解释、对比（analyze、review、explain……）就只读；要修复、添加、重构、改成（fix、add、refactor……）就可以改；判断不了时沿用原来的默认（可以改），并在结果里说明。`--mode` 永远优先。只读的子智能体发现必须改文件才能完成时，会停下并标成 `needs_write`，交回给你决定。

**它操作的是聊天网页吗？** 不是。两边调用的都是工作模式（`codex exec`、`claude -p`），也就是你在终端里用的那个智能体，不是网页聊天。

**支持哪些工具？** Claude Code 和 Codex CLI 可以当主也可以当子，两个方向都在真机上测过。通过 Claude Code 用 DeepSeek 已在真实任务上校准过，只当子智能体；经 Codex 用 DeepSeek 真跑过（一个小的只读任务）。DeepSeek Harness（`dsh`）和 Gemini CLI 已经适配（社区维护），只当子智能体，还没真跑过。Kimi、GLM、Qwen、OpenRouter 已配置，没真跑过。每家一个适配器（`ccx/agents/`），`ccx agents` 列出各自的能力；加一家的方法见 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md)（从 `ccx/agents/_template.py` 和 `tests/fakes/fake_template.py` 开始）。

**官方还是社区？** *官方*（Claude Code、Codex CLI）：每次发版都在适配器 `tested_version` 写的版本上真跑只读、可写和续接任务（发版检查）。*社区*（Gemini CLI、`dsh`、新加的适配器）：按命令行的 `--help` 和文档写成，只用模拟程序测过。装的版本主次版本号和 `tested_version` 不一样时，`ccx doctor` 会给 WARN：官方的请先跑发版检查再用，社区的表示在这个版本上没验证过。

**两个模型能直接讨论吗？** 现在能做的是单向的：`ccx ask` 问一次第二意见，`ccx resume` 在同一个子会话里追问，`ccx send` 发消息进正在运行的 Codex 会话。选错代价高的决定可以用 `ccx discuss`：不同厂商的模型最多讨论 3 轮（一家出方案、一家挑错、一家裁判），轮与轮之间只传要点；组长开之前会先问你。

## 安全

ccx 会运行什么、能改什么、怎么报告问题：[SECURITY.zh.md](SECURITY.zh.md)。

## 参与贡献

见 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md)（测试、规则、怎么为另一个智能体命令行加适配器）和[行为准则](CODE_OF_CONDUCT.md)。

## 许可

MIT，见 [LICENSE](LICENSE)。
