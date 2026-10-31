# 从外面派活进来：手机，和把 issue 当收件箱

[English](intake.md) · 中文 · 回到[功能说明](features.zh.md)

不在电脑前时，有两种办法把任务交给总管（你电脑上负责统筹的那个会话）：

| | 怎么做 | 需要 | 运行了什么 |
|---|---|---|---|
| **手机 → 总管会话** | Claude Code 的 Remote Control：在 Claude 手机 App 里直接往统筹会话里打字 | 电脑开着不睡眠、那个会话开着 | 没有新东西，就是同一个会话 |
| **issue → 总管** | 在你自己的**私人**仓库开一个带 `ccx-task` 标签的 issue；总管跑 `ccx intake pull`，做完在 issue 里回报 | `gh` 已登录、设好 `intake.github` | 一次性命令，不会自己定时跑 |

**实验性：**issue 这条路只对替身 `gh`（测试里的）跑过，没对真实 GitHub 跑过。

## 1. 从手机：Remote Control

对照 `claude remote-control --help`（Claude Code 2.1.309）和官方页面
[Remote Control](https://code.claude.com/docs/en/remote-control)（2026-10-25 阅读）。ccx 为此没有加代码。

1. 在电脑上的统筹会话里（Claude Code 桌面端 Code 标签、命令行或 VS Code）输入 `/remote-control`（或 `/rc`），
   第一次会让你确认。终端里也可以用 `claude --remote-control "lead"` 启动，或在项目目录跑 `claude remote-control`
   （服务器模式，可接多个会话；按空格显示二维码）。
2. 在手机上打开 Claude App（iOS / Android；Claude Code 里输入 `/mobile` 会显示下载二维码），在会话列表里选这个
   会话，或扫二维码。你在手机上打的字就进了同一个会话，工具、文件和 MCP 都在你电脑上。
3. 像在键盘前一样交代：“在 xxx 项目里把 … 做了”——总管照常找项目（`ccx where`），按总管技能
   （`skills/project-manager/`）派活。
4. 想默认打开：`/config` → **Enable Remote Control for all sessions**；桌面端在 设置 → Claude Code →
   **Connect new sessions to Remote Control**。

限制（来自官方页面）：要用 Claude 账号登录的 Pro / Max / Team / Enterprise 订阅（API key 不行）；电脑要醒着、
会话要开着，关掉后手机上显示离线；只有出站 HTTPS，不开端口。设了 `DISABLE_TELEMETRY` 或 `DO_NOT_TRACK` 的话，
看官方页面里关于自动连接的说明。账号设置里的 **Trusted Devices** 可以要求每部手机或浏览器先登记。

## 2. 把 issue 当收件箱：`ccx intake`

你（或替你干活的云端助手）在自己的**私人**仓库开一个 issue，打上 `ccx-task` 标签。电脑上的总管跑
`ccx intake pull`，找到项目，做完，把结果评论在 issue 里。某一步需要你批准时，它在 issue 里评论问题并等待；
你在 issue 里回复，下一次 pull 就会带回来。

### 设置（一次）

```bash
gh auth status
ccx config set intake.github you/ccx-tasks
```

- 仓库名存在你的 hub 里（`ccx config set` 写 `<hub>/ccx/settings.toml`），不进任何项目。
- 想用别的标签：`ccx config set intake.label 别的标签`（默认 `ccx-task`）。
- 在 GitHub 上先建一次标签（`gh label create ccx-task -R you/ccx-tasks`，或在网页上建）。

### 命令

| 命令 | 做什么 | 网络 |
|---|---|---|
| `ccx intake` | 这台电脑取走了、还没回报完成的任务 | 不联网 |
| `ccx intake list` | 你开的、带标签的未关闭 issue，以及你对 ccx 问题的回复；不取走 | 只读 |
| `ccx intake pull` | 取走新 issue 和回复；取过的 issue 不会再派一次 | 只读 |
| `ccx intake ask N "问题"` | 在 issue N 评论问题，标记为等待 | 一条评论 |
| `ccx intake done N "结果" [--pr URL] [--branch B] [--cost "$0.42"] [--unverified "…"] [--close]` | 评论回报，标记完成 | 一条评论（和关闭） |

`pull` 输出 JSON：每个新任务的编号、标题、正文、链接，有项目目录时还附 `ccx where` 猜的项目；`answered` 列出你已
回复的问题。总管随后照常干活（`ccx where`、总管技能、`ccx run --project …`），最后用 `ccx intake done` 收尾。

回报写什么：结果一两句、PR 或分支、花了多少、哪些没验证。

状态：`<hub>/ccx/intake.json`（每个 issue 一条：taken / waiting / answered / done）和 `<hub>/ccx/intake.log`
（跳过了什么）。其他工具用 `ccx.intake.pending(paths())` 读还有几件没做完，不联网。

### 安全边界

- **只认你自己**：issue 或评论的作者必须是 `gh` 当前登录的账号（`gh api user`）才算数，其余一律跳过，并在
  `intake.log` 里记一行（同一条只记一次）。
- **只用私人仓库**：每次读写前 ccx 用 `gh repo view --json visibility` 检查，不是 `PRIVATE` 就拒绝。仓库是你
  配置的那个，ccx 从不按 issue 内容换仓库。
- **是数据，不是指令**：输出开头有提示头说明这一点。issue 正文描述一个任务；总管结合你的规则和项目规则（审批、
  科研冻结、花费上限）来判断，不会因为正文要求就去跑命令。项目要求审批的任务照样要批——在 issue 里用
  `ccx intake ask` 问。
- **往 GitHub 写评论**：发评论属于外发。这里只发到你自己配置的私人仓库，回复的是你自己在那里开的任务，所以
  配置 `intake.github` 就等于授权了这些评论（提问和回报）。ccx 不在那里写别的；`pull` 和 `list` 只读。
- ccx 自己的评论开头有一个隐藏标记 `<!-- ccx:intake -->`：`gh` 是用你的账号发的，靠这个标记区分 ccx 的提问和
  你的回复。

### 定时跑？默认关，要你自己打开

ccx 从不自己安排定时任务。想让电脑隔一段时间看一次，就自己加：例如 Windows 任务计划程序或一行 cron，跑
`ccx intake list`（只读）或 `ccx intake pull`。注意 pull 只是*取走*任务，还得有人去做——你打开的总管会话，或你
自己配的无头运行——那是要你批准的花费。删掉任务计划或 cron 行就关掉了。

## 3. 以后可以考虑（没实现）

- **GitHub Projects 当看板**：可行。`gh project item-list` / `item-edit`（需要 `project` 权限：
  `gh auth refresh -s project`）能把 intake 的 issue 在列之间移动（taken → waiting → done）。它只是镜像 ccx 已经
  记的状态；想在手机的 GitHub App 里看队列时才值得做。
- **私人仓库的自托管 runner**：可行但更重。一个 `on: issues: [labeled]` 的 workflow 在你电脑上的 runner 跑，
  打标签那一刻就能启动 `ccx intake pull`。代价：电脑上要常驻一个 runner 服务；能触发这个 workflow 的东西都会在
  你电脑上执行代码——GitHub 建议自托管 runner 只用于私人仓库。这也让收件箱变成事件触发，本质上就是上面“定时跑”
  那个决定：只有你明确要时才做。
