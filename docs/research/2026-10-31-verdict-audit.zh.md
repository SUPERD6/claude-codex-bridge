# 收据误报审计：ccx 收据说"对"、隐藏测试却没过，有多常见？（2026-10-31）

[English](2026-10-31-verdict-audit.md) · 中文 · [全部报告](README.zh.md)

## 一句话

**#158 之后，收据说"对"的 209 次里，有 8 次隐藏测试没过：3.8%（Wilson 95% 区间 2.0–7.4%）。** #158 之前是 18/267（6.7%）。

这 8 次都是同一种情况：ccx 的 `--check` 过了，审查也过了，但 check 没测到隐藏测试要的那条行为。其中 1 次，check 根本没跑隐藏测试所在的文件；另外 7 次跑的是同名文件，可那是子智能体自己写的版本。8 次里没有一次是"补丁没落地"（#158 给这种情况加了 `no_changes` 标签）。有 hub 记录的 3 次，审查都没被拒绝用工具；另外 5 次这一点是 Unknown。

审计前定的门槛是 2%。点估计高于门槛，区间下限正好压在门槛上，所以**列为发布前必修项**。

另一面同样要紧。#158 之后，最后一张收据说"不对"的 51 个单元里，有 47 个其实通过了隐藏测试，其中 35 个是审查没通过。另有 18 个单元先拿到"不对"的收据，主导续跑之后才变成对的。ccx 判得太严的时候，比判得太松多得多。

## 方法

- **单元。** 评测实际计入了 6 个结果文件：`r4/calib`、`r4/long`、`r5/results`（r5、r5c–r5h、r6a）、`r5/holdout-results`（hc1）、`r5/m1h2-results`、`r5/m1r5-results`。这些文件里，凡是 ccx 组、至少跑过一次 ccx 的单元都算进来，共 565 个。
  - 主导一次都没派活的单元没有收据，不算。
  - 52 行试跑和中止行不算（`pilot-dropped`、`m1r5-aborted`、`m1h`、`m1r5-part1`、`pg0`、`long-pilot-dropped`）。它们要么跑在坏掉的环境里，要么中途停了；而且后来的运行复用了同名的工作目录。
- **组别。**
  - 有主导（Sonnet medium）：`ccx`、`ccx2`、`ccx2nc`、`ccx2@auto`、`ccx2daily*`，共 385 个单元。
  - 没有主导、ccx 直接按任务说明跑：`direct` 和 r4 的校准组，共 180 个单元，全在 #158 之前。
- **ccx 说了什么。** 看单元里每条运行链的最后一次。一次运行如果被后来的运行接着跑了，就不算最后一次。"接着跑"有两种：
  - ccx 自己的修复轮（`review_of`）；
  - 主导的 `ccx resume`。hub 里看 `resumed_from`；stream 里看主导执行的 `ccx resume <run>` 命令，因为收据里不写它续跑的是哪次。
- **怎样算"说对"。** 每条链的最后一次都通过收据顶行的规则（`delegate.compact` / `exit_ok`），这个单元才算"说对"。规则是：
  - ok；
  - kind 不是 `review_issues review_failed check_broken no_changes check_failed env` 里的任何一个；
  - check 没失败；
  - 审查结论不是 `issues` 或 `failed`；
  - 状态是 `done` 或 `partial`。

  子智能体自己报的 `partial` 也算"说对"，因为这时收据印的是 `"ok": true`。严格口径（`--strict`）把 `partial` 算作"说错"。
- **从哪里读判定。**
  - 295 个单元（r4 long、r5 开发集、r6a、m1r5）：读单元 hub 里的 `run.json`。
  - 150 个单元（hc1、m1h2）：打分后 hub 被删了，读主导 stream 里它最后看到的 ccx 收据。
  - r4 校准的 120 个单元：读结果行里的字段（`ccx_ok`、`status`、`check`、`review`）。

  交叉核对：220 个单元 hub 和 stream 都在，其中 4 个，主导最后看到的收据和 hub 里最后一次运行不一致。这 4 个都通过了隐藏测试，所以不影响误报数。
