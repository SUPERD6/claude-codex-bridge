# Gemini CLI 能不能当组长？（2026-10-25）

[English](2026-10-25-gemini-lead.md) · 中文

还没做。这份说明写清要做什么、工作量多大，由用户决定做不做。写这份说明的机器上没装 Gemini CLI，下面没有一项真跑过。

## ccx 对组长的要求，和 Gemini CLI 有什么

组长就是适配器里 `can_lead = True` 的那家：对话开始时 ccx 把共享记忆给它看，并能读它的对话来记花费、做交接、发每轮提示。`--as`（`ccx mem delta`、`ccx fresh`、`ccx lead`）现在从适配器读取可选值（`ccx.agents.leads()`），所以登记上只要改这一个标志。

| 需要 | Claude Code / Codex 现在 | Gemini CLI（2026-10-25 读的文档） |
|---|---|---|
| 能加上下文的开局 hook | SessionStart → `ccx mem delta` | **有。**`SessionStart`（source 为 startup / resume / clear），输出 `hookSpecificOutput.additionalContext`：交互模式“插入为历史里的第一轮”，非交互模式“加在用户提示前面”。geminicli.com/docs/hooks/reference，最后更新 2026-04-10 |
| 每轮 hook（对话过长提示） | UserPromptSubmit → `ccx lead --hint` | **有。**`BeforeAgent`：additionalContext “只追加到这一轮的提示” |
| hook 配在哪 | `~/.claude/settings.json`、`~/.codex/config.toml` | `~/.gemini/settings.json`（用户级）、`.gemini/settings.json`（项目级），`hooks.<事件>[].hooks[]`，`type: "command"`，`timeout` 单位毫秒（geminicli.com/docs/hooks，最后更新 2026-04-13） |
| 说明文件 | CLAUDE.md / AGENTS.md | GEMINI.md（适配器里已写） |
| 读它的对话 | 会话 JSONL 文件 | **不知道**：没查 Gemini CLI 把对话存在哪、什么格式 |
| 额度 | 两家都能读 | 读不到（已经是 `quota_readable = False`） |

文档的提醒：页面横幅写着 2026-06-18 起，免费和 Google One 用户的 Gemini CLI 已被 Antigravity CLI 取代。用户实际会用哪一个，决定这件事值不值得做。ccx 的适配器是对着 Gemini CLI 0.65.0 的源码写的。

## 要做的事，分块

1. **开局 hook + 记忆（小，一个 PR）：**`ccx sync` 往 `~/.gemini/settings.json` 写一个带标记的 SessionStart 条目；`ccx mem delta --as gemini` 输出 Gemini 要的 JSON（`{"hookSpecificOutput": {"additionalContext": "..."}}`），而不是纯文本；doctor 检查这一条；`can_lead = True`、填上 `start_hook`；用假 Gemini 测。约半天。
2. **每轮提示（小）：**一个 `BeforeAgent` 条目 → `ccx lead --hint --as gemini`，同样的 JSON。几个小时，但提示要读组长自己的对话，所以要等第 3 块。
3. **读它的对话（中）：**找到 Gemini CLI 的对话文件，写 `lead_events`（每轮 token）和给 `ccx fresh` / `ccx handoff --from-transcript` 用的读取。一到两天，而且要有真 CLI 才看得到文件。
4. **技能怎么进 Gemini（不知道）：**组长靠 agent-delegate 技能知道怎么派活。Gemini CLI 是从某个文件夹加载技能，还是只能经 GEMINI.md 或扩展，没查。
5. **真机检查：**安装、登录，把 1–3 各跑一次（Gemini 当组长派只读和可写子任务），把版本写进 `tested_version`。

只做 1–2，Gemini 组长就能用上共享记忆；不做 3，它自己的花费不进账本，从它交接要手写（`ccx handoff`）。
