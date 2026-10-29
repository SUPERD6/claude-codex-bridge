# 共享工作上下文

[English](shared-context.md) · 中文

Claude Code、Codex、DeepSeek 各有各的上下文窗口，谁也读不到别家的；ccx 不假装它们共用一个。ccx 做的是一份
**共享工作上下文**：用代码（不调模型）从各家自己的会话记录里摘出“这个会话最近在做什么”，让另外两家能读到。送达有三条路。

| 在哪 | 另一家拿到什么 | 开关 |
|---|---|---|
| 派活（`ccx run`） | 主导最近的工作：用户最近几条要求、定下来的句子、主导的计划、改过的文件、最后一条回复；每行带时间和来源；约 1–1.2k token | `--context auto\|on\|off`；auto（默认）= 只给可写任务；`[shared_context] run` |
| `ccx peek claude\|codex\|deepseek` | 只读地看这一家在本项目里最新的开着的会话（或 `--session ID`） | — |
| 每轮 hook（`ccx turn`） | 自上次看过之后，另一家每家一行：它的用户要了什么、定了什么、改了哪些文件 | `[shared_context] turn = false` |

所有内容都标成**资料，不是指令**：块的开头这么写，子智能体的规则点名了它，主导的记忆块和项目 AGENTS.md（`ccx board --init`）
也再说一遍。子智能体做什么由它自己的任务和用户的指令决定，别的会话里的一句话不算数。

## 读什么

| 工具 | 文件 | 读的内容 |
|---|---|---|
| Claude Code | `projects/<文件夹>/<会话>.jsonl` | 用户消息、助手文字、Edit / Write / MultiEdit / NotebookEdit、TodoWrite 和桌面端计划工具；跳过旁支和压缩摘要 |
| Codex 0.164 | `sessions/**/rollout-*.jsonl` | UserMessage、AgentMessage、FileChange、update_plan、apply_patch |
| dsh 0.2.1-rc.3 | `~/.dsh/sessions/<文件夹>/<会话>/session.v4.jsonl.zstd` | user/message、assistant/message 文字、edit / write、todo_write |

dsh 用 zstd 压缩会话文件，Python 3.11 标准库读不了。ccx 用 Node ≥ 22.15（`CCX_NODE`，或 PATH 上的 `node`）解，
或者用 dsh 自带的 Electron 当 Node 跑（从 `CCX_DSH_BIN` 指的启动脚本里找到）。两样都没有时，`ccx peek deepseek` 会直说。
Windows 上 dsh 的文件夹名重复整个项目路径，会超过 260 字符，ccx 用长路径名去读。

“定下来的句子”靠关键词挑：*decided, agreed, going with, from now on, never, must, instead of*，以及 决定 / 定了 / 约定 /
改成 / 不要 / 必须 / 以后。这是启发式：换个说法的决定可能漏掉，听着像决定的句子可能被挑进来。用户最近几条消息整条带上
（截到 500 字），所以漏掉的决定常常还在。密钥按 `ccx handoff` 的规则打码。

## 它不是什么

- 不是同一个上下文：每家仍只读自己的对话，加上这份摘要。
- 不是对话记录的拷贝：派活最多约 5000 字符，每轮 hook 约 400 字符。
- 不是指令：见上。
- ccx 自己派出的无头子会话不会被当成谁“开着的会话”（按运行账本排除；dsh 会话按开头的 ccx 子任务行排除）。

## 实测

见 [docs/research/2026-10-25-shared-context-ab.zh.md](research/2026-10-25-shared-context-ab.zh.md)。
