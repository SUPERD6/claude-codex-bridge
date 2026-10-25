# 进度

[English](STATUS.md) · 中文 · 更新于 2026-10-24 · 版本 0.4.0 · 317 个测试

这一页故意只写一页：智能体开局读进来的东西，之后每一轮都要跟着重读。以前的记录、完整的把握程度表、验收检查和完成列表在 [STATUS-archive.zh.md](STATUS-archive.zh.md)；改了什么写在 [CHANGELOG.md](../CHANGELOG.md)。请保持简短：做完一项就在这里写一行，细节放进更新记录。这一页只由主会话改；各个 PR 改为加一个 `changes/<PR>.md`。

## 现在

顺序来自共享方案（提案 F–J，都已批准）。**J13** 把压主智能体成本的几项提到前面，因为花费几乎都在主智能体每轮重读自己的对话上（子任务 30 天共 $0.34；主智能体每轮重读中位数约 22 万 token）：

| 步骤 | 状态 |
|---|---|
| H13 自动记对错 | ✅ PR #2 |
| H10 主智能体自己的上下文（`ccx lead`、每轮提示） | ✅ PR #3 |
| H11 一周正式对比：工具（`ccx trial`） | ✅ PR #5——一周的数据由实测会话收集（PR #6，含 J0、E8、F9） |
| J1 + J2 每轮重读什么、缓存在哪断了（`ccx lead --breakdown`、`--cache`） | ✅ PR #8 |
| J3 大段输出先压缩再给主智能体（`ccx sum`） | ✅ PR #9 |
| J6 这一页压到一页 | ✅ PR #10 |
| J0 基线、H11 第一批、E8 两向交接、F9 开/关、J7 | ✅ PR #6（[报告](research/2026-10-24-h11-e8-f9-measurements.zh.md)）：主智能体每次请求中位数 35.2 万 token / $0.11（7 天），每次约 5.5 万固定开销；只有主智能体信 ccx 的 check 时，派活才每个小任务少 1 次请求；F9 没启动过子智能体；J7 开关已加，还没有推翻数据 |
| 按那份报告修的：交接按文件存（并行会话不互相覆盖）、编号列表兜底计划、交接附这段对话的 ccx 运行、节省有实测就用实测否则标明是模型、agent-delegate 写明验收已过就别重跑 | ✅ PR #15 |
| J12 真机跑一次 `ccx uninstall --apply` 再装回（报告 5c）；修了：换行保持原样、Codex 块放回原位、卸载后提示怎么装回技能 | ✅ PR #17 |
| J8–J10 官方 codex-plugin-cc 共存、同类项目、改名备选（只改文档，[调研](research/landscape.zh.md)） | ✅ PR #4；共存方案未实现、未实测；改名等用户拍板 |
| G1 `ccx ui`（本机只读实时页面）+ `ui.lang` | ✅ PR #7；`ccx stop` 接着做（适配器已合并） |
| I1–I4 适配器按家收拢、按厂商判断“另一家”、额度换边和审查者按数据选 | ✅ PR #11——新接口：`ccx.agents.get(名字)` → `Adapter`（build/parse、vendor、support、tested_version、capabilities()）；`ccx.agents.vendor()`、`others()`；`ccx agents` 以 JSON 列出 |
| J4 一键换新会话（`ccx fresh`） | ✅ PR #12 |
| J5 给主智能体自己的档位建议（`ccx lead --suggest`、看板一行） | ✅ PR #13 |
| J11 按职责拆 `ccx/delegate.py`，行为不变 | ✅ PR #14 |
| F10–F14 自带子智能体：按花费和额度限制、Claude 给 Agent 工具、有独立部分时明确要求用子智能体 | ✅ PR #18——上限还没被真实运行触发过（子智能体很少启动：PR #6） |
| H5–H6 + I6 共享记忆用起来：建议记下的事由用户同意才写、本项目优先、记录用到次数、没有开局 hook 的工具在派活说明里带相关记忆 | ✅ PR #21——建议是启发式抽取；**H7 等用户做**：第一次（在 `...\玩` 文件夹里）碰上了中文路径崩溃，PR #27 已修；请在 Codex 桌面端新开一个对话再发一次“ok” |
| 每个 PR 只加 `changes/<PR>.md`，不再直接改 CHANGELOG/STATUS | ✅ PR #22 |
| H3–H4 + I7 `ccx discuss`（2–3 家出方案、挑错、裁判，`ccx ui` 里显示成对话） | ✅ PR #23——真跑过一次讨论（Codex + Claude，3 轮达成一致，$0.28）；只有两家时出方案的也当裁判 |
| H8–H9 `ccx way`（按风险挑三种合作方式；按活的类型记一次做对率和返工率） | ✅ PR #24 |
| DeepSeek 作为第四家（`dsh` 适配器、经 Codex 跑 DeepSeek），以及 Kimi / GLM / Qwen / OpenRouter | ✅ PR #25——经 Claude Code 和经 Codex 两条路真跑过；`dsh`、Gemini 和几家小厂没跑（没装 / 没有 key） |
| 按七核心真机实测修的：`ccx task resume` 在会话开始前被杀时重开这一步（#26）；中文路径不再崩溃（#27）；`ccx doctor` 检查 Codex 组长的沙箱（#28） | ✅ #26、#27；#28 待合并——在 Windows 上只有 `danger-full-access` 能让 Codex 组长派活给 Claude |
| 七核心真机 A/B（派活、选模型、审查、记忆；3 轮，上限 $6） | ⏳ 进行中（ccx-evals 会话）；第 1 轮：派活让主智能体每 3 次请求少 1 次，但总花费持平、慢约 2.7 倍；自动选模型不比固定一个模型好；审查花费约 34 倍，通过率没提高，还放过了一个错的解 |

## 接下来三件

1. 跑完七核心 A/B（第 2–3 轮和记忆组），按结果改：审查和选模型的默认设置；“ccx 说通过、隐藏测试失败”的情况（可见测试漏了要求时，验收命令太弱）。
2. J1–J6 合并一周后用 `scripts/eval/j0_baseline.py real --days 7` 对比 PR #6 里的真实会话基线；每周抽查 5 条自动判定，J7 才有推翻比例。
3. 然后：H7（上面那条用户确认）、`ccx stop`、I5、H1–H2、H12、H14–H16、I8、让第三家真正参加一次 `ccx discuss`，最后发版。

## 把握程度（简版）

**真机** = 在一台真实的 Windows 电脑上、用已登录的命令行工具跑过；**模拟** = 只有用模拟命令行工具的测试。

- **真机**：两个方向的委派（只读和可写）、`--check`、独立审查、失败类型、`--bg`、`ccx send`、自动续接、杀掉后 `task resume`、Claude 侧的记忆、接入（`sync --apply`）、记账和 `ccx report`、DeepSeek 作为模型来源、E8 两个方向的交接（各一次）、`ccx lead --breakdown` / `--cache`、`ccx ui`（在 Edge 里打开过；数据是假 CLI 上跑出的 ccx 运行，也只读地开过一次真实 hub；其他浏览器和系统没开过）。
- **只有模拟**：worktree、`ccx batch`、额度用完换另一边、队列和岗位、`--fork`、Gemini CLI、真实的额度中断。
- **没校准**：选模型的先验（真实对错记录太少）、`ccx trial` 里 10 分钟的查看时间、`--breakdown` 每一项的 token 估算（总数是实测的）。
