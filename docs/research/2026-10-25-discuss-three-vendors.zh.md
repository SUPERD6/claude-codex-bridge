# 三家厂商一起讨论一个决定：第一次真跑（2026-10-25）

[English](2026-10-25-discuss-three-vendors.md) · 中文 · ccx main `485d322` · codex-cli 0.164.0 · claude 2.1.309 ·
DeepSeek 经 Claude Code（`--bare`）· Windows 11 · 数据：[data/2026-10-25-discuss-three-vendors.json](data/2026-10-25-discuss-three-vendors.json)

**结论：能用（n = 1）。**Codex 出方案、Claude 挑错、DeepSeek 裁判；3 轮、7 次发言，花 $0.016、85 秒。裁判是独立的第三家，每一条带标签的内容都读出来了，预估也在要求的 2 倍以内。只跑了一次：这说明机制在真实模型上能跑通，不说明建议质量普遍如何。

## 怎么跑的

在临时 `CCX_HUB` 里（不碰用户的账本和路由数据）运行 `ccx discuss --with codex,claude,deepseek --tier T1 --question-file q.txt`，在 #38（预估）、#42（格式）、#51（档位）合并之后。T1 即 Codex 用 `gpt-6-luna low`、Claude 用 `haiku low`、DeepSeek 用 `deepseek-flash low`。

问题有已知答案：一个命令行工具要写一个被网页轮询的小 JSON 文件，要在 Windows、macOS、Linux 上都对。(A) 直接写，(B) 先写临时文件再 `os.replace`，(C) 临时文件再 `os.rename`，(D) 加锁文件。正确答案是 (B)：Windows 上目标已存在时 `os.rename` 会失败，(A) 会让读者看到半个文件，(D) 要所有读者都守锁。

## 验收

| 检查 | 要求 | 结果 |
|---|---|---|
| 裁判独立 | `judge_independent = true` | true（三家） |
| 裁判的标签都解析成功 | RECOMMEND + `[consensus]` / `[disagreement]` / `[reason]` | 四样都有：3 条共识、3 条分歧、2 条理由；没有一回合不守格式，没用上格式提醒 |
| 预估 | 实际在预估的 0.5–2 倍内 | dry-run 预估 $0.0094–0.0213（模型估）；实际 $0.0163 = 最大预估的 0.77 倍，3 轮都跑满了 |
| `ccx ui` | 能显示 | 讨论页画出了 7 次发言和结论（在本机页面上用浏览器看过） |
| 花费上限 | 本会话 ≤ $1；DeepSeek 当天 ≤ $1 | 一共 $0.016，DeepSeek $0.0017 |

## 过程

| 回合 | 智能体 · 模型 | $ | 秒 | 输入（其中缓存）/ 输出 token | 说了什么 |
|---|---|---|---|---|---|
| 第 1 轮出方案 | Codex · luna low | 0.0021 | 6 | 19.5k (0) / 240 | 选 (B)，Windows 共享冲突时短暂重试，读者保留上次的有效状态 |
| 第 1 轮挑错 | Claude · haiku low | 0.0043 | 20 | 13.0k (0) / 3.3k | 反对：重试几次、用尽怎么办；替换前要 `fsync` |
| 第 2 轮修改 | Codex | 0.0007 | 6 | 20.1k (16.1k) / 266 | (B) + `mkstemp`、`fsync`、有限重试、用尽时保留旧文件 |
| 第 2 轮挑错 | Claude | 0.0027 | 15 | 13.9k (6.5k) / 2.2k | 反对：要具体数字、过期怎么让人看见、临时文件清理 |
| 第 3 轮修改 | Codex | 0.0021 | 6 | 19.4k (0) / 232 | 0.5 秒内最多 5 次，JSON 里带时间戳，清理旧临时文件 |
| 第 3 轮挑错 | Claude | 0.0028 | 17 | 14.8k (6.5k) / 2.2k | 反对：重试预算没实测、`mkstemp` 建的是 0600 文件、多个写入者 |
| 裁判 | DeepSeek · flash low | 0.0017 | 14 | 7.9k (3.8k) / 1.8k | RECOMMEND (B) 及细节；3 共识、3 分歧、2 理由 |

建议是对的；挑错方提的都是真问题，出方案的一方也接受了（唯一临时文件名、`fsync`、重试用尽怎么办、过期时间戳）。

## 下一步值得改的（这次没做）

1. **挑错方一直不认可。**每一轮它的 `[must]` 都是新的实现细节（重试次数、文件权限、多个写入者），没有一条说明选 (B) 是错的，所以每次都跑满 3 轮。说明里写的 `[must]` 是“会让这个选择变错的”，便宜模型没守住。可以试：让挑错方和上一轮比较，剩下的只是细化（`[note]`）时就认可；再多跑几次统计“第几轮认可”。
2. **不同路线的启动开销不一样。**DeepSeek 经 Claude Code `--bare` 读了 7.9k token，Claude Code 自己是 13–15k，Codex 是 19–20k；预估表对所有经 Claude Code 的路线都用 Claude Code 的数，provider 会略微估高（这个价位下无所谓）。
3. **Claude 挑错方用中文回答**，其他两家用英文，大概是 Claude Code 加载了用户自己的说明文件。不影响解析（标签是 ASCII），但页面上中英混杂。

## 没跑的（I5）

这台机器上没装 Gemini CLI 和 DeepSeek Harness（`dsh`），也没有 Kimi（`MOONSHOT_API_KEY`）、GLM（`ZAI_API_KEY`）、Qwen（`DASHSCOPE_API_KEY`）、OpenRouter（`OPENROUTER_API_KEY`）的 key，所以都没跑：**Gemini：未跑。dsh：未跑。Kimi、GLM、Qwen、OpenRouter：未跑。**DeepSeek 经 Claude Code 在上面当裁判跑过。
