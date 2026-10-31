# 维护模式：隔一段时间再接手 ccx

[English](maintenance.md) · 中文 · 回到 [README](../README.zh.md)

这一页写给停了一阵再回来的人：维护者、贡献者，或者一个编码智能体。它说清楚现在的状态写在哪、已知哪些有问题或没验证、
哪些开关默认关着以及为什么，还有怎么跑评测才不会骗到自己。

## 1. 从哪开始

按顺序读，够用就停：

| 读什么 | 在哪 | 为什么 |
|---|---|---|
| 在仓库里干活的规则 | [AGENTS.md](../AGENTS.md) | 每次提交前跑测试、不放个人信息、文档中英两份、每个 PR 一个 `changes/<PR>.md` |
| 现在到哪了 | [docs/STATUS.zh.md](STATUS.zh.md)（一页） | 现状、接下来三件、有多确定；旧页面在 [STATUS-archive.zh.md](STATUS-archive.zh.md) |
| 改了什么 | [CHANGELOG.md](../CHANGELOG.md) 和 [changes/](../changes/) 里的小文件 | `changes/*.md` 是上次发版之后合进来、还没折进 CHANGELOG 的 PR |
| 为什么是这样 | [docs/DECISIONS.md](DECISIONS.md) | 每个真正的决定一行，新的在上，带依据 |
| 测过什么 | [docs/research/README.zh.md](research/README.zh.md) | 每份报告一行：问题、结果、主要局限 |
| 上一个会话的笔记 | 你本机检出里的 `.ccx/handoff.md`（如果有） | 只在本机，从不进仓库 |

然后跑一遍测试（`python -m pytest -q tests`）；测试从不调用真正的智能体命令行。

## 2. 已知问题和没验证的路径

其中实验性的几条在各自的功能说明处也标了。完整清单是 [STATUS](STATUS.zh.md) 里"没验证"那一行。

| 问题 | 已知情况 | 在哪 |
|---|---|---|
| 用时 | 留出集上 ccx 的用时约为主导自己做的 3 倍（中位 61 秒对 21 秒） | [hc1 报告](research/2026-10-29-hc1-holdout.zh.md) |
| 省钱的范围很窄 | 10 个留出任务、一个主导模型（Sonnet）、子智能体是 Codex gpt-6-luna low：每次成功约省 30%；只看 5 个外部仓库任务约省 15%。长对话的主导把小任务派出去不省 | [实测](measured.zh.md)、[第 4 轮](research/2026-10-26-r4.zh.md) |
| 选模型的先验 | 难度 → 模型成功率在评测任务之外没校准过 | [功能说明](features.zh.md) |
| 实验性：Gemini CLI | 按文档写的适配器，用替身测过，没真跑过；只能当子智能体 | [常见问题](faq.zh.md) |
| 实验性：真实的额度用完 | 换到另一个工具只用替身测过 | [功能说明](features.zh.md) |
| 实验性：macOS 和 Linux | 只在 CI 里跑；所有真实运行都在一台 Windows 电脑上 | [README](../README.zh.md) |
| 实验性：从 GitHub 地址装 Codex 插件 | 按 Codex 插件文档写，只用替身测过 | [安装](install.zh.md) |
| 实验性：`ccx intake` 对真实 GitHub | 只对替身 `gh` 跑过 | [intake](intake.zh.md) |
| 没真跑过 | Codex 桌面端窗口里的 `ccx say --now`、`ccx doctor --codex-rule` 生成的 Codex 规则、排队归档后 dsh 应用自己后来的写入、子智能体自己的子智能体上限（F11）、`--review auto` 的触发率、真实会话里 hook 超时、L2 自动合并全流程 | [STATUS](STATUS.zh.md) |

## 3. 实验性开关：哪些默认关、为什么

默认值在 [config/tiers.toml](../config/tiers.toml) 里；个人可以在 `<hub>/ccx/tiers.toml` 覆盖任何一个。只有一部分键
还能用 `ccx config set <段>.<键> <值>` 改（见最后一列）；其余只能改文件，`[subagent]` 是有意如此（没有单次运行的参数）。每个开关同一条规矩：只有前后对比证明做对的不减少，才改默认，并在
[DECISIONS](DECISIONS.md) 记一行。

