# 对话板真机验收（2026-10-25）

[English](2026-10-25-board-acceptance.md) · 中文

验收对象：对话板（#66 `say` / `reply` / `board`，#74 每轮 hook `ccx turn`，#76 `--now` / `--resume`），用真实的
Codex 和 DeepSeek CLI，从一个 Claude Code 会话发起。版本：codex-cli 0.164.0、dsh 0.2.1-rc.3、Claude Code 桌面端（本会话，Opus）。

## 准备

- 一个用完即删的 git 项目，里面一个有 bug 的函数（`calc.py`：`average([])` 除零），`ccx project init`、
  `ccx board --init`，`CLAUDE.md` 只有 `@AGENTS.md`。
- 临时 `CCX_HUB`，放了和用户 hub 一样的“DeepSeek 不设上限”几行（`providers.deepseek`、`providers.deepseek-codex`、
  `pay_per_token.dsh` 的 `daily_usd = 1000`）；`CCX_DSH_BIN` 指向 `dsh.cmd`。
- 两个后台无头子会话：`ccx run --to codex --model gpt-6-luna --effort low --mode read ...` 和
  `ccx run --to dsh --model deepseek-flash --effort low --mode read ...`（“读 calc.py，说说 average 做什么”）。

## 结果

| 步骤 | 结果 |
|---|---|
| 本 Claude 会话 `ccx say --to codex --thread avg --resume <codex 运行>` | 贴出 #2，`from`/`via` = `claude:<会话>`；Codex 回答，贴为 #3 `codex -> claude:<会话>`、`re #2`、`via ccx-run:<id>` |
| `ccx say --to deepseek --thread avg --resume <dsh 运行>` | 贴出 #1；DeepSeek 回答，贴为 #4 `deepseek -> claude:<会话>`、`re #1` |
| 修完下面的问题后再问 DeepSeek | #5 / #6：DeepSeek 记得这条线，同意 Codex（空列表抛 ValueError） |
| `ccx board --all` | 6 条；`from` / `via` 都对，每条回复的 `reply_to` 指向它回的那条 |
| 用本会话 id 跑 `ccx turn --as claude`（Claude hook 实际跑的命令） | 第一轮推来 #3、#4、#6（长的只给首行 + `ccx board --thread avg`）；第二轮什么都不输出 |
| 项目里 `git status` | 没有 `.ccx/board.jsonl`（已忽略）；有 `context.md`、`journal.jsonl`（本来就要共享） |

## 发现并已修

- 用 `--resume` 时，推进无头会话的消息写的是“用 `ccx reply` 回复”。DeepSeek 照做，失败后在回答里写了“没法贴到对话板，
  因为这个环境的 PATH 里没有 `ccx`”（ccx 其实已经替它贴了）。现在 `--resume` 的消息改成“回答会替你贴成回复，别跑
  `ccx reply`”；重跑（#5 / #6）回答干净。加了测试检查这句话。

## 花费

| 谁 | 模型 | 次数 | token（新输入 / 缓存 / 输出） | 钱 |
|---|---|---|---|---|
| DeepSeek（dsh，按 token 付费） | deepseek-flash low | 3 | 6,974 / 93,696 / 2,836 | **$0.0030**（ccx 账本；真钱） |
| Codex（订阅） | gpt-6-luna low | 2 | 7,219 / 48,640 / 392 | 折合 API $0.0014，不额外花钱 |
| Claude（本组长会话） | — | — | `say` / `board` 命令不调模型 | 只有本会话自己的轮次 |

DeepSeek 控制台前后差额没看（这里看不到）；账本数字是 ccx 按 token 数估的。

## 没验证的

- **Codex 桌面端每轮 hook**：按要求跳过（H7：Codex 桌面端至今一条 hook 输出都没看到，ccx-memory 在查信任键）。未验证。
- **`ccx say --now` 推进开着的 Codex 桌面对话**：要项目里有开着的 Codex 桌面对话，没跑；只有假 `codex queue` 的测试。
- **DeepSeek 桌面端按 AGENTS.md 规则每轮读对话板**（`ccx board --as deepseek`）：没跑。无头运行说明 dsh 的 PATH
  里可能没有 `ccx`；那样的机器上这条规则没法生效。
- Claude hook 是用 hook 的 JSON 手动跑 `ccx turn --as claude` 验的，不是桌面端新开一轮。
