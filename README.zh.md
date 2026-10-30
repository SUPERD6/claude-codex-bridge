<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="relayline（命令 ccx）：几个编码智能体互为主导和子智能体；一次真实运行：选了 Codex luna/low，一次完成，已验收，$0.0023" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/relayline/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/relayline/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/relayline/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/relayline"></a>
</p>

<p align="center"><a href="README.md">English</a> · 中文 · <a href="https://superd6.github.io/relayline/zh/">网站</a></p>

# relayline

**在 Claude Code 里，把一件能验收的杂活交给跑便宜模型的 Codex。** ccx 自己重跑你的验收命令，另一家的模型审查改动，
这次运行花了多少记进账本，想撤回只要一条命令。反过来也行（Codex 或 DeepSeek 当主导、Claude Code 接活），大家共享记忆和
工作上下文。命令是 `ccx`，只用 Python 标准库。

## 和自己做、和 Claude Code 自带的子智能体比

**留出集（hc1，2026-10-29）：** 在做 ccx 时没用过的 10 个任务上（× 3 轮，sonnet 当主导，隐藏测试），ccx 未见正确率更差
（29/30，对 29/30 和 27/28），每次成功比自己做、比自带子智能体的默认用法都便宜，但用时约为自己做的 3 倍
（[报告和局限](docs/research/2026-10-29-hc1-holdout.zh.md)）。**开发集**（其余几行）：第 5 轮，本仓库 10 个真实改动 × 2，
sonnet 当主导，隐藏测试，子智能体是 Codex gpt-6-luna low。内置子智能体：每一轮都算，包括精简做法的 builtin2；ccx：第 5 轮修完之后的四轮（修之前的第一轮是
17/20、每次成功 $0.248）。

| | 主导自己做 | Claude Code 内置子智能体 | ccx → Codex |
|---|---|---|---|
| 做对 | 19/20（一轮） | 17–19/20（三轮） | 18–20/20（四轮，r5e–r5h） |
| 每次成功的花费 | $0.211 | $0.114–0.202 | $0.116–0.135 |
| 用时中位数 | 94 秒 | 276–316 秒 | 236–267 秒 |
| [留出集](docs/research/2026-10-29-hc1-holdout.zh.md)（10 个任务 × 3）：做对、每次成功、用时 | 29/30、$0.090、21 秒 | 27/28、$0.103、123 秒（默认用法） | 29/30、$0.063、61 秒 |

- **花费。** 留出集上 ccx 每次成功比自己做低约 30%，比内置子智能体的**默认用法**低约 39%；只看其中 5 个别的仓库的任务
  （干净的一半：本仓库自己的任务，答案可能就在 ccx 的代码里）低约 15% / 42%。精简做法的内置子智能体（builtin2，给内置
  子智能体用 ccx 的精简做法）不在那次运行里：开发集上它每次成功 **$0.114**，比我们最近一轮 ccx（r5h，**$0.135**；ccx 的
  范围是 $0.116–0.135）便宜，所以两种派活方式还分不出胜负。在开发集那些较大的任务上，两者每次成功都比主导自己做便宜。
- **速度：ccx 比自己做慢**，留出集上约 3 倍（61 秒对 21 秒；内置子智能体默认用法 123 秒），开发集上是主导自己做的 2.5–2.8 倍；第 1 轮的小任务约 3 倍（34 秒对 11 秒），第 3 轮更难、
  更含糊的小包任务（主导是新开的短对话）约 4.5 倍（63 秒对 14 秒）：合起来 2.5–4.5 倍。小一些的任务上，总花费和自己做相比第 1、4 轮基本持平，第 3 轮更贵（每次成功 $0.071 对 $0.045）。
- **ccx 比内置子智能体多给的：** 活跑在另一家的模型和额度上；ccx 自己重跑你的 `--check`，不只信报告；另一家审查改动；
  每次运行的花费进账本；`ccx undo` 撤回一次运行。
- **跨厂商一本账：** 每次子智能体运行以及它自己开的子会话，Claude 和 Codex 记在同一本账上（2026-10-30 用 codex-cli 0.164.0 实测：通过 `--parallel` 要求的 Codex 子智能体用 `spawn_agent` 开了 3 个子会话，账本里这次运行的总数逐项恰好等于父会话加 3 个子会话）。Claude Code 自己有 `/context` 和 `/cost` 看它自己这个会话；ccx 多给的是两家共用的一本账，加上主导每轮重读内容的分部分明细（从主导自己的会话文件读，不在账本里；`ccx lead --breakdown`，以及 `ccx ui` 的“实测与 token 去向”页面）。
- **局限：** 留出集只有 10 个任务、只测了 sonnet 主导，金额是 API 等价价，“未见更差”不是统计意义上的非劣检验。开发集的
  任务也在修 ccx 时用过；主导自己做只跑了第一轮；第 5 轮早于干净环境检查。全部数字（包括不利的，
  以及单个功能的最好情况 A/B）：[docs/measured.zh.md](docs/measured.zh.md)。

**不用账号先看看：** `ccx demo` 用临时目录里编好的项目、运行和花费打开 `ccx ui`（离线可用，不用登录 Claude
或 Codex，不动你自己的设置）。

## 快速开始

```bash
claude plugin install relayline --marketplace SUPERD6/relayline   # Claude Code 里的技能和 hook（2.1.275+）
pipx install git+https://github.com/SUPERD6/relayline             # ccx 本体，给终端和 Codex 用
ccx setup                    # 向导：每一步都说明，改东西前先问
ccx run --to codex --mode read "Summarise README.md in three lines for a new user: what this project does, how to install it, and the first command to try"
```

