# 调研：官方插件共存、同类项目与改名备选（2026-10-24）

[English](landscape.md)

对应提案 J8（和官方 codex-plugin-cc 共存）、J9（同类项目对比）、J10（改名备选）。

**查看方式和日期：** 本文所有 GitHub 数字（星数、最近推送、许可证、创建时间）都是 **2026-10-24** 用 GitHub API
（`gh api repos/<owner>/<repo>`、`gh search repos`）查到的，之后会变。PyPI 是否重名用
`https://pypi.org/pypi/<名字>/json` 的返回码判断（200 = 已被占用，404 = 未被占用），同日查看。查不到或没有一手来源的写
“未确认”。本文 **没有安装任何插件**，需要实测的列在每节末尾。

## 结论

1. **官方插件确实存在。** `openai/codex-plugin-cc`，2026-03-30 创建并发布 v1.0.0，Apache-2.0，查看时约 3.45 万星，
   最新 v1.0.6（2026-07-08）。它让 Claude Code 调 Codex 做审查、派活、把会话转给 Codex、管后台任务。
2. **和 ccx 重叠的只有“Claude → Codex 派活”这一侧。** 官方插件不选模型（不传 `--model` 时由 Codex 用自己的默认值）、
   不记 token 和花费、不做 Codex → Claude 反向、不管主智能体成本、不管多家。共存方案：检测到它已安装时，审查和会话转移建议
   直接用它，ccx 专注路由、校准、记账、主智能体成本和多家（第 1.4 节）。
3. **同类项目很多，各有侧重。** 最接近的是 PAL MCP 的 `clink`（MCP 里调别的 CLI）和 CCB（`SeemSeam/claude_codex_bridge`，
   可见的多智能体终端工作区）。没有找到第二个“按成功率和成本选模型 + 记账 + 量主智能体成本”的项目，但这只是本次搜索的结果，
   不代表一定没有。
4. **改名值得考虑。** GitHub 上已有一个 3,595 星、几乎同名的 `SeemSeam/claude_codex_bridge`，以及至少 6 个同名的
   `claude-codex-bridge`；而且现名带两个厂商产品名。第 3 节给出 8 个备选，由用户拍板；本 PR 不改任何名字。

## 1. J8：OpenAI 官方插件 codex-plugin-cc

### 1.1 事实

