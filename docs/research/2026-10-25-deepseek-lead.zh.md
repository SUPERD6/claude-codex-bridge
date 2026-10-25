# DeepSeek 当组长、`dsh` 当子智能体：真跑记录（2026-10-25）

[English](2026-10-25-deepseek-lead.md) · 中文 · DeepSeek Harness 桌面版 0.2.1-rc.3（自带的 `dsh`，ccx 从卸载注册表找到）·
Claude Code 2.1.309 · codex-cli 0.164.0 · Windows 11 · 临时 `CCX_HUB`

都在一个小仓库上跑（`calc.py` 里 `add` 写成了 `a - b`，加 `test_calc.py`），T1（DeepSeek `deepseek-flash low`、Codex `gpt-6-luna low`、Claude `haiku low`）。DeepSeek 经 ccx 花了约 $0.01，另加两个组长会话本身（最多几美分），在当天 $1 以内。

## `dsh` 当子智能体（I5）

| 运行 | 结果 | $ |
|---|---|---|
| 只读：哪个测试失败、为什么 | 完成，答对；只读沙箱生效（pytest 写不了临时目录） | 0.0023 |
| 可写，被自动续接到只读那次的会话 | **blocked**：会话保持只读，改不了文件 | 0.0016 |
| 可写，新会话（`--new`），`--check "python -m pytest -q -p no:cacheprovider"` | 完成；`add` 改对；ccx 自己重跑验收也通过 | 0.0010 |
| 续接这个可写会话：加 `sub` 和测试 | 在同一会话里完成（同一个 `session-…`）；3 个测试通过。随后 ccx 的独立审查把 `sub` 里的 `return a - b` 误报为错误，dsh 核对后说明是误报 | 0.0013 + 0.0009 |

据此修了：ccx 不再跨“只读/可写”续接 dsh 的会话（它的权限在会话开始时由 `DSH_PERMISSION_MODE` 定下）。

## DeepSeek 当组长

| 组长 | 它跑的命令 | 账本 | 说明 |
|---|---|---|---|
| `dsh --profile headless`，`DSH_PERMISSION_MODE=workspace-write` | `ccx run --to codex ...` | – | **失败**：写 hub 的运行目录报 `[WinError 5]`；提权要审批，无头 dsh 没有审批通道 |
| 同上，`danger-full-access` | `ccx run --to codex ...` | caller `dsh`，caller_vendor `deepseek`，完成 | Codex 没打开文件就回答了；同样的任务从 Claude Code 组长派出也一样，所以是 luna low 在只读任务上偷懒，不是 dsh 的问题 |
| `claude -p --bare --model deepseek-flash`（ANTHROPIC_BASE_URL 指向 DeepSeek） | `ccx run --to claude ...` | caller `deepseek`，caller_vendor `deepseek` | 第一次：Claude 子智能体报 “Not logged in”，因为 bare 组长把 `CLAUDE_CODE_SIMPLE` 传下去了。修好后第二次完成，Claude 读了文件、答对，按 Claude（`haiku`）计价 |

顺带看到的：dsh 给它运行的命令设 `DSH_SESSION_ID`、`DSH_PROFILE`、`DSH_HOME`、`DSH_SHELL`；Windows 上它的 shell 是 Windows PowerShell 5.1；把多行任务当参数传给 `dsh.cmd` 会在第一行处截断（要用 stdin，`-`）。dsh 0.2.1-rc.3 没有命令 hook：它读 `$DSH_HOME/AGENTS.md`、`<agentsHome>/AGENTS.md` 和项目里的 `AGENTS.md` / `CLAUDE.md`。

## 没跑的

跑 DeepSeek 模型的 Codex 当组长（靠 config.toml 的 `model_provider` 或 `CCX_LEAD` 认出）；dsh 桌面版自己的会话当组长（只跑了无头模式）；Gemini CLI（用户决定不装）；Kimi、GLM、Qwen、OpenRouter（没有 key）；macOS 和 Linux。
