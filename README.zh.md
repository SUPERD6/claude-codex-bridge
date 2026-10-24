<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="ccx：Claude Code 和 Codex 互相派活；一次真实运行：选了 luna/low，一次完成，已验收，$0.0023" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/claude-codex-bridge/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/claude-codex-bridge/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/claude-codex-bridge/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/claude-codex-bridge"></a>
</p>

<p align="center"><a href="README.md">English</a> · 中文 · <a href="https://superd6.github.io/claude-codex-bridge/zh/">网站</a></p>

> **仍在开发中（v0.4，2026 年 10 月）。** 它每天在一台 Windows 电脑上真实使用，两个方向、终端和桌面端都跑通了。还没做完的：
> - **还没有真实的“省了多少”数据。** 两周带验收结论的真实使用还没积累，选模型的初始参数未校准；下面的数字都是单次真实运行。
> - **只用模拟命令行测过的：** 待办队列（`ccx q`）、长期岗位、worktree 和 `ccx batch`、真实额度用完时换另一边、`ccx uninstall --apply`。Gemini CLI 从没真跑过。macOS 和 Linux 只在 CI 里跑过。
> - **还没做的：** 本机实时界面（`ccx ui`），以及 ccx 写进会话的几句提示语的中英文切换。上面的网站还没发布。
>
> 旧记录（CHANGELOG、docs/STATUS）里的提交号指的是公开前压缩掉的私有历史。欢迎提问题和反馈；哪些功能验证过、怎么验证的，见 [STATUS](docs/STATUS.zh.md)。

**让 Claude Code 和 Codex 互相派活。** ccx 为每一块工作挑一个最便宜、又大概率能做完的模型，交给另一个工具去跑，由主智能体验收，并记下花了多少——贵的主智能体就不用再干便宜的活。谁当主都行；也可以派给 Gemini CLI，或通过 Claude Code 用 DeepSeek。

```bash
pipx install git+https://github.com/SUPERD6/claude-codex-bridge
ccx setup                    # 向导：每一步都说明，改东西前先问
ccx run --to codex --mode read "用三行总结 README.md"
```

<p align="center"><img alt="演示动画：ccx route 选出 codex:gpt-6-luna:low，ccx run 一次完成，ccx verify 记下结论" src="docs/assets/demo.svg" width="100%"></p>

## 在真机上实测

| 项目 | 结果 |
|---|---|
| 启动一个 Claude 子智能体（每次请求的固定上下文） | 用 ccx 的精简启动：4.6 万 → **1.36 万** token |
| 一个小的只读任务，Claude Code → Codex | **一次完成**，luna/low，**$0.0023** |
| 记账和 Codex 自己的周额度对照 | 每 1% 额度折算 **$2.8–4.4**，4 个时段都稳定 |
| 测试 | 139 个，Linux、Windows、macOS × Python 3.11–3.13 |

1.0 之前会换成两周日常使用的真实数字（派出去到底省了多少）。

## 能做什么

| | |
|---|---|
| **两个方向都行**——Claude Code 当主、Codex 干活，或者反过来；终端和桌面端都可以。 | **自动选模型**——5 个问题打出难度 → 选智能体、模型、强度并给出成功率；每次 `ccx verify` 都会让它更准。 |
| **启动省钱**——子智能体精简启动；一小时内同一个子会话接着用，缓存不会失效。 | **共享记忆**——开局只推对方新写的几行；还有两边都能看到的项目层。 |
| **断了能续**——额度用完、崩溃或关了窗口：`ccx task resume` 接着原来的会话做。 | **有账可查**——每次运行的 token 和花费，以及派出去到底省了多少的看板。 |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture-dark.svg">
  <img alt="谁当主都行；ccx 把简报交给另一个工具在后台跑、交回 JSON；开局 hook 从你的 hub 带来新记忆、交接和没做完的任务；项目的 .ccx 文件夹放背景、日志、inbox、断点和撤回快照" src="docs/assets/architecture-light.svg" width="100%">
</picture>

设计说明：[docs/DESIGN.zh.md](docs/DESIGN.zh.md) · 进度：[docs/STATUS.zh.md](docs/STATUS.zh.md) · 决策记录：[docs/DECISIONS.md](docs/DECISIONS.md) · 变更：[CHANGELOG.md](CHANGELOG.md)

## 它怎么工作（一个例子）

你在 Claude Code 里说："把 `loader.py` 支持自定义分隔符，并补测试。"

