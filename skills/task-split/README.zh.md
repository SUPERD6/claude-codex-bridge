# task-split（中文说明）

[English: SKILL.md](SKILL.md) · [方法与论文（英文）: references/method.md](references/method.md)

**作用**：把一个大任务拆成合适的小块，并给出数字：拆成几块、每块多大、哪些能并行、整体成功率和每成功一次的花费。可以单独用（Python 3.11+）。

## 拆分原则

先明确结果与验收，再沿可检查、依赖较少的边界拆分。先规划当前需要的里程碑，遇到新证据再细分，不固定块数或层数。每块写清结果、依赖、文件范围与完成条件；简单顺序工作不必先跑定量估算。

当大小、成本或并行关系确实影响决策时才使用下面的脚本。时间跨度与开销来自假设或历史记录，不能当作当前任务的实测保证。方法细节按需读 references/method.md。

## 用法

```
python scripts/split_plan.py size --minutes 240 --rung codex:gpt-6.1-sol:medium
python scripts/split_plan.py template > plan.json   # 改成你的各块
python scripts/split_plan.py check plan.json --lanes 3
```

`size` 输出最优块数、每块分钟数、整体成功率、每成功一次的花费和建议。

`check` 输出：
- 分成几“波”（同一波可以并行）；
- 关键路径和预计墙钟时间；
- 每块的成功率；
- 问题标记：太大、太小、没有检查、并行的块改同一个文件、依赖太多（`files` 决定哪些块能并行：改同一个文件的块不并行）；
- 一行现成的 `checkpoint.py init` 命令，直接交给 task-checkpoint 记录进度。

## 和其他技能的关系

当前 agent 可以自己完成各块。长任务需要恢复记录时使用 task-checkpoint；确有选模型或已获授权的委派需求时，才使用 task-routing / agent-delegate。拆分、估算并行波次都不自动授权启动额外 agent。

## 自动校准

每次检查通过或失败后，记一次结果（ccx 会自动记）。参数会自动向真实情况靠拢：task-routing 校准成功率和花费，task-split 校准每个模型能做多长的任务。Claude 和 Codex 用的是同一个技能目录，所以学到的东西共用一份。价格表超过 30 天没更新会提醒，提醒后对照官方价格页更新。

## 局限

- 时间跨度和开销是带日期的估计值，要用你自己的运行记录来校准。
- 分钟数本身也是估计，所以结果给的是数量级和问题标记，不是精确的排期。
