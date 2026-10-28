<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="relayline（命令 ccx）：几个编码智能体互为组长和子智能体；一次真实运行：选了 Codex luna/low，一次完成，已验收，$0.0023" src="docs/assets/banner-light.svg" width="100%">
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

**一个承诺：AI 编程少花钱。** 让 Claude Code、Codex、DeepSeek 组成一个互相派活的团队：每块活交给最可能做对的
最便宜的那一家，每块活都有人验收，大家共享记忆和工作上下文。命令是 `ccx`，只用 Python 标准库。

## 四根柱子

| | ccx 做什么 | 实测 |
|---|---|---|
| **省钱** | 每块活按“最便宜、又最可能做完”选智能体、模型和强度（不值得派就让你自己做）；子智能体精简启动；`ccx lead` 显示组长每轮重读了多少。 | 带上组长最近工作的派活，**总花费少 63%**，返工 0 次（不带时 29 次）（[A/B](docs/research/2026-10-25-shared-context-ab.zh.md)） |
| **更准** | ccx 自己重跑验收命令，可请另一家审查改动，每次运行都记对错、用来校准选模型。 | 带共享工作上下文**一次做对 36/36，不带 7/36**（[A/B](docs/research/2026-10-25-shared-context-ab.zh.md)） |
| **分工** | 5 个问题打出难度，选智能体、模型、强度；组长只看总结；三家谁当组长都行。 | 派出去后组长**每个任务都少 1 次请求，21/21**（[七核心 A/B](docs/research/2026-10-24-seven-cores-ab.zh.md)） |
| **共享** | 项目记忆和个人记忆、组长之间交接、共享工作上下文（`ccx run --context`、`ccx peek`）、开着的会话互相留言的留言板。 | 项目记忆送到子智能体手里并被照做：**有记忆 9/9 做对，没有 0/9**（[七核心 A/B](docs/research/2026-10-24-seven-cores-ab.zh.md)） |

**看数字要连同局限一起看。** 这些都是一台电脑上的小型受控任务。共享工作上下文的 A/B 按设计就是这个功能的最好情况。
只是把小任务派出去，总花费基本持平（比值 1.02，token 3.3 倍，慢约 23 秒）；换成真实的长对话组长能省多少，目前是外推、
还没测。全部数字（包括不利的）：[docs/measured.zh.md](docs/measured.zh.md)。

## 快速开始

```bash
claude plugin install relayline --marketplace SUPERD6/relayline   # Claude Code 里的技能和 hook（2.1.275+）
pipx install git+https://github.com/SUPERD6/relayline             # ccx 本体，给终端和 Codex 用
ccx setup                    # 向导：每一步都说明，改东西前先问
ccx run --to codex --mode read "用三行总结 README.md"
```

需要 Python 3.11+，以及登录好的 `claude` 和 `codex` 命令行；DeepSeek（`dsh`，或 `DEEPSEEK_API_KEY` 里的密钥）可选。
`ccx -h` 先列常用命令。

<p align="center"><img alt="演示动画：ccx route 选出 codex:gpt-6.1-sol:medium，ccx run 一次完成并由 ccx 重跑验收命令，ccx verify 记下结论" src="docs/assets/demo.svg" width="100%"></p>

## 谁和谁配合

| | 当组长 | 接活 |
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
| [实测](docs/measured.zh.md) | 全部测量和局限、省了多少怎么算、核对过的外部事实 |
| [共享工作上下文](docs/shared-context.zh.md) · [留言板](docs/board.zh.md) | 开着的会话之间共享什么、怎么共享 |
| [常见问题和同类项目](docs/faq.zh.md) | 花费、订阅、安全、哪些工具能用；和同类项目有什么不同 |
| [设计](docs/DESIGN.zh.md) · [决策](docs/DECISIONS.md) · [变更](CHANGELOG.md) | 内部 |

**和同名项目不是一个东西：** relayline 原名 `claude-codex-bridge`，但不是
[CCB](https://github.com/SeemSeam/claude_codex_bridge)，也不是 OpenAI 官方的
[codex-plugin-cc](https://github.com/openai/codex-plugin-cc)（[区别](docs/faq.zh.md#同类项目对比)）。

## 安全、参与贡献、许可

ccx 会运行什么、可能改什么、怎么报告问题：[SECURITY.md](SECURITY.md)。参与贡献（测试、规则、给别的智能体命令行加适配器）：
[CONTRIBUTING.md](CONTRIBUTING.md) 和[行为准则](CODE_OF_CONDUCT.md)。MIT 许可，见 [LICENSE](LICENSE)。