1. Claude（主）按 5 项给任务打分（改 2 个文件、单模块、目标清楚、风险低、有现成写法），写一段不到 200 字的简报，只写目标、要看的文件、怎样算完成。
2. 执行 `ccx run --from claude --files 2 --coupling one --clarity goal "…"`。ccx 调用 task-routing 技能，算出每个“智能体:模型:强度”的成功率和每次成功的花费，挑出 `codex:gpt-6.1-sol:medium`。如果算下来自己做更划算、或者应该先拆开，就直接告诉主智能体，不派。
3. ccx 在后台调用 `codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" …`。会话 ID 一出现就存盘。Codex 自己读文件、改代码、跑测试，这部分 token 花的是 Codex 账号的额度。
4. Codex 必须按 JSON schema 回报：`status / summary / files_changed / verification / …`。Claude 只读这一小段，再自己看一眼 `git diff`，确认测试真的跑过，然后 `ccx verify <run_id> --ok 1`。
5. 如果 Codex 回报 `blocked`，ccx 会在**同一个 Codex 会话**里升一档（high）继续，不用重新喂背景。如果 Codex 额度用完，自动换 Claude 做；超时或崩溃，`ccx resume <run_id>` 接着做。
6. 每次运行都写进账本，结果自动记回 task-routing / task-split，下次选得更准。`ccx report` 生成看板网页：谁花了多少 token、什么类型的 token、额度用了多少、估计省了多少。

反过来，在 Codex 里用同样的命令加 `--to claude`，就是 Codex 当主、Claude Code 当子。

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
pipx install git+https://github.com/<you>/claude-codex-bridge
ccx init --hub <你的个人hub路径>
ccx doctor
```

**从克隆的仓库装**（要改代码，或者想让 `git pull` 直接升级接进 hub 的技能）：

```powershell
git clone https://github.com/<you>/claude-codex-bridge
cd claude-codex-bridge
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
     [--mode read] [--check CMD] [--review auto|on|off] [--worktree] [--task <id> --step <n>] [--minutes 60] [--no-fallback] [--force] [--no-ab]
ccx verify <run_id> --ok 1|0 [--note "说明"]  # 主智能体验收结论：校准选模型/拆分，并关掉 checkpoint 这一步
ccx resume <run_id> "追问"          # 在同一个子会话里继续；中断后也用它接着做
ccx task status | resume <任务>     # 长任务：一条命令接着做中断的那一步（额度用完时自动换另一边）
ccx handoff --by claude --to codex "做完了什么/定了什么/接下来做什么" [--next "任务5" ...]   # 换主智能体接力
ccx verify <run_id> --ok 0 --reason wrong     # 你的判断（没人判断的，12 小时后按证据自动记“大概率对/错”）
ccx handoff --from-transcript codex --to claude   # 原主智能体写不了（额度用完）：从它的会话文件生成交接
                                                  # （先用代码提取；格式认不出时交给自动选出的子智能体整理，--no-model 不用模型）
ccx undo <run_id> [--apply]         # 撤回某次可写运行改动的文件（新建的文件挪到一边，不删除）
ccx ask "问题"                       # 让另一个模型快速给个第二意见（只读、低强度）
ccx archive [--apply] | --restore <run>   # 归档用完的子会话（2 小时后也会自动归档）
ccx batch plan.json                 # 互不依赖的任务并行；多个写任务自动分到不同 worktree
ccx route --files 3 --coupling cross ... [--lead claude:opus:high --ctx-files 日志.txt]  # 只看推荐；加 --lead 还会比较自己做 vs 派出去
ccx plan size --minutes 240 --rung codex:gpt-6.1-sol:medium   # 大任务拆几块（task-split）
ccx show <run_id> [--full]          # 默认只显示压缩结果
ccx stats [--summary]               # 按 agent×级别统计；--summary 给出花费、省了多少、缓存占比
ccx report [--days 30] [--publish]  # 看板网页（离线单文件）；--publish 提交到你的私有用量仓库
ccx config set defaults.tradeoff 0.3   # 省钱↔快 的旋钮：save / balanced / fast，或 0..1
ccx ab done <id> --ok 1             # 结束一次 A/B 抽样（主智能体自己做的那 10%）
ccx run "任务" --to gemini --tier T2                       # 派给 Gemini CLI
ccx run "任务" --to deepseek      # 通过 Claude Code 用 DeepSeek flash（密钥放环境变量 DEEPSEEK_API_KEY），思考强度按难度选
ccx run "任务" ... --bg             # 后台跑，马上返回 run_id；用 ccx show 查看
ccx send --list | --thread <id> "消息"   # 发消息给正在运行的 Codex 桌面/交互会话
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

