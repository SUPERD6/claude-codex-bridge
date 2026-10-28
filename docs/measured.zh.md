# 实测

[English](measured.md) · 中文 · 回到 [README](../README.zh.md) · 全部[研究报告](research/README.zh.md)

## README 四个数字的出处

| 柱子 | 数字 | 出处 | 局限 |
|---|---|---|---|
| 省钱 | 总花费少 63%；返工 0 次对 29 次 | [共享工作上下文 A/B](research/2026-10-25-shared-context-ab.zh.md)（2026-10-25，Codex luna low + DeepSeek flash low，42 对） | 任务专门设计成需要组长的上下文：按设计就是这个功能的最好情况 |
| 更准 | 一次做对 36/36 对 7/36（McNemar p ≈ 4e-9） | 同一个 A/B | 同上；中性任务两组都是 6/6 |
| 分工 | 组长每个任务都少 1 次请求，21/21 | [七核心 A/B](research/2026-10-24-seven-cores-ab.zh.md) §2.2 | 总花费基本持平（比值 1.02），token 3.3 倍，慢约 23 秒；组长是短的无头会话 |
| 共享 | 项目记忆被照做：9/9 对 0/9（McNemar p = 0.004，Holm 0.016） | [七核心 A/B](research/2026-10-24-seven-cores-ab.zh.md) §2.1 | 3 个任务 × 3 次；hub 记忆经开局 hook 这条路没测 |

## 第 5 轮：真实的大任务（2026-10-26/27，开发集）

本仓库 10 个真实改动 × 2，sonnet medium 当组长，隐藏测试；细节和所有组见[第 5 轮报告](research/2026-10-26-r5.zh.md)。
**开发集，只当信号**：这些任务也在修 ccx 时用过，而且这轮早于干净环境检查（[r5 计划 §8](research/2026-10-26-r5-plan.zh.md)）。
它不改上面四个数字。

| 轮次 | 组 | 做对 | 每次成功的花费 | 用时中位数 |
|---|---|---|---|---|
| r5h | ccx2（按 agent-delegate 技能现在教的用法） | 19/20 | $0.135 | 236 秒 |

对照报告里的第一轮：组长自己做 19/20、$0.211、94 秒；内置子智能体 19/20、$0.155、278 秒。报告 §7 的表停在 r5f；
r5h 这一行按同样的定义（20 个单元的总花费 / 做对的单元数；20 个单元用时的普通中位数）从同一个结果文件算出，
r5h 也在[编排层审计](research/2026-10-28-harness-audit.zh.md)里。

## 实测（2026-10-24，ccx 0.4.0）

全部来自真机上的真实运行，方法、原始表格和局限见[实测报告](research/2026-10-24-h11-e8-f9-measurements.zh.md)和[七核心 A/B](research/2026-10-24-seven-cores-ab.zh.md)。**有利的和不利的都列在这里。** 最后一列写明是测量还是外推。

| 问题 | 结果 | 把握 |
|---|---|---|
| 小任务派给 Codex 省不省？（[七核心 A/B](research/2026-10-24-seven-cores-ab.zh.md) 第 1 轮：7 个 Python 任务（4 小 3 中）× 3，sonnet 主智能体自己做 / 派给 Codex luna low，配对） | **总花费基本持平：比值 1.02**（中位数 $0.0344 → $0.0351；按任务的符号检验 p = 1）。**总 token 3.3 倍**（3.56 万 → 11.9 万），**慢约 23 秒**（10.9 → 33.7 秒）。主智能体**每个任务都少 1 次请求**（3 → 2，21/21）。做对：自己做 21/21，派出去 18/21（便宜的子智能体把一个中等任务 3 次都做错）。更早一批（PR #6）：haiku 当主、派完自己再跑测试，请求没省、花得更多。 | **测量**；5–15 分钟的任务、短的无头主智能体 |
| 换到真实的长对话主智能体会怎样？ | 少 1 次请求 ≈ 少读 35.2 万 token（下面的中位数）≈ 按 Opus 缓存读价每个小任务**约省 $0.07，多等约 23 秒**，而且可能做错；主智能体不省请求时，多花约 $0.003。 | **外推，不是测量**（[A/B](research/2026-10-24-seven-cores-ab.zh.md) §2.2） |
| 钱到底花在哪？（本机真实会话，7 天） | Claude 主智能体每次请求中位数 **35.2 万 token、$0.11**，缓存读占 99%；同期 ccx 子任务一共 $0.42。所以最该省的是主智能体每轮重读的上下文。 | **测量**（读会话文件，2026-10-17–24） |
| Codex 自带的子智能体会被用上吗？ | gpt-6-luna low 上 **5/5 次都没启动**，连明确要求的那次也没有；开 / 关的花费和用时差别在噪声以内。更高档的模型没测。 | 只对 luna low 有把握 |
| 只凭交接，接手方能说对“做到哪、下一步”吗？ | 受控场景 3/3 说对（含中途被杀）；真实长会话第一次说错（计划读成了过期状态），修好后说对。 | 真实会话只有 1 个 |
| 精简启动一个 Claude 子智能体 | 每次请求的固定上下文 4.6 万 → **1.36 万** token | 单次实测 |
| 记账和 Codex 自己的周额度对照 | 每 1% 额度折算 **$2.8–4.4**，4 个时段都稳定 | 4 个时段 |
| 测试 | 268 个，Linux、Windows、macOS × Python 3.11–3.13 | 只证明逻辑，不证明真机 |

## 省了多少，怎么算

- **AE$（API 等价美元）**：token × 官方价格表，按 4 类分别计价（新输入、写缓存、读缓存、输出）。订阅制不按 token 收费，所以用它做统一尺子。实测与 Claude 自报费用差 1.5%。
- **估计节省**：每个派出去的任务 = 同样的 token 按主智能体模型的价格算 − 子智能体实际花费 − 写简报和验收的开销；附 95% 置信区间。
- **A/B 实测**：约 10% 本可以派的任务，随机让主智能体自己做（`defaults.ab_self_rate`，可设为 0 关掉），按同样难度对比实际花费，用来检验上面的估算。
- 主智能体自己的用量从两边工具自带的会话记录里读（Claude `~/.claude/projects`，Codex `~/.codex/sessions`），子智能体的会话会排除，避免重复计算。

## 测试

```bash
python -m pytest -q tests        # 或 python -m unittest discover -s tests
```

测试用模拟的 codex/claude/gemini（`tests/fakes/`）检查：命令参数、流式解析、升级、续会话、额度回退、超时、防套娃、增量记忆、同步的幂等和备份、学习回路、看板。GitHub Actions 在 Linux/Windows/macOS × Python 3.11–3.13 上跑。
**测试只证明这些逻辑本身是对的，不能证明在真实 CLI 和你的电脑上跑通**。在你自己的电脑上请跑 `ccx selftest`，验收清单见 [docs/DESIGN.zh.md](DESIGN.zh.md) 的“验收”。

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