最后一行是只读的第一次试用：Codex 读这份 README，用最便宜的模型三行作答（命令和英文版一致。你在自己的终端里用 `--to`
点名时，再小的任务也会派出去，只在 stderr 提示一句自己做更省；主会话代为调用时，太小的任务仍会被建议自己做）。`ccx setup` 问到的 hub 是你自己的一个文件夹，放共享记忆、技能和每次运行的记录。

然后是 ccx 真正要做的事：一件有验收命令、能判断做没做完的杂活（在你的项目里，用你自己的测试命令；`--check` 里点名的测试文件必须已经存在，否则 ccx 在启动子智能体之前就会停下）：

```bash
ccx run --to codex --check "python -m pytest -q tests/test_dates.py" --review on "parse_date() rejects ISO dates that end in Z; make it accept them and add a case for it to tests/test_dates.py"
ccx undo <run_id>            # 不想要：先显示会还原什么；加 --apply 才真还原
```

只有 ccx 自己跑你的 `--check` 通过了，这次运行才算过；`--review on` 让另一家的模型读改动；JSON 结果里有运行 id、
验收、审查和花费。可能改文件、却没给 `--check` 的运行，会在 stderr 提醒一行。

需要 Python 3.11+，以及登录好的 `claude` 和 `codex` 命令行；DeepSeek（`dsh`，或 `DEEPSEEK_API_KEY` 里的密钥）可选。
`ccx -h` 列出你自己会敲的命令（run、resume、show、q、undo、ui 等）；`ccx -h --all` 还列出智能体之间互相调用的（board、say、reply、peek）、进阶和维护用的，开发者用的（trial、ab、bench 等）放在最后。

## 其他能做的

和 [docs/features.zh.md](docs/features.zh.md) 里的七件事一致，每件一句：（1）Claude Code、Codex、DeepSeek 互为主导和
子智能体；（2）模型之间直接对话（`ccx ask`、`ccx discuss`、留言板）；（3）共享记忆和工作上下文；（4）拆活，按难度和
花费给每块选人；（5）子智能体精简启动，`ccx lead` 看主导每轮重读多少；（6）验收、另一家审查、每次运行都记对错；
（7）不丢可控（`ccx undo`、`--worktree`、按钮要再点一次确认的 `ccx ui`）。

**换主导。** 前一半是 Claude Code 做的，后面想交给 Codex（或反过来）？在 `ccx ui` 的项目页点“交给 Codex 继续”/
“交给 Claude 继续”，再点一次确认，就会为这个项目运行 `ccx handoff`：把做完了什么、定了什么、下一步写进项目（当前主导的
对话文件在的话就从它整理），并给你一行话，在那个工具里打开这个项目时贴给它。任务时间线会显示每段时间由谁主导。

<p align="center"><img alt="演示动画：ccx route 选出 codex:gpt-6.1-sol:medium，ccx run 一次完成并由 ccx 重跑验收命令，ccx verify 记下结论" src="docs/assets/demo.svg" width="100%"></p>

## 谁和谁配合

| | 当主导 | 接活 |
|---|---|---|
| Claude Code | 能 | 能 |
| Codex | 能 | 能 |
| DeepSeek（`dsh`，或经 Claude Code；接活也可经 Codex） | 能 | 能 |
| Gemini CLI；经 Claude Code 的 Kimi、GLM、Qwen、OpenRouter | 不能 | 已适配，没真跑过 |

所有“能”都在一台 Windows 电脑上真跑过；macOS 和 Linux 只在 CI 里跑。现在是 v0.5，仍在开发中：
哪些验证过、怎么验证的，见 [docs/STATUS.zh.md](docs/STATUS.zh.md)。

## 更多

| 页面 | 里面有什么 |
|---|---|
| [做什么、怎么做](docs/features.zh.md) | 七件事的细节、`ccx ui`、一个从头到尾的例子、共享的东西放在哪、分级、安全边界 |
| [安装和命令](docs/install.zh.md) | 从源码安装、接入你已有的配置、全部命令 |
| [实测](docs/measured.zh.md) | 全部测量和局限（留出集运行、第 5 轮对比、单个功能的最好情况 A/B）、省了多少怎么估、核对过的外部事实 |
| [共享工作上下文](docs/shared-context.zh.md) · [留言板](docs/board.zh.md) | 开着的会话之间共享什么、怎么共享 |
| [常见问题和同类项目](docs/faq.zh.md) | 花费、订阅、安全、哪些工具能用；和同类项目有什么不同 |
| [设计](docs/DESIGN.zh.md) · [决策](docs/DECISIONS.md) · [变更](CHANGELOG.md) | 内部 |

**和同名项目不是一个东西：** relayline 原名 `claude-codex-bridge`，但不是
[CCB](https://github.com/SeemSeam/claude_codex_bridge)，也不是 OpenAI 官方的
[codex-plugin-cc](https://github.com/openai/codex-plugin-cc)（[区别](docs/faq.zh.md#同类项目对比)）。

## 安全、参与贡献、许可

ccx 会运行什么、可能改什么、怎么报告问题：[SECURITY.md](SECURITY.md)。参与贡献（测试、规则、给别的智能体命令行加适配器）：
[CONTRIBUTING.md](CONTRIBUTING.md) 和[行为准则](CODE_OF_CONDUCT.md)。MIT 许可，见 [LICENSE](LICENSE)。