## 已核对的外部事实（2026-10-22）

- codex-cli 0.164.0 `exec --help`：`--json`、`-m`、`-c`、`--output-schema`、`-o`、`--ignore-user-config`、`--ephemeral`、`exec resume <id>`（resume 不接受 `-s`，所以沙箱统一用 `-c sandbox_mode=…`）；精简启动（`--ignore-user-config`）必须带上用户的 `windows.sandbox`，否则 Windows 上只读模式会拒绝所有命令
- Claude Code 2.1.309 `--help`：`-p --output-format json|stream-json`（stream-json 必须加 `--verbose`）、`--model`、`--effort low..max`、`--json-schema`、`--resume`、`--strict-mcp-config`；实测：第一条事件带 session_id，最后的 result 事件带 `structured_output`、`usage`、`total_cost_usd`；`--resume` 报的是单次用量；默认参数无头启动约 4.6 万 token，写入 1 小时缓存；用 ccx 的精简参数约 2 万，一小时内再次启动（哪个项目都行）只新写入约 650–2000 token
- OpenAI GPT-6 文档：`gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-luna`；6.1-sol 的 effort 为 low/medium/high/xhigh/max
- Codex hooks 文档：`[[hooks.SessionStart]]`，stdout 作为开发者上下文注入，新 hook 需要在 `/hooks` 里信任
- Gemini CLI 0.65.0 `--help` 与内置源码：`-p`（无头，附加在 stdin 之后）、`-o stream-json`（init / message / tool_use / tool_result / error / result 事件）、`--approval-mode plan|auto_edit`、`--session-id`、`--resume <uuid>`、模型别名 `flash-lite / flash / pro`
- DeepSeek 文档：Claude Code 用 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` 加密钥；ccx 用 `ANTHROPIC_API_KEY` 加 `--bare` 传入，调用方自己的 Claude 登录不会被发到 DeepSeek（2026-10-24）；闲时半价；价格（高峰）deepseek-flash 输入 $0.30 / 缓存 $0.006 / 输出 $1.20，deepseek-v4-pro $1.32 / $0.044 / $3.96（每百万 token）
- Gemini 价格（ai.google.dev/pricing）：3.5-flash-lite $0.30 / $0.03 / $2.50，3.8-flash $0.75 / $0.075 / $3.75（到 2026-12-31），3.1-pro-preview $2.00 / $0.20 / $12.00

## 常见问题

**多一个智能体，不是更费 token 吗？** 只有很小的任务会，这时 ccx 会直接让你自己做（`delegated: false`）。其余的子智能体用比主智能体便宜的模型、精简启动；`ccx report` 用你自己的运行算出差多少，大约每 10 个任务里会有 1 个让主智能体自己做，用来实测。

**我用的是订阅，不是 API。** 花费按 API 价格折算，方便互相比较；看板也会显示每个工具的额度用在了哪里。一边额度用完了，任务会换到另一边。

**让子智能体改文件安全吗？** 只能改任务所在的文件夹；每次可写运行都会拍快照，可以 `ccx undo`；`--mode read` 或 `--worktree` 不会动你的工作区。详见 [SECURITY.zh.md](SECURITY.zh.md)。

**只读还是可以改文件？** 不加 `--mode` 时，ccx 按任务描述判断：说的是分析、解释、对比（analyze、review、explain……）就只读；要修复、添加、重构、改成（fix、add、refactor……）就可以改；判断不了时沿用原来的默认（可以改），并在结果里说明。`--mode` 永远优先。只读的子智能体发现必须改文件才能完成时，会停下并标成 `needs_write`，交回给你决定。

**它操作的是聊天网页吗？** 不是。两边调用的都是工作模式（`codex exec`、`claude -p`），也就是你在终端里用的那个智能体，不是网页聊天。

**支持哪些工具？** Claude Code 和 Codex CLI，两个方向都在真机上测过。用 DeepSeek 的 Claude Code 已在真实任务上校准过；Gemini CLI 已经适配，但还没真跑过。

## 安全

ccx 会运行什么、能改什么、怎么报告问题：[SECURITY.zh.md](SECURITY.zh.md)。

## 参与贡献

见 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md)（测试、规则、怎么为另一个智能体命令行加适配器）和[行为准则](CODE_OF_CONDUCT.md)。

## 许可

MIT，见 [LICENSE](LICENSE)。目前是私有仓库，v1.0 之后公开。