- **真值。** 单元的 `ok`：在原提交自带的测试文件上跑 pytest。这些文件是运行结束后才加进去的，也就是隐藏测试。
- **#158 前后**（`12599c0`，2026-10-28 16:02）。单元所用的 ccx 版本（`fingerprint.commit`）包含 `12599c0`，就算 #158 之后。没有 fingerprint 的行（r4、r5–r5h）按时间算：它们都在 10-25/26 跑完，算之前。#158 之后的是 r6a（`c64494d`）、hc1（`b473976`）、m1h2（`600fa7b`）、m1r5（`3a15b8b`）。
- **重算。** 脚本只读不写。`--work` 指向放着 `r4c r4l r5* r6a m1r5` 这些工作目录的临时文件夹：

```bash
python scripts/research/verdict_audit.py --eval .ccx/eval --work "$TEMP" --out docs/research/data/2026-10-31-verdict-audit.json
```

  去掉路径后的逐单元数据：[data/2026-10-31-verdict-audit.json](data/2026-10-31-verdict-audit.json)。

## 四格表

四格是"收据说对 / 说错"乘"隐藏测试过 / 没过"。最危险的一格是"说对其实错"，下表按"收据说对的次数"算它的占比。

| 时段 | 单元 | 说对也对 | **说对其实错** | 说错其实对 | 说错也错 | 说对其实错 / 说对 |
|---|---|---|---|---|---|---|
| 全部 | 565 | 450 | **26** | 79 | 10 | 26/476 = 5.5%（3.8–7.9） |
| #158 之前 | 305 | 249 | **18** | 32 | 6 | 18/267 = 6.7%（4.3–10.4） |
| ↳ 无主导 | 180 | 151 | 11 | 15 | 3 | 11/162 = 6.8% |
| ↳ 有主导 | 125 | 98 | 7 | 17 | 3 | 7/105 = 6.7% |
| **#158 之后**（全有主导） | 260 | 201 | **8** | 47 | 4 | **8/209 = 3.8%（2.0–7.4）** |
| #158 之后，严格口径（`partial` 算错） | 260 | 80 | 4 | 168 | 8 | 4/84 = 4.8%（1.9–11.6） |

括号里是 Wilson 95% 区间。这个区间假定各单元相互独立，实际并不独立（见"局限"），所以偏窄。如果按 #158 之后的全部单元算，"说对其实错"是 8/260 = 3.1%。

按结果文件分：

| 文件 | 时段 | 单元 | 说对其实错 / 说对 |
|---|---|---|---|
| r4 校准（无主导） | 之前 | 120 | 4/117 |
| r4 长会话 | 之前 | 5 | 0/5 |
| r5 开发集 r5–r5h | 之前 | 180 | 14/145 |
| r6a（开发集） | 之后 | 30 | 3/25 |
| hc1（留出集） | 之后 | 30 | 1/29 |
| m1h2（留出集，日常配置组） | 之后 | 120 | 4/103 |
| m1r5（开发集，日常配置组） | 之后 | 80 | 0/52 |

## 26 次"说对其实错"，按原因分

原因由脚本里 `cause()` 的固定规则从记录判出，依次看三件事：
1. 单元是不是一个文件都没改；
2. 最后一次运行有没有 check；
3. check 命令有没有点到隐藏测试所在的文件（任务的 `tests` 列表，见 `scripts/eval/tasks_r5.py` / `tasks_holdout.py`）。

隐藏测试是原提交自带的测试文件，运行结束后才加进去，所以按设计，check 从来跑不到它们。下表里的"同名文件"，指 check 跑的是子智能体那一版的同名文件。