| 键 | 默认 | 打开后做什么 | 为什么关着 | `config set` |
|---|---|---|---|---|
| `defaults.focused_retry` | `false` | `--check` 没过时，重试续同一会话，带上失败的命令和输出 | "只修失败处"缩小了重试复查的范围，没法保证做对的不减少；等一轮实测（起因：r6a 里旧式重试中位 389 秒） | 能 |
| `defaults.namecheck` | `"warn"` | `"fail"` 让改动代码里的未定义名字直接判失败 | `warn` 离线 0 误报；`fail` 等前后对比（r6a 跑了 `ccx2nc` 组，结果还没发表） | 不能（单次用 `ccx run --namecheck`） |
| `lanes.default` | `0` | `ccx batch` / `ccx q run` 让几块活续在几个热会话里，不再每块开新会话 | 比每块新开会话便宜约 40%，但更慢，也仍比一次做完贵（[热通道](research/2026-10-25-warm-lanes.zh.md)）；由确认实验决定 | 能 |
| `memory.by_kind` | `false` | 开局只推偏好和约束；简报带相关的坑和事实 | 由确认实验决定；原本要决定它的 H11 试用已于 2026-10-26 作废 | 能 |
| `memory.start_scene` | `false` | 开局再带当前项目的场景块 | 同上 | 能 |
| `review.context` | `false` | 审查简报再附改动附近的代码 | 回放第 5 轮：用时和输出约减半，但已知 bug 28 次只抓到 11 次（不附时 19 次） | 不能 |
| `review.fix_rereview` | `"full"` | `"focus"` 让修复轮的复审对着首轮问题看 | 由用时决定：中位只省 2.4 秒，门槛是 10 秒（漏掉的 `[must]` 24 对 21，共 33，各跑 1 遍，分不出是不是噪声） | 不能 |
| `review.cache_ttl` | `""` | 设 Claude 审查者的提示缓存时长（`"5m"` / `"1h"`） | 没做 A/B | 不能 |
| `routing.small_self` | `false` | `ccx route` / `ccx propose` 对最多改 `routing.small_self_files`（1）个源文件的活建议自己做、不派（`ccx run` 不变） | 用 r5 + 留出集已有数据按参考改动的文件数复算：一题不少、墙钟 -14%、成本 +5%；主导自己的估计要等留出集一轮（self / ccx2 / ccx2+small_self） | 能 |
| `lead.model_by_task` | `false` | 新开主导对话时按任务难度选模型 | 阈值是暂定的，等 `scripts/eval/r5.py --lead-model auto` 和固定模型比过 | 能 |
| `subagent.codex_memories` | `true` | `false` 给子智能体关掉 Codex memories | B3：对着用户日常配置做完前后对比再改（[计划](research/2026-10-30-b3-lean-switches-plan.zh.md)） | 不能 |
| `subagent.clean` | `false` | 子智能体不加载个人技能和用户设置 | 同一个 B3 测量；个人技能带来的正确率可能丢掉 | 不能 |
| `subagent.codex_lean_tools` | `false` | Codex 写入任务关掉网页搜索、生成图片和 goals | 同一个 B3 测量 | 不能 |
| `policy.picked` | `""` | 按档位预先授权派活，不再先提议 | 是个人自己的选择，永远不当默认 | 能 |

不是实验性、而是有意留空的（用 `ccx config set` 设）：`board.github` 和 `intake.github`（空 = 完全不碰网络，直到你填上自己的私人仓库）、`report.publish_dir`、`projects.roots`。

## 4. 怎么跑评测

评测花真钱，数字会进 README，所以规矩很严。

1. **先写计划。**新建 `docs/research/<日期>-<名字>-plan.md`（和 `.zh.md`）：问题、各组、任务、判定规则和预算，跑之前就提交。
   跑完后的偏离写明，不藏。
2. **先估价不跑。**`python scripts/eval/r5.py run ... --dry-run` 打印排期和花费估算。
3. **用干净环境。**`scripts/eval/r5.py` 每个单元从零开始（新的仓库副本、hub、智能体 home、关掉个人 hook 和记忆的设置文件；
   见 `scripts/eval/preflight.py`），没有干净环境就拒绝开跑（`--force-unclean` 能强行开跑，结果行会记下来）。把要测的提交钉住（`--pin-commit`）。
4. **机器保持安静。**计时的评测在跑时，同一台机器上不跑全量测试和其他重活。启动时让日志记下结束，例如
   `python scripts/eval/r5.py run ... > run.log 2>&1; echo exit=$? >> run.log`。
5. **用脚本汇总，不手算。**`python scripts/eval/r5.py summary --tag <标签>` 只算干净的行，并在共同的单元上配对比较；
   `scripts/eval/r5_timeline.py` 看时间花在哪。
6. **把发现的都公开，包括对 ccx 不利的。**在 `docs/research/` 写报告并写明局限，在 [research/README.zh.md](research/README.zh.md)
   加一行，用 `r5.py export docs/research/data/<文件>.json` 导出去掉个人信息的数据（检查有没有本机路径：`tests/test_repo_hygiene.py` 会把这个目录里的任何盘符路径报出来）。

例子（根据脚本自己的说明改写）：

```bash
python scripts/eval/r5.py run --taskset holdout --rounds 3 --arms ccx2 --tag ho4 --dry-run
python scripts/eval/r5.py run --rounds 2 --arms ccx2,builtin2 --tag r5d --budget 25
python scripts/eval/r5.py summary --taskset holdout
```

留出任务（`scripts/eval/tasks_holdout.py`）是留给最终结论用的。这个文件就在公开仓库里，所以它们已经不再是留出集；新的结论需要新的没见过的任务。

## 5. 发版

1. `python scripts/collect_changes.py` 预览由 `changes/*.md` 生成的 CHANGELOG 条目；加 `--version X.Y.Z --title "..." --apply`
   写进去并删掉这些小文件。
2. 在 `ccx/__init__.py`、`pyproject.toml`、`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json` 里改版本号；更新
   [STATUS](STATUS.zh.md)（一页，中英两份）。
3. 打 `vX.Y.Z` 标签；标签会触发完整的 CI 矩阵。发不发布（GitHub Release、PyPI）由维护者决定。