| 事实 | 内容 | 来源 |
|---|---|---|
| 名字 | 仓库 `openai/codex-plugin-cc`；插件市场名 `openai-codex`，插件名 `codex`（安装 id `codex@openai-codex`） | [仓库](https://github.com/openai/codex-plugin-cc)、[marketplace.json](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json) |
| 发布时间 | 仓库创建 2026-03-30T15:29Z，v1.0.0 发布 2026-03-30T16:44Z；OpenAI 开发者社区帖子日期 2026-03-30 | [releases](https://github.com/openai/codex-plugin-cc/releases)、[社区帖](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186) |
| 最新版本 | v1.0.6，2026-07-08；最近推送同日 | [releases](https://github.com/openai/codex-plugin-cc/releases) |
| 许可证 | Apache-2.0 | [LICENSE](https://github.com/openai/codex-plugin-cc/blob/main/LICENSE) |
| 活跃度 | 约 34,536 星 | GitHub API |
| 官方文档 | 只有仓库 README；没找到 developers.openai.com 上的专页（未确认是否存在） | [README](https://github.com/openai/codex-plugin-cc#readme) |
| 前置条件 | ChatGPT 订阅（含免费版）或 OpenAI API key；Node.js 18.18+；用的是本机已安装的 `codex`（全局 CLI）和它的登录、配置 | README “Requirements”“FAQ” |
| 安装 | 在 Claude Code 里：`/plugin marketplace add openai/codex-plugin-cc` → `/plugin install codex@openai-codex` → `/reload-plugins` → `/codex:setup` | README “Install” |
| 命令 | `/codex:review`（只读审查，不可加关注点）、`/codex:adversarial-review`（可加关注点的挑刺审查）、`/codex:rescue`（派活，经 `codex:codex-rescue` 子智能体）、`/codex:transfer`（把当前 Claude 会话导入成 Codex 会话，打印 `codex resume <id>`）、`/codex:status`、`/codex:result`、`/codex:cancel`、`/codex:setup` | README “What You Get”“Usage” |
| 选模型 | `/codex:rescue` 可传 `--model`、`--effort`；不传时“Codex chooses its own defaults”；`spark` 映射到 `gpt-5.3-codex-spark`。没有按任务自动选模型 | README `/codex:rescue`、[rescue.md](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/commands/rescue.md) |
| 怎么调 Codex | 包装 Codex app server（`codex app-server`），不是独立运行时 | README “Codex Integration” |
| 后台任务状态 | 存在 `$CLAUDE_PLUGIN_DATA/state/<工作区名>-<hash>/`（没有该变量时在系统临时目录 `codex-companion/` 下），最多保留 50 个任务 | [state.mjs](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/scripts/lib/state.mjs) |
| Hook | 注册 `SessionStart`、`SessionEnd`、`Stop` 三个 hook；可选的“审查闸门”用 `Stop` hook，README 警告它可能形成长循环、很快耗尽额度 | [hooks.json](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/hooks/hooks.json)、README “Enabling review gate” |
| 记 token / 花费 | README 没提；在 `codex-companion.mjs` 里搜 `usage`/`token` 只命中帮助文字（2026-10-24 的 main）。**结论：未见记账功能**，但没逐行读完全部源码 | 源码搜索 |
| 反方向（Codex 调 Claude） | 不在这个插件里。社区有 `sendbird/cc-plugin-codex`（Apache-2.0，226 星）做反方向 | [sendbird/cc-plugin-codex](https://github.com/sendbird/cc-plugin-codex) |
| 旧的 `codex mcp-server` | 有二手报道说已弃用（[inside.com.tw](https://www.inside.com.tw/article/42196-openai-codex-plugin-claude-code)），没找到官方说明，**未确认**。本机 codex-cli 0.164.0 的 `codex --help` 里只有 `mcp`（管理外部 MCP）和 `app-server`，没有 `mcp-server` | 本机 `--help` |
| 发布当天的安全问题 | 有一篇报道说发布当天披露过分支名命令注入并已修复（[noqta.tn](https://noqta.tn/en/news/openai-codex-plugin-claude-code-rival-integration-2026)），只有这一个来源，**未确认** | — |

### 1.2 和 ccx 的重叠

| 功能 | 官方插件 | ccx |
|---|---|---|
| Claude Code → Codex 派活 | `/codex:rescue` | `ccx run --to codex` |
| 后台运行、看状态、取结果 | `--background`、`/codex:status`、`/codex:result`、`/codex:cancel` | `--bg`、`ccx show`、`ccx q` |
| 接着上一个 Codex 会话 | `--resume` / `--fresh`，会话可在 Codex 里 `codex resume` | 一小时内同一会话、同一文件夹自动续接；`ccx resume <run_id>` |
| 代码审查 | `/codex:review`、`/codex:adversarial-review` | `ccx run --review`、`ccx ask` |
| 把会话交给 Codex | `/codex:transfer`：用 Codex 的会话导入功能，转成可继续的 Codex 会话（保留原对话） | `ccx handoff`：写一份交接摘要，新会话读摘要（不搬原对话） |
| 按难度、成功率、成本选模型 | 无（手动 `--model`，否则用 Codex 默认） | 有（五问打分 + task-routing，`ccx verify` 校准） |
| 记 token、花费、额度 | 未见 | `ccx stats` / `ccx report` / `ccx quota` |
| 主智能体自己的成本 | 无 | `ccx lead`、每轮提示 |
| Codex → Claude、Gemini CLI、DeepSeek | 无 | 有（DeepSeek 经 Claude Code 或 Codex 真跑过；Gemini CLI 和 DeepSeek Harness 还没有） |
| 共享记忆、技能、MCP | 用 Codex 自己的配置，不同步 | `ccx sync`、`ccx mem` |
| 安装方式 | Claude Code 插件市场，Node.js | pipx，Python 标准库 |

### 1.3 官方插件做得比 ccx 好的地方（如实写）

- 官方维护，跟 Codex app server 的协议一起演进；ccx 走 `codex exec`，靠解析 JSON 输出。
- `/codex:transfer` 能把 **完整的 Claude 会话** 转成 Codex 会话，ccx 的交接只有摘要。
- 一行命令安装，有 `/codex:setup` 帮忙装 Codex 和登录。
- 用户量大得多，问题更可能被别人先踩到。

### 1.4 共存方案（设计，未实现）

**原则：** 不抢它的活，不碰它的文件。ccx 只读它是否已安装，不调它的内部脚本、不改它的配置、不替用户安装。

1. **检测。** `ccx doctor` 和 `ccx setup` 运行 `claude plugin list --json`（Claude Code 2.1.309 有这个命令，`--help`
   说明是“List installed plugins”；本机列表为空，所以 **输出字段名未确认**），找 id 为 `codex@openai-codex` 的项。
   读不出来就当作没装，不报错。
2. **检测到已安装时：**
   - `ccx doctor` 多一行：“已检测到官方 codex-plugin-cc：审查可用 `/codex:review`，转会话可用 `/codex:transfer`；
     ccx 负责选模型、记账和主智能体成本。”
   - agent-delegate 技能在 Claude 当主智能体时加一句分工：**只要第二意见或审查**，用 `/codex:review` /
     `/codex:adversarial-review`；**要按成本选模型、要记账、要能续接和回退**，用 `ccx run --to codex`。
   - 想把整段对话搬到 Codex 时，提示 `/codex:transfer`，而不是 `ccx handoff`。
   - Codex → Claude、Gemini、DeepSeek、记忆和技能同步、`ccx lead` 不受影响。
3. **不做的事：**
   - 不调用 `codex-companion.mjs` 等插件内部脚本。它没有承诺稳定接口（这是判断，不是官方说明），版本一升就可能坏。
   - 不读写它的任务状态目录。
   - 不默认替用户打开“审查闸门”。它和 ccx 的每轮提示都挂在 Claude 的 hook 上，叠加后的行为没测过。
4. **记账缺口要说清。** 通过插件跑的 Codex 任务不经过 ccx，所以不进 ccx 的账本，`ccx report` 里的“派出去省了多少”
   不含它们。ccx 读 `~/.codex/sessions` 算 Codex 主会话用量；插件的任务能用 `codex resume` 打开，**可能**也落在这个
   目录里。如果落在这里，会被 ccx 当成 Codex 主会话的用量，分类就错了。这一点要实测（下面第 3 条）。

### 1.5 需要实测的后续待办

需要在一台愿意装这个插件的机器上做，本 PR 没做：

1. 装上后 `claude plugin list --json` 的实际输出，确定检测用哪个字段。
2. 装上后 Claude Code 每轮固定开销多多少 token（`claude plugin details codex@openai-codex` 会给预估的 token 成本，
   也可以用 `ccx lead --breakdown` 前后对比）。
3. `/codex:rescue` 跑的任务会不会写进 `~/.codex/sessions`；会的话，`ccx lead` / `ccx report` 要能把它们和主会话分开。
4. 插件的 `SessionStart` hook 和 ccx 的 SessionStart hook 同时存在时，两边输出是否都正常、开局多读多少 token。
5. 同一个仓库里先 `/codex:rescue` 再 `ccx run --to codex`（或反过来）会不会抢同一个 Codex 会话。
6. 打开审查闸门时，和 ccx 的每轮提示叠加有没有问题。

## 2. J9：同类项目

只列和“Claude Code / Codex 互相调用、共享记忆”直接相关的项目。星数和日期都是 2026-10-24 查看；“最近推送”是 GitHub 的
`pushed_at`。描述按各项目 README 概括，不评价好坏。

| 项目 | 做什么 | 星数 | 最近推送 | 许可证 | 和 ccx 的区别 |
|---|---|---:|---|---|---|
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | OpenAI 官方 Claude Code 插件：在 Claude 里调 Codex 审查、派活、转会话、管后台任务 | 34,536 | 2026-07-08 | Apache-2.0 | 只做 Claude → Codex；不选模型、不记账。见第 1 节 |
| [sendbird/cc-plugin-codex](https://github.com/sendbird/cc-plugin-codex) | 跑在 Codex 里的插件，调 Claude Code 做审查、派活、后台任务（反方向） | 226 | 2026-10-19 | Apache-2.0 | 只做 Codex → Claude；ccx 两个方向都走同一套路由和账本 |
| [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server)（PAL MCP，原名 Zen MCP） | MCP 服务器：在一个 CLI 里接多家模型（Gemini、OpenAI、OpenRouter、Ollama 等），有 chat、consensus、codereview 等工具；`clink` 工具能从一个 CLI 启动另一个 CLI 当子智能体 | 11,805 | 2025-12-15（v9.8.2） | Apache-2.0（LICENSE 是 Apache 2.0 原文，GitHub 显示为 NOASSERTION） | 模型多、工具多，也有“自动选模型”（由 Claude 挑）；ccx 按成功率和每次成功的成本选，并用实际结果校准、记账。PAL 走 MCP 和 API key，ccx 走两个 CLI 的订阅额度 |
| [SeemSeam/claude_codex_bridge](https://github.com/SeemSeam/claude_codex_bridge)（CCB） | 可见的多智能体终端工作区：在分屏里同时跑 Codex、Claude、Gemini、Kimi、Qwen 等 16 类 CLI，代理之间有消息队列，可随时接管；有后台守护进程、项目共享记忆文件 `.ccb/ccb_memory.md`、安卓遥控 | 3,595 | 2026-10-23（v8.7.18） | AGPL-3.0（LICENSE 文件写明，GitHub 显示为 NOASSERTION） | 重在可见、可接管的多代理协作和通信；ccx 是无界面的派活工具，重在选模型、成本和记账。名字和 ccx 仓库名几乎相同 |
| [umum-ai/claude-codex-bridge](https://github.com/umum-ai/claude-codex-bridge) | Claude Code 插件，通过 MCP 工具和 Channels 接 `codex app-server`：异步启动 Codex 任务、看进度、中途追加指令、停止、续接 | 10 | 2026-10-15 | MIT | 任务跑的时候能追加指令；ccx 是跑完后用 `ccx resume` 接着说。只做 Claude → Codex，不选模型、不记账 |
| [Jayden-X-L/claude-codex-bridge](https://github.com/Jayden-X-L/claude-codex-bridge) | 双向“审计”桥：一方做完，打包交给另一方的 CLI 复核，结果回到原对话 | 16 | 2026-06-02 | MIT | 专注互相审查；ccx 的复核只是派活流程的一步 |
| 其他同名 `claude-codex-bridge`（[Dunqing](https://github.com/Dunqing/claude-codex-bridge) 14 星、[ZhangYiqun018](https://github.com/ZhangYiqun018/claude-codex-bridge) 13 星、[keng1304](https://github.com/keng1304/claude-codex-bridge) 11 星等） | 多是 MCP 方式让 Claude 咨询 Codex，或双向调用 | 7–14 | 2025-09 至 2026-05 | MIT / 未声明 | 规模小；功能和上面几类相近 |
| [DaizeDong/claude-codex-memory-sync](https://github.com/DaizeDong/claude-codex-memory-sync) | 同一台机器上把 Claude Code 的技能、指令、兼容的 MCP 设置、审过的 hook 和项目记忆同步到 Codex；先预览、备份，可回滚 | 1 | 2026-10-24 | MIT | 单向（Claude → Codex）的配置同步，比 ccx 的同步覆盖面更细（命令、子智能体角色也转）；不做派活 |
| [conradomateu/mycelium](https://github.com/conradomateu/mycelium)、[shakystar/memorize](https://github.com/shakystar/memorize) | 在 Claude Code、Codex、Gemini CLI 等之间同步技能、MCP 和记忆（mycelium）；Claude Code 和 Codex 共享一份本地项目记忆（memorize） | 31 / 14 | 2026-10-24 / 2026-09-24 | MIT / MIT | 只做共享记忆和配置；ccx 的记忆是派活的配套，按“只给对方的新增行”注入 |
| [feiyun0112/AgentBridge](https://github.com/feiyun0112/AgentBridge) | 用微信和本机的 Claude、Codex、Gemini 等聊天（ACP 或 CLI 方式） | 28 | 2026-03-24 | 未声明 | 方向不同：人通过聊天软件用代理，不是代理互相派活 |
| [catatafishen/agentbridge](https://github.com/catatafishen/agentbridge) | JetBrains IDE 插件，让 AI 编程代理完整访问 IDE | 87 | 2026-10-21 | Apache-2.0 | 只是同名，领域不同 |

**关于名字里带 agent-bridge / agentbridge / codex-bridge 的项目：** GitHub 上按名字搜，`agentbridge` 和
`codex-bridge` 下面多是把代理接到微信、飞书、Slack、ChatGPT 网页版的桥（例如
[chenhg5/cc-connect](https://github.com/chenhg5/cc-connect) 16,080 星），和 ccx 不是一类。上表只挑了和“代理互相派活”
相关的几个。提案原文说的“agentbridge”具体指哪个仓库没有写明，这里列了两个最常见的同名项目，**未确认是否就是原意**。

**ccx 的位置（如实）：**

- 只在 ccx 里看到的：按成功率和每次成功的成本选“哪家 + 哪个模型 + 多大推理强度”，用 `ccx verify` 的实际结果校准；
  每次运行的 token、花费、额度记账和看板；量主智能体自己每轮重读的成本（`ccx lead`）；同一套流程两个方向通用，
  还能派给 Gemini CLI 和 DeepSeek。
- ccx 没有的：可见的分屏界面（CCB 有）、任务运行中追加指令（umum-ai 有）；多家 API 模型共识（PAL 有）；把完整对话转给 Codex
  （官方插件有）；聊天软件入口。
- ccx 的短板：当时是 0.4.0，仓库 0 星（2026-10-24）；省多少钱还没测出来（README 开头已写明）；Gemini CLI 没真机跑过。

## 3. J10：改名备选（等用户拍板）

**为什么考虑改名：**

- GitHub 上有 3,595 星的 `SeemSeam/claude_codex_bridge`（CCB），和本仓库名只差下划线；同名的 `claude-codex-bridge`
  至少还有 6 个（第 2 节）。搜索时很难区分。
- 现名里的 “Claude” 是 Anthropic 的产品名，“Codex” 是 OpenAI 的产品名，ccx 也不只接这两家了。
- 不改也可以：只在 README 第一句讲清和 CCB、官方插件的区别（这一节已经加进 README）。

**怎么查的（2026-10-24）：** PyPI 用 `https://pypi.org/pypi/<名字>/json` 的返回码；GitHub 用仓库搜索
`<名字> in:name`，记总数和星数最高的几个。**没有做商标数据库检索**（例如 USPTO、EUIPO），“厂商商标”一栏只看名字里有没有
Claude、Codex、OpenAI、Anthropic、Gemini、GPT 等厂商或产品名。改名前建议再查一次商标库和 npm。

| 候选 | 意思 | PyPI | GitHub 同名（in:name） | 含厂商名 | 优点 | 缺点 |
|---|---|---|---|---|---|---|
| **ccx**（仓库改名为 ccx，命令不变） | 现有命令名 | 未占用 | 2,774 个仓库名含 “ccx”，最高的是 ccxt/ccxt（44,556 星，加密货币交易库） | 不含；但 “cc” 常被读作 Claude Code | 用户已经在用这个命令，改动最小 | 太短，搜索时会被 ccxt 淹没；看不出是做什么的 |
| **relayline** | 接力线 | 未占用 | 5 个，都是 0 星、领域无关 | 不含 | 几乎没人用；“接力”贴近派活 | 看不出“省钱、记账”这一点 |
| **crewcost** | 团队 + 成本 | 未占用 | 0 个 | 不含 | 完全没重名；直接点出“成本” | 容易让人联想到 CrewAI（不同项目）；听起来像纯记账工具 |
| **leadwork** | 主智能体的活 | 未占用 | 25 个，最高 2 星、领域无关 | 不含 | 点出“主智能体别干便宜活” | 英文里不算常用词，意思要解释 |
| **tandem-agents** | 双人协作的代理 | 未占用（`tandem` 已被占用） | 2 个，最高 1 星 | 不含 | 好懂；适合“两边互为主从” | 推广到多家后“双人”不太准；Tandem 是很多产品的名字 |
| **taskbaton** | 任务接力棒 | 未占用 | 1 个，0 星 | 不含 | 几乎没重名；比喻清楚 | “baton” 这个词在同类项目里已有人用（见下一行） |
| **batonpass** | 交棒 | 未占用 | 13 个，最高 4 星 | 不含 | 比喻清楚，好记 | 同类里有 `agent-baton` 这类名字（例如 captpascallv-dev/agent-baton，主智能体给 CLI 派任务卡），容易混 |
| **agentledger** | 代理账本 | 未占用（但 `agent-ledger` 已被占用） | 109 个，最高 cahcacah/AgentLedger 81 星 | 不含 | 点出记账 | 和已有项目重名；只讲了记账一面 |

**不建议的：** `agent-baton`（PyPI 未占用，但 GitHub 上已有 19 个，其中至少两个也是“给多个代理接力派活”，最容易混）、
`baton`、`tandem`、`handoff`、`taskrelay`、`delegato`、`agent-ledger`（PyPI 都已被占用）。

**如果改名，影响面（供拍板参考，本 PR 不动）：** GitHub 仓库名（GitHub 会自动重定向旧地址）、`pyproject.toml` 的包名、
README 和网站里的链接、安装命令 `pipx install git+…`。命令 `ccx` 可以保持不变。

**决定（2026-10-24）：改名为 `relayline`**（命令 `ccx` 和 Python 包目录 `ccx/` 不变）。改名前查过，都在 2026-10-24：

| 查哪里 | 查什么 | 结果 |
|---|---|---|
| USPTO [商标检索](https://tmsearch.uspto.gov/) | `relayline` | 没有结果（对照查 `relay` 有 796 条，说明检索在工作） |
| [TMview](https://www.tmdn.org/tmview/)（含 EUIPO 和其他商标局） | `relayline` | 没有结果（对照 `relay`：3,015 条） |
| TMview | `relay line`（包含） | 2 条无关且已失效：RELAYPAY ONLINE PAYMENT SOLUTIONS（澳大利亚）、CHICAGO SHORELINE MARATHON AND RELAY（美国） |
| npm | `registry.npmjs.org/relayline`、`/relay-line`；npm 搜索 `relayline` | 404、404；0 个包 |
| PyPI | `pypi.org/pypi/relayline/json` | 404（未占用） |
| GitHub | `relayline in:name`；`github.com/relayline` | 5 个仓库，都是 0 星、领域无关；没有这个用户或组织 |

这不是法律意义上的商标清查：只查了同名；软件类里已有单词 `RELAY` 的商标（例如美国第 42 类一条有效注册），所以带 relay 的组合词并不独特。

## 来源

所有链接 2026-10-24 查看。

- openai/codex-plugin-cc：[仓库与 README](https://github.com/openai/codex-plugin-cc)、[releases](https://github.com/openai/codex-plugin-cc/releases)、[marketplace.json](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json)、[rescue.md](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/commands/rescue.md)、[hooks.json](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/hooks/hooks.json)、[state.mjs](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/scripts/lib/state.mjs)
- OpenAI 开发者社区：[Introducing Codex Plugin for Claude Code](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186)（2026-03-30）
- 二手报道（只用于标注“未确认”）：[inside.com.tw](https://www.inside.com.tw/article/42196-openai-codex-plugin-claude-code)、[noqta.tn](https://noqta.tn/en/news/openai-codex-plugin-claude-code-rival-integration-2026)
- 同类项目：第 2 节表格里的各仓库链接（README、LICENSE 文件、GitHub API 元数据）
- 本机命令：Claude Code 2.1.309 `claude plugin list --help`、`claude plugin details --help`；codex-cli 0.164.0 `codex --help`
- PyPI：`https://pypi.org/pypi/<名字>/json`