| 原因 | #158 前 | #158 后 | 记录里的证据 |
|---|---|---|---|
| A. 补丁没落地 | 2 | 0 | `direct · brief-words · 1`：一个文件都没改，状态 partial（子智能体放弃了，见 r5 报告）。`direct · dsh-archive · 1（r5c）`：diffstat 是"no changes"。#158 为这种情况加了 `no_changes` 这个 kind。 |
| B. 没有 check，只靠审查 | 5 | 0 | 全是 `direct` 组，它按设计就没有 `--check`：`waiting-evals`、`q-resume-session` ×2、`projects-refresh`、`quota-stop-log`。审查都放行了（`projects-refresh` 的审查结论是 `unclear`）。 |
| C1. check 没跑隐藏测试所在的文件 | 7 | **1** | 之前：r4 校准组 `luna` 在 `inventory`、`debug-line` 上各 2 次（合成任务：check 跑可见测试，隐藏测试是另一个文件）；`r5e quota-stop-log`（check 跑 `test_quota_fast.py`，隐藏测试在 `test_quota_stop_log.py`）；`r5g mem-report`（`test_memory_e7.py` 对 `test_memsuggest.py`）；`r5h q-killed-spend`（`test_queue.py` 对 `test_recover.py`）。之后：`m1h2 doctor-codex-sandbox · 3 · ccx2daily_clean`，check 是 `tests/test_ccx.py -k doctor`，隐藏测试却是新文件 `tests/test_codex_lead_sandbox.py`。 |
| C2. check 跑了同名文件（子智能体那版） | 4 | **7** | 之前：`r5 ccx quota-stop-log · 1`；`r5 ccx q-resume-session · 2` 和 `r5g q-resume-session · 2`（跑了 `test_queue.py`，没跑 `test_recover.py`）；`r5c projects-refresh · 2`。之后：`r6a q-resume-session · ccx2nc`（只跑 `test_queue.py`；审查先提了问题，修复轮跑完后审查放行）、`r6a codex-hook-text`、`r6a mem-report`、`hc1 discuss-auto-tier · 3`、`m1h2 discuss-auto-tier` ×3。这 7 个都是 check 过了、审查（Claude Haiku low）也过了。 |

记录里还能看到下面这些情况。它们确实出现过，但不能证明就是原因：

- **审查被拒绝用工具。** #158 之前，有 hub 记录的 14 个误报单元里，有 7 个的审查至少被拒了一次工具调用（r4 校准那 4 个没有 hub）。所有从 hub 读的单元里，#158 之前是 91/185，之后是 6/110。#158 之后从 hub 读的 3 个误报单元（r6a）都没被拒。从 stream 读的 5 个（hc1、m1h2）是 Unknown，因为审查的事件不在主导的 stream 里。
- **修复轮之后没再审查。** `r5c projects-refresh · ccx2` 和 `r5e quota-stop-log · ccx2`：第一次审查提了问题，修复轮那次运行自己没有审查，它的 check 过了。两个都在 #158 之前。
- **`partial` 却印着 `"ok": true`。** #158 之后的 8 个里有 4 个（都在 m1h2）是子智能体自己报的 `partial`。严格口径会把它们算作"说错"，但同时也会把另外 121 个其实做对的单元变成"说错"（47 → 168）。
- **第 5 轮报告里已知的根因**（[r5 §2](2026-10-26-r5.zh.md)）。`ccx quota-stop-log · 1` 是主导把需求转述错了。`ccx q-resume-session · 2` 和 `direct q-resume-session · 2` 是审查的修复轮追着需求里没要求的问题改。
- **"修复轮后 ccx show 显示旧结果"**（#161 已修）。记录里没有因它造成的误报：hub 和 stream 不一致的那 4 个都通过了隐藏测试。只有 stream 的单元没有 hub 可比，对它们来说是 Unknown。
- **具体哪条隐藏断言没过，这些单元没有记录。** 结果行只存了通过和失败的个数；m1r5 留下的失败现场（`hidden-pytest.txt`）里也没有误报单元。所以是 Unknown。
- **#158 之后的 8 个里有 4 个是同一个任务**（`discuss-auto-tier`，留出集）。这几次的 diff 都是整份文件重写：一个约 690 行的文件，加了约 700 行、删了约 670 行，多半是换行符变了。`codex-hook-text`（1213/1206）和 `doctor-codex-sandbox`（768/692）也是这样。这和误报有没有关系是 Unknown。

## 另一面：说错其实对（#158 之后 51 个里有 47 个）

每个单元只归到一类，按它最后几次运行依次判断：check 命令本身坏了、check 没过、审查没过、规则（`no_changes`）触发、其他。

47 个里只有 4 个是主导自己动手改了文件（Edit 工具）；其余的，子智能体的结果本来就对，是收据判得太严。47 个里有 41 个来自 m1h2 和 m1r5 的日常配置组。"说错其实对"会让主导多花时间、多跑修复轮、多花钱，但不会留下错代码。

