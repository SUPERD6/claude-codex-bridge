# B3 子智能体精简开关：计划与评测组（2026-10-30）

[English](2026-10-30-b3-lean-switches-plan.md) · 中文 · 返回[研究报告](README.zh.md)

**状态：只是计划，什么都还没跑；下面没有任何数字是结果。** 开关已经在 ccx 里，出厂都是今天的做法；测量它们的评测组在 `scripts/eval/r5.py` 里。

## 为什么要新基线

到目前为止评测过的 ccx2 单元（r5、hc1），Codex 子智能体都跑在专用的评测 Codex home 里，带 `--ignore-user-config`、`--ignore-rules`、关 memories；Claude 子智能体不加载用户设置和技能。用户日常真正用的配置（Codex memories、AGENTS.md、技能）从没测过。B3 的多数开关是让子智能体*向*已测过的配置靠拢，所以拿它们和评测过的 ccx2 比，什么也比不出来：需要一个"日常配置"基线。

## 开关（config/tiers.toml 的 `[subagent]`，出厂都是今天的做法）

| 键 | 改了以后 | 预期（从对话记录估算，未实测） |
|---|---|---|
| `codex_memories`（true） | false：每一档 Codex 加 `-c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false` | 每次请求少约 6.8k，每次运行少 25–35k |
| `clean`（false） | true：Codex / dsh 用空 HOME，Claude 不加载技能和用户设置，提示加一句总结用什么语言，Agent 工具只在 `--parallel` 时给 | Codex 每次请求少 4–6k；Claude 每次运行少 5–8k |
| `codex_lean_tools`（false） | true，只对写入任务：关网页搜索、图片生成、goals；直连 OpenAI 时关 apps / plugins | 每次请求少约 3–4k |

细节和风险见[功能说明](../features.zh.md#实验性子智能体精简开关subagent实测前不开)。

## 评测组（手动选，`--arms ...`）

四组和 ccx2 一字不差（同一个主导、同样的措辞和命令行），区别只在子智能体启动用的 home，以及写进单元自己 hub 的 tiers.toml 里的 `[subagent]` 覆盖（主导开始前按 ccx 的读法读回确认；每组代码相同）。

| 组 | 子智能体 |
|---|---|
| `ccx2daily` | 日常配置基线：Codex 用每个单元自己的 home，里面是用户 `~/.codex` 的 memories/、AGENTS.md、skills/ 和 `~/.agents/skills`（作为它的 HOME）的副本，不加 `--ignore-user-config` / `--ignore-rules` / 不关 memories；Claude 子智能体加载 `user,project,local` 三层设置，技能开着 |
| `ccx2daily_nomem` | 基线 + `codex_memories = false` |
| `ccx2daily_clean` | 基线 + `clean = true` |
| `ccx2daily_leantools` | 基线 + `codex_lean_tools = true` |

每个单元的 home 怎么做（`scripts/eval/daily_home.py`）：

- 登录用评测 Codex home 自己的 `auth.json`，复制进单元的文件夹。凡是带用户自己登录的都不复制：任何深度的 `auth.json`、凭据文件、`config.toml`（hooks、信任状态、profiles、MCP 服务器）、sessions、日志、历史、数据库、rules、hooks、plugins 都不复制，链接不跟随。复制完再把文件夹走一遍，出现这类名字就停掉这个单元。
- 它的 config.toml 是写出来的，不是复制的：只有 ccx 精简启动时保留的设置（`windows.sandbox`）、评测关掉的功能（apps、plugins、remote_plugin：不接账号连接器）和用户自己的 memory 设置。所以这几组测不到 `codex_lean_tools` 里 apps / plugins 那部分；网页搜索、图片生成和 goals 测得到。
- 它在单元的 `x-` 文件夹里，单元结束后随之删除。
- 评测 Codex home 本身从不写入，所以其他各组的预检和单元间检查（那里出现 memories、AGENTS.md 或技能就拒绝）一点没变。每个单元自己的 home 是日常组写明的例外。Claude 子智能体仍用单元的设置文件（hooks 关、自动记忆关、禁止读真实 home），主导的隔离和审计和 ccx2 一样。在 `--claude-isolation flags` 模式下，用户设置层就是用户真实的 `~/.claude/settings.json`（hooks 仍关，用户级 CLAUDE.md 仍排除）；在 `config-dir` / `ccx-home` 下是单元的全新 home，所以 flags 模式下 Claude 那一侧更接近日常。
- 每行有 `daily`（复制了什么，只记名字；memory 设置；从 hub 读回的开关），指纹的 `models.daily` 里也有；每个 ccx 运行的记录里有 `subagent_switches`。

不花钱的自检：`python scripts/eval/r5.py daily-check --codex-home <评测 codex home>` 在临时文件夹里建一个日常 home，打印里面有什么（只列名字）然后删掉；带日常组的 `run --dry-run` 会列出要复制什么和各组的覆盖。

## 测量（来自 B3 计划；约 $20）

- **M1**（`codex_memories`、`clean`）：A = `ccx2daily`，B = `ccx2daily_nomem`，C = `ccx2daily_clean`。留出集 10 题 × 3 轮 + r5 10 题 × 2 轮：每组 50 个配对单元，每组约 $5。
- **M2**（`codex_lean_tools`）：D = `ccx2daily_leantools` 对同一个基线，题目相同。
- **决策规则（现在就定好）：** 四条全满足才改默认：right_B ≥ right_A − 1；输掉的配对（A 对、B 错；McNemar）≤ 2；没有哪道题 B 每轮都错而 A 至少对过一轮；子智能体每次运行的输入中位数降 ≥15%（M2：每次请求的前缀降约 3k）。有单侧缺失的配对或不干净的单元就判 Unknown，开关保持关。
- 统计功效有限：基线约 95% 时，50 对只能看出 ≥10 个百分点的下降。输掉 2–3 对的边界情况，只对该组再补 50 个单元（约 $5）。

命令（没有运行）：

```bash
python scripts/eval/r5.py daily-check --codex-home <评测 codex home>
python scripts/eval/r5.py run --taskset holdout --rounds 3 --arms ccx2daily,ccx2daily_nomem,ccx2daily_clean \
    --tag b3m1 --codex-home <评测 codex home> --budget 20 --dry-run
```
