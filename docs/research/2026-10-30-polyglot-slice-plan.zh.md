# Polyglot 切片：一个有难度梯度的外部基准（计划，2026-10-30）

[English](2026-10-30-polyglot-slice-plan.md) · 中文 · 返回[研究报告](README.zh.md)

**状态：只有计划和评测适配；下面没有任何数字是结果。** 预跑（1 个单元，证明链路通）记在文末。 有结果后写进本文件；别处引用数字时要带上“外部基准、30 题、一轮”。

## 为什么

留出集 hc1 上 ccx2 和自己做一样对（29/30）、便宜约 30 %，但“更准”没有证据：所有题便宜模型本来就能做对，分流、审查、升级显不出作用。这个切片加入已知对部分模型有难度、且 ccx 开发时没用过的题。

## 来源与许可（2026-10-30 核对）

| | |
|---|---|
| 基准 | aider 的 polyglot 基准，[Aider-AI/polyglot-benchmark](https://github.com/Aider-AI/polyglot-benchmark) |
| 固定提交 | `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`（2024-12-22，2026-10-30 时的 `main` 头） |
| aider 怎么选的 225 题 | 六种语言共 697 道 Exercism 练习里，2024 年 7 个模型中最多 3 个能做出的那些（[aider 博客 2024-12-21](https://aider.chat/2024/12/21/polyglot.html)） |
| 许可 | 仓库没有 LICENSE 文件；README 说题目版权属 Exercism，按 Exercism 的开源许可使用。Python 题库（[exercism/python](https://github.com/exercism/python)）是 MIT。本仓库不复制任何题目内容，运行开始时才拉取 |

## 30 题和选法

基准里全部 34 道 Python 题，去掉按（Exercism 难度，测试数）排最低的 4 道：list-ops、robot-name、proverb、transpose。清单、每题难度、测试数、理由和去掉的 4 题见 [`scripts/eval/polyglot_selection.json`](../../scripts/eval/polyglot_selection.json)。选题只看了每题的 `.meta/config.json`、测试文件（数测试个数）、说明长度和 Exercism 难度评级；没有打开 `.meta/example.py` 或 `.approaches/`（解法）。

只做 Python：跑评测的机器上没装 Go 和 Node.js，JS/Go 部分没法预跑，留到以后。

**难度梯度是假设，不是测量。** aider 只公开每个模型的总通过率，不公开每题的，所以今天的便宜模型每题能不能过并不知道。第一轮里 `direct` 组（Codex gpt-6-luna low、无主导）就是在测它。事先登记：如果 `direct` 拿到 27/30 或更高，这个切片也到了天花板，就照实说，不对分流下任何结论。

## 一个单元看到什么

- 仓库：只有题目的解答存根文件，放在只有一次提交的新仓库里（没有 `.meta/`、`.approaches/`、`.docs/`、测试和历史）。
- 任务说明：题目自己的说明（introduction、instructions、instructions.append，按 aider 的顺序），加一段和 aider 类似的补充：改哪个文件、别改名字、只用标准库、测试是隐藏的、只给解答文件打分。
- 开跑前先跑 `python scripts/eval/polyglot_check.py`，确认每道题的隐藏测试能正确打分：完全按单元的方式打分，原样存根必须失败，题目自带的参考解必须通过（参考解由检查脚本从临时克隆里读，不会进任何单元）。
- 隐藏测试：题目的测试文件。打分时只把解答文件复制到一个新文件夹，和测试、一个自带的 `pytest.ini` 放在一起，所以智能体写的别的东西（自己的测试、`conftest.py`、pytest 设置、遮住标准库的模块）都不生效。判对的条件是 pytest 总结行显示通过数正好等于该题测试数，且没有跳过、失败或报错（导入时跳过整个模块或以 0 退出的解答不算对）。解答文件不见了算失败。限时 300 秒。
- 其余沿用第 5 轮给留出集外部仓库的干净环境：金丝雀之前克隆一次、读进内存后删掉；拷贝和 Claude 的网页工具都禁止；pip 没有索引；审计会标出指向 exercism、problem-specifications 或基准仓库的抓取命令。

和 aider 不同（两次机会，第二次给看测试错误），这里只有一次、测试一直隐藏，所以通过率更接近 aider 的首次通过率。

## 三组（`--taskset polyglot` 的默认组）

| 组 | 谁干活 |
|---|---|
| `self` | 主导（Claude Code，Sonnet medium）自己做 |
| `ccx2` | 同一个主导按 agent-delegate 技能的写法交给 ccx（save 档：先 Codex gpt-6-luna low，ccx 的 `--check` 失败时升一级） |
| `direct` | 没有主导：`ccx run` 直接交给 Codex gpt-6-luna low，带审查、`--minutes 60`、没有 `--check`、不升级（沿用第 5 轮的 direct 组） |

三组的题目说明、隐藏测试和干净环境都相同；主导提示里不提基准名字。不同的是干活的方式，这正是要比的：

- 练习题没有测试文件可以填进 ccx2 的 `--check`，所以对练习题，主导被告知让子智能体在解答旁写一个自己的测试文件，并把它当 `--check`（例如 `python -m pytest -q test_own.py`）。这个检查是子智能体自己写的，答错也可能通过；self 的主导按补充说明“自己写检查自己跑”，处境一样。
- ccx2 的主导用 `--brief-file` 传任务说明（说明很长，满是反引号和 `$`，放在双引号里会被 shell 展开）；子智能体拿到的是主导转抄的说明，和所有 ccx2 运行一样。
- direct 没有主导，所以它拿到的说明里没有主导提示里关于文件夹的两句话。

## 第一轮（由统筹排期，还没跑）

```bash
python scripts/eval/polyglot_check.py                       # 每道题都能正确打分（不花钱）
python scripts/eval/r5.py run --taskset polyglot --rounds 1 --tag pg1 --arm-order balanced --budget 15 \
    --codex-home <eval codex home>
python scripts/eval/r5.py summary --taskset polyglot --tag pg1
```

90 个单元。dry-run 按第 5 轮每单元均值估约 $11；那些均值来自整个代码库里的任务，一道练习只有一个文件，应该更便宜（预跑的那个单元是第一个实测）。`--budget 15` 留了余量，避免预算停在中途留下不完整的配对；`--arm-order balanced` 下每道题的三个单元是连着跑的。

事先登记（开跑前写好，之后不改）：

- 主要指标同 hc1：每组做对数/30（隐藏测试，Wilson 95 % 区间）、每次成功花费、墙钟中位数。
- 天花板：`direct` ≥ 27/30 就说明这个切片对分流说明不了什么，照实报告，到此为止。
- 只有 ccx2 做对数高于 direct，且配对 McNemar（三对之间做 Holm 校正，`r5.py summary` 会打印）p < 0.05，才能写“分流提高了正确率”；否则只报做对数和区间，当作方向，不当结论。ccx2 对 self 同样处理（没过这个检验就不说比 self 更准）。
- 花费和墙钟只报告，不做检验。一轮只是信号，不是证明。

## 限制（引用数字时一起写）

1. Exercism 题目和解法都是公开的，很可能在所有模型的训练数据里；对各组影响相同。
2. 30 题、一种语言、一轮、一种主导模型。
3. `direct` 跑完前不知道难度梯度（见上）。
4. 解答文件在打分进程里运行：导入时改写测试框架的解答可以作弊。每个练习单元不论对错都保留最终 diff（在结果文件旁的 `-artifacts/` 目录），读它们就能发现这种情况。
5. 金额是 API 等价价。

## 预跑

1 个单元，只为证明链路通（2026-10-31，标签 `pg0`，提交 1142da3，主导 sonnet medium）：`pg-two-bucket`，`ccx2` 组。这不是结果：1 个单元说明不了任何一组。

| 项目 | 值 |
|---|---|
| 隐藏测试 | 9 个全过（等于该题测试数） |
| 是否分派 | 是，ccx 派给 Codex gpt-6-luna low |
| 花费 | $0.079（主导 $0.069） |
| 墙钟 | 79 秒 |
| env_clean / 审计 | 是 / 干净 |

说明了什么：干净环境、分派主导用子智能体自写测试当 `--check` 和 `--brief-file`、隐藏测试打分、保留现场，整条链路都通。最终 diff 只有解答、子智能体的 `test_own.py` 和主导的 `brief.md`。开跑前先等了别的会话的测试跑完（`--wait-quiet`）。子智能体请求数当时还没记录（`sub_req=None`，记录它的 ccx 改动当时还没合并）。这一个练习单元的花费约为估算所用第 5 轮均值 $0.12 的三分之二，所以正式一轮应低于 $11。
