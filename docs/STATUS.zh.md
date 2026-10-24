# 进度

[English](STATUS.md) · 中文 · 更新于 2026-10-24 · 版本 0.4.0 · 254 个测试

这一页故意只写一页：智能体开局读进来的东西，之后每一轮都要跟着重读。以前的记录、完整的把握程度表、验收检查和完成列表在 [STATUS-archive.zh.md](STATUS-archive.zh.md)；改了什么写在 [CHANGELOG.md](../CHANGELOG.md)。请保持简短：做完一项就在这里写一行，细节放进更新记录。

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
| J0 基线、H11 第一批、E8 两向交接、F9 开/关、J7 | PR #6（[报告](research/2026-10-24-h11-e8-f9-measurements.zh.md)）：主智能体每次请求中位数 35.2 万 token / $0.11（7 天），每次约 5.5 万固定开销；只有主智能体信 ccx 的 check 时，派活才每个小任务少 1 次请求；F9 没启动过子智能体；J7 开关已加，还没有推翻数据 |
| J8–J10 官方 codex-plugin-cc 共存、同类项目、改名备选（只改文档，[调研](research/landscape.zh.md)） | ✅ PR #4；共存方案未实现、未实测；改名等用户拍板 |
| G1 `ccx ui`（本机只读实时页面）+ `ui.lang` | ✅ PR #7；`ccx stop` 接着做（适配器已合并） |
| I1–I4 适配器按家收拢、按厂商判断“另一家”、额度换边和审查者按数据选 | ✅ PR #11——新接口：`ccx.agents.get(名字)` → `Adapter`（build/parse、vendor、support、tested_version、capabilities()）；`ccx.agents.vendor()`、`others()`；`ccx agents` 以 JSON 列出 |
| J4 一键换新会话（`ccx fresh`） | ✅ PR #12 |
| J5 给主智能体自己的档位建议（`ccx lead --suggest`、看板一行） | 本次改动 |

## 接下来三件

1. 在新适配器上做 F10–F14（按 PR #6 的实测缩小范围）；J11 是 PR #14。
2. J1–J6 合并一周后用 `scripts/eval/j0_baseline.py real --days 7` 对比 PR #6 里的真实会话基线；每周抽查 5 条自动判定，J7 才有推翻比例。
3. 然后是统一顺序里剩下的：H5–H7 + I6 共享记忆、H3–H4 + I7 `ccx discuss`、H8–H9、`ccx stop`、I5、H1–H2、H12、H14–H16、I8，最后开源发布。

## 把握程度（简版）

**真机** = 在一台真实的 Windows 电脑上、用已登录的命令行工具跑过；**模拟** = 只有用模拟命令行工具的测试。

- **真机**：两个方向的委派（只读和可写）、`--check`、独立审查、失败类型、`--bg`、`ccx send`、自动续接、杀掉后 `task resume`、Claude 侧的记忆、接入（`sync --apply`）、记账和 `ccx report`、DeepSeek 作为模型来源、E8 两个方向的交接（各一次）、`ccx lead --breakdown` / `--cache`、`ccx ui`（在 Edge 里打开过；数据是假 CLI 上跑出的 ccx 运行，也只读地开过一次真实 hub；其他浏览器和系统没开过）。
- **只有模拟**：worktree、`ccx batch`、额度用完换另一边、队列和岗位、`--fork`、Gemini CLI、`ccx uninstall --apply`、真实的额度中断。
- **没校准**：选模型的先验（真实对错记录太少）、`ccx trial` 里 10 分钟的查看时间、`--breakdown` 每一项的 token 估算（总数是实测的）。
