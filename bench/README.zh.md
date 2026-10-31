# 公开基准：自己重跑我们的数字

[English](README.md) · 中文 · 我们公布的数字：[docs/measured.zh.md](../docs/measured.zh.md) 和
[留出集报告（hc1）](../docs/research/2026-10-29-hc1-holdout.zh.md)

> **留出集从此不再是留出集。** 这 10 道题在 hc1 那一轮（2026-10-29）之前一直没用来开发 ccx。现在公开在这里，
> 任何人（包括我们）都可以对着它调，之后训练的模型也可能见过它。以后在它上面跑出的数字只算"重跑"，不算新的留出结果。
> 我们下一轮的头条结论会另建一套新的留出集。

## 这是什么

relayline（命令 `ccx`）让 Claude Code 把活交给 Codex（反过来也行），每次派活留一张收据。这个基准测的是：这样派活
是否和智能体自己做一样对、而且更省。下文用词：**主导**（lead）是接到任务的 Claude Code 智能体；**组**（arm）是一种
干活方式（主导自己做，或派出去）；**单元**（unit）是一题 × 一组 × 一轮；**tag** 是一次运行（它的全部单元）的名字。

20 个真实的代码改动，每个都有题面、起点和决定对错的隐藏测试：

| 题集 | 题目 | 用途 | 已公布的运行 |
|---|---|---|---|
| `holdout`（hc1） | 10 道：本仓库 5 道，[humanize](https://github.com/python-humanize/humanize) 4 道，[itsdangerous](https://github.com/pallets/itsdangerous) 1 道 | README 头条（10 题 × 3 轮） | [results/hc1.jsonl](results/hc1.jsonl) |
| `r5`（开发集） | 本仓库 10 道 | 调 ccx 用：只算信号，不算结论 | [results/r5-dev.jsonl](results/r5-dev.jsonl) |

每道题 = 某个已合并提交的父提交上的仓库；题面写清哪里错了或缺了什么、测试要用的名字，但不给测试的输入和期望值；
隐藏测试就是那个提交自己的测试文件。[tasks/](tasks/) 里每题一个文件（题面、提交、测试文件、准确的 pytest 命令）。

"组"（arm）指谁来干活。主导是一个全新的无界面 Claude Code（`claude -p`，Sonnet，medium effort）：

| `--arm` | r5.py 里的组 | 主导…… | 需要 |
|---|---|---|---|
| `self` | `self` | 自己改 | Claude Code |
| `ccx` | `ccx2` | 通过 `ccx run` 交给 Codex（先用最便宜的 Codex 模型，开审查，带针对性的 `--check`） | Claude Code、Codex、一个专用 Codex 目录 |
| `builtin` | `builtin` | 交给 Claude Code 自带的子智能体（Haiku 干活） | Claude Code |

真正干活的是 [scripts/eval/r5.py](../scripts/eval/r5.py)；[run.py](run.py) 只负责选参数、打印表格。每个单元都在
自己的环境里跑：新的仓库副本、自己的临时 HOME / hub / git 身份，主导不带你的设置、hooks、CLAUDE.md 和记忆，
Claude 的 Read / Edit 工具不能读你真实的主目录。**这不是沙箱**：智能体的 shell 命令（Claude 的 Bash、Codex 的
shell）仍然能读你的文件，审计只记录它们提到的路径，不拦。介意的话请在单独的系统账户或虚拟机里跑。第一个单元之前 r5.py 会先检查机器，有任何会让数字不公平的情况就拒绝开跑（见"拒绝开跑时"）。

## 安装

需要 git、Python 3.11+、已登录的 [Claude Code](https://docs.claude.com/en/docs/claude-code)（PATH 里有 `claude`）。
`ccx` 组还需要 [Codex CLI](https://github.com/openai/codex)。**不需要**安装 ccx：评测直接从这个检出里运行它。

```bash
git clone https://github.com/SUPERD6/relayline.git
cd relayline
python -m venv .venv
```

激活它（`source .venv/bin/activate`，Windows 上是 `.venv\Scripts\activate`），然后：

```bash
python -m pip install "pytest>=9" freezegun
```

保留完整 git 历史（不要 `--depth`）：本仓库的题从旧提交开始。外部仓库的题会在开跑时从 GitHub 克隆 humanize 和
itsdangerous（只需要联网一次）；它们的测试用同一个 Python 跑，这个 Python 里不能装 `humanize` 或 `itsdangerous`。

## 跑 `self` 组（最便宜）

先跑一个单元，确认环境（约 $0.03–0.20，`--dry-run` 估 $0.20；另加几美分的 canary：开跑前一个很小的 Haiku 请求，检查隔离是否生效）：

```bash
python bench/run.py run --set holdout --arm self --tasks hz-intword-carry
```

再跑整个留出集一轮（10 个单元；按 hc1 实测约 $0.9，每个中位 21 秒；`--dry-run` 按开发集均值估约 $2，所以下面
的预算留了余量）：

```bash
python bench/run.py run --set holdout --arm self --budget 3
```

`--dry-run` 只打印排程和费用估算，什么都不跑。默认一次跑一个单元（`--jobs 1`），免得互相拖慢计时；hc1 是两个
同时跑的，要和它对齐就用 `--rounds 3 --jobs 2`。`--` 之后的参数原样交给 r5.py（`python scripts/eval/r5.py run -h`）。

## 跑 `ccx` 组

Codex 不能看到你自己的设置，所以评测用一个单独的 Codex 目录，你自己在里面登录一次：

```bash
mkdir ~/codex-eval-home
CODEX_HOME=~/codex-eval-home codex login
```

（PowerShell：`$env:CODEX_HOME = "$HOME\codex-eval-home"; codex login`，然后关掉这个窗口。）再传它的绝对路径：

```bash
python bench/run.py run --set holdout --arm ccx --codex-home /absolute/path/to/codex-eval-home --budget 3
```

`builtin` 组不需要额外准备（`--arm builtin`）。要比较几组，就一次跑完，让它们的单元在同一时段交错：
`--arm self,ccx`（或像 hc1 那样 `self,ccx,builtin`）。`--budget` 算的是这个 tag 的所有行，组或轮次多了要调大。

## 结果

结果行写到 `bench/runs/<tag>-results.jsonl`（git 忽略）；tag 默认是 `<题集>-<提交>`，因为 r5.py 一个 tag 只在一个
提交上跑。跑完 run.py 会打印表格；任何结果文件都可以：

```bash
python bench/run.py table bench/runs/holdout-abc1234-results.jsonl
python bench/run.py table bench/results/hc1.jsonl
```

我们的 hc1 结果打印出来是：

| Tag | Arm | Right | Cost per success | Wall, median |
|---|---|---|---|---|
| hc1 | builtin (Claude Code's built-in sub-agent) | 27/28 | $0.103 | 123 s |
| hc1 | ccx2 (delegated to Codex through ccx) | 29/30 | $0.063 | 61 s |
| hc1 | self (the lead does it itself) | 29/30 | $0.090 | 21 s |

这里的 builtin 组是自带子智能体的默认用法，指令比 ccx2 重（它的干活者被要求跑全量测试，ccx2 只跑针对性检查），
所以价差有一部分来自指令，不是 ccx 本身。builtin2（给自带子智能体同样精简的 ccx2 措辞）不在 hc1 里；在开发集上
它每次成功比 ccx2 便宜（r5d $0.114 对 r5h $0.135）。

Right = 隐藏测试通过。Cost per success（每次成功的花费）= 该组总花费 ÷ 做对的单元数（按 API 标价折算，订阅付费的
也一样算）。Wall = 各单元耗时的真中位数。干净环境检查没通过的行（`env_clean: false`）不计入，表格会写出有几行。

每个单元一行（JSON lines）。最常用的字段：

| 字段 | 含义 |
|---|---|
| `tag`、`taskset`、`round`、`task`、`arm` | 哪个单元 |
| `ok` | 隐藏测试是否通过 |
| `pytest` | 测试输出的最后一行 |
| `usd`、`lead_usd`、`ccx_usd`、`sub_usd` | 花费：总的、主导的、ccx 运行的、派出去那部分的 |
| `wall_s` | 单元耗时（秒） |
| `lead_model`、`lead_effort`、`lead_requests`、`lead_tokens` | 主导是谁、用了多少 |
| `env_clean`、`fingerprint` | 干净环境结果；提交、CLI 版本、Python、系统、隔离方式 |
| `timeline` | 按角色和原因分的秒数、$ 和 token |

你自己的结果行里还留着我们公布时删掉的字段（本机路径、run id），别原样公开。
`python scripts/eval/r5.py export <file.json> --taskset holdout --results <你的文件> --include-unclean`
会写出脱敏副本（一个含 `summary` 和 `rows` 的 JSON 文件），[results/](results/) 就是这样导出的：我们把它拆成
结果行（`*.jsonl`）和 `*-summary.json`，又删掉了它留在 `ccx_namecheck[].run` 里的 run id
（其中的时间戳会暴露机器何时在用）和环境变量名的哈希。它的脱敏会整段替换 Windows 路径，但 macOS / Linux 路径里
只替换用户名，所以分享前请自己检查（`python -m pytest -q tests/test_bench.py` 会对 `bench/results/` 跑我们的检查）。

`*-summary.json` 是 r5.py 自己的汇总（配对检验、区间、分仓库）。`hc1-summary.json` 和表格一样只算干净的行，但它的
`wall_med` 取两个中间值里较大的那个，可能和表格的真中位数不同；`r5-dev-summary.json` 算了所有行（开发集的运行
大多在干净环境检查出现之前）。

## 和我们的数字对照

- 留出集：[results/hc1.jsonl](results/hc1.jsonl)，90 行，提交 `b473976`，Windows，Claude Code 2.1.309，Codex CLI
  0.164.0，Sonnet medium 主导。[hc1 报告](../docs/research/2026-10-29-hc1-holdout.zh.md) 里有预注册、每一处偏离、
  配对区间和 8 条限制。
- 开发集：[results/r5-dev.jsonl](results/r5-dev.jsonl)，tag r5 到 r6a（除 r6a 外都在干净环境检查出现之前）；
  [docs/measured.zh.md](../docs/measured.zh.md) 写了每个公布数字用的是哪些 tag。文件里其他 tag 和组（r5c、r5g、
  r6a、`direct`、`ccx2nc`）是原始数据，我们没有据此发布结论。
- 想测 hc1 当时用的提交：检出 `b473976`（那里没有 `bench/`），直接调 r5.py：
  `python scripts/eval/r5.py run --taskset holdout --arms self --rounds 1 --tag mine --out <文件>`，再回到这个
  检出用 `python bench/run.py table <文件>` 打表。

重跑时该预期什么：10 个单元是很小的样本。hc1 里两组之间差值的按题区间大约是 30 题中 ±3 题，费用也会随当天的
模型版本和价格变。请拿你同一时间跑的几组互相比，别拿你跑的一组去比我们的表。ccx 组的行也不等于 hc1 的：
ccx 从你的检出运行，它比 `b473976` 新。

已知限制（详见 hc1 报告）：本仓库的题，答案可能就在 ccx 运行所用的 ccx 代码里（Codex 能读到这个检出），
所以外部仓库的题才是干净的；模型训练截止之前的外部提交可能被记住；只测了 Sonnet medium 主导；价格按 API 标价
折算；hc1 的 harness 审计没有数据（每个单元的 hub 在读之前就清掉了）；公布的运行只在 Windows 上跑过。r5.py 在 Linux 和 macOS 上的路径（没有 Job Object 的进程清理）写了但没有真跑过：实验性。

## 拒绝开跑时

r5.py 拒绝开跑时会说明原因，例如：机器上有别的评测、pytest、`claude -p` 或 `codex exec` 在跑；检出里有已跟踪
文件的未提交改动，或 `ccx/`、`scripts/`、`config/`、`skills/` 下有新文件；`ccx` 组没给 `--codex-home` 或那里没
登录；canary 主导看到了你自己的指令；外部仓库没准备好（不能联网克隆，这个 Python 缺 pytest 9+ 或 freezegun，或者装了
humanize / itsdangerous）；评测用的 Codex 目录里有自己的 skills、plugins 或设置。`-- --force-unclean` 可以强行跑，但每行都标 `env_clean: false`，表格不计入。

## 许可与复制范围

本仓库的题和 `bench/` 里的一切都是 MIT，和 relayline 其余部分一样。外部仓库的题只放指针：仓库地址、完整提交号、
测试文件路径。这里没有复制 humanize（MIT）或 itsdangerous（BSD-3-Clause）的任何内容；你运行时 r5.py 从 GitHub
取，它们的代码和测试仍归各自的许可。隐藏测试是公开的，在每个提交的历史里一直都是：能去查那个提交的智能体就能
找到答案。外部仓库的题，评测会拿走智能体的 Claude 联网工具和外部仓库副本；shell 里下载不拦，只由审计标出。

## 文件

| 路径 | 内容 |
|---|---|
| `tasks/holdout/*.md`、`tasks/r5/*.md` | 每题一个文件，由 `make_tasks.py` 从 `scripts/eval/tasks_holdout.py` 和 `tasks_r5.py` 生成（以它们为准；测试会检查两边一致） |
| `run.py` | `run`（调 r5.py）和 `table` |
| `results/*.jsonl`、`results/*-summary.json` | 我们公布的结果行和 r5.py 对它们的汇总，已脱敏 |
| `runs/` | 你自己的结果行（git 忽略） |