| 类别 | 单元 | 主导改过 | 记录里能看到的 | 例子 |
|---|---|---|---|---|
| 审查 `[must]` 误报（`review_failed`，check 已过） | **35** | 2 | 审查全是 Claude Haiku low；修复轮之后审查仍不满意。按任务分：review-min-lines 8、projects-refresh 5、quota-stop-log 5、mem-report 5、q-killed-spend 4、其他 8。这些 `[must]` 都是先引一句需求，再要求隐藏测试并没有要求的边界情况或解读。 | `m1r5 q-resume-session · 1 · ccx2daily_clean`：`[must]` 针对的是改动给现有测试加了 `--to codex`（check `tests/test_queue.py` 7 个全过）。`hc1 review-min-lines · 1`：`[must]` 纠结的是 `---` / `+++` 文件头怎么算。 |
| check 没过（exit 1：测试跑了，有失败） | **11** | 2 | exit 1 表示测试跑起来了，不是命令或环境坏了（那种是 exit 4/5）。从 hub 读的 3 个，没过的都是子智能体自己写的或改过的测试：`test_ui.py`、`test_archive_after_run.py` 里的（隐藏测试会换掉这两份文件），以及新文件 `test_batch_review_risk.py` 里的。从 stream 读的 8 个，没有记录是哪条测试没过：Unknown。 | `m1r5 waiting-evals · 1`：`FAILED tests/test_ui.py::TestData::test_waiting_excludes_evaluation_runs`，而隐藏的 `test_ui.py` 过了。 |
| check 命令写坏、规则 `no_changes` | 0 | | 这两种都出现过，但每次主导都续跑了，最后一张收据说对（见下）。 | |
| 其他 | **1** | 0 | 单元结束时，最后一次运行还处在 `running` 状态，所以没有状态。 | `m1r5 dsh-archive · 2 · ccx2daily_clean` |

**主导续跑过的"不对"收据：另有 18 个单元。** 这些单元先拿到"不对"的收据，主导执行了 `ccx resume`，最后一张收据说对，隐藏测试也过了。第一张收据的情况是：check 没过 9 个、`no_changes` 4 个、check 命令写坏 2 个、审查没过 3 个。

写坏的 check 是 `python -m pytest -q tests -k undo or verify or verdict`（`m1h2 undo-not-verdict`）：`-k` 后面的表达式没加引号，被 shell 拆开，pytest 以 exit 4 退出。`no_changes` 那几次，单元最后的代码树其实有 1–2 个文件改动。这 18 次续跑每次都要花一次运行，而哪些续跑是真正需要的，记录分不出来。

## 对照门槛

审计前定的门槛（发布计划 P1-10）：#158 之后"说对其实错"超过 2%，就列为发布前必修。**结果是：按收据说对的次数算 3.8%，按全部单元算 3.1%，严格口径 4.8%，区间下限 2.0%。没过门槛。**

怎么修，这里不做决定。记录里能看出三个方向，都还没测过：
- check 只跑了子智能体自己写的或改过的测试时，把它标成弱证据；
- 要求 check 在改动前失败、改动后通过；
- 把子智能体报的 `partial` 放到收据顶行。

## 局限

- **check 和隐藏测试的关系。** 隐藏测试是运行结束后才加的，ccx 的 check 永远看不到它们。"说对"最多只能和主导选的 check 加上审查一样可靠。真实使用里没有隐藏测试，这次审计说不出那时收据有多常错。
- **只有一种主导模型。** 有主导的单元全是 Sonnet medium。子智能体大多是 Codex gpt-6-luna low，审查大多是 Claude Haiku low。其他主导、模型和审查都没有审计。
- **单元不独立。** 同样的任务在不同轮次、不同组里反复出现：#158 之后的 8 个误报只落在 5 个任务上，其中 4 个是同一个任务。Wilson 区间按独立来算，所以偏窄。
- **#158 前后不是对照比较。** 任务集（开发集、留出集）、组别（日常配置组只在之后出现）和 ccx 版本都不一样。从 6.7% 降到 3.8%，不能算作 #158 测出来的效果。
- **开发集任务在调 ccx 时用过。** 留出集里本仓库的 5 个任务，答案可能就在 ccx 自己的代码里（见 [hc1 报告](2026-10-29-hc1-holdout.zh.md)）。
- **收据规则是用今天的规则套到旧记录上重算的。** #158 之前的记录没有 `no_changes` 这个 kind，A 类只能靠改动文件数来判。r4 校准只读结果行的字段。stream 里的续跑靠主导执行的 `ccx resume <run>` 命令识别，别的写法会漏掉。
