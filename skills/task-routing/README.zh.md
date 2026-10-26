# task-routing（中文说明）

[English instructions: SKILL.md](SKILL.md) · [方法与论文（英文）: references/method.md](references/method.md)

**作用**：在用户要求选模型、比较自己做与委派，或已经授权委派时，提供模型和推理强度的估算建议。普通“省 token”请求不触发估算或委派；输出不是实测成功率、订阅额度预测或启动代理的授权。

**可以单独用**：整个文件夹复制到任何 Claude Code 或 Codex 的技能目录就能用。只需要 Python 3.11+，不依赖 ccx。

## 怎么算的

1. **任务打分**：主智能体按 5 项给任务打分，加起来是难度 b（0–10）。这 5 项是：改几个文件、跨几个模块、目标清不清楚、风险高不高、要不要新设计。
2. **成功率**：P = 1 / (1 + e^(−1.2·(θ − b)))。θ 是某个“模型 × 强度”组合的能力值，这个公式来自项目反应理论（IRT），也是 IRT-Router 用的方法。
3. **单次成本**：按价格表折算成美元。
4. **怎么选**：能检查对错的任务，先用便宜的，失败了在同一个会话里升级（级联规则）；在“最终成功率 ≥ 门槛”的选项里，挑“每成功一次花费”最低的。不能检查对错的任务，直接选“成功率 ≥ 门槛”里最便宜的。
5. **防过度**：难度 b ≤ 1 建议自己做。如果连最好的组合成功率都低于 50%，建议先拆成小任务。
6. **会学习**：每次记录真实结果（检查过了没有），能力值按 θ ← θ + 0.25·(结果 − 预测) 更新，每周向初始值回落一点。

## 例子

```
python scripts/task_routing.py route --files 3 --coupling cross --clarity goal --risk low --novelty pattern --explain
python scripts/task_routing.py record --rung codex:gpt-6.1-sol:medium --b 4 --ok 1
```

## 档位（整个流程）

`--tradeoff` 也是档位：决定每块活谁做。分档看主智能体的简报，加上 `--minutes` 和 `--files`（`ccx propose`，或
`scripts/task_routing.py tier`）。阈值是暂定值，在 ccx 的 `config/tiers.toml [policy.*]`。

| 档 | 谁做 |
|---|---|
| `save` | 全部经 ccx 委派（`ccx2`），模型按 save 选；主智能体按 check + 审查验收 |
| `balanced` | 小、中自己做，大的交 `ccx2`；大小拿不准、状态机/续跑类自己做 |
| `fast` | 全部自己做 |
| `cheapest` | `direct`：交 ccx，主智能体不验收；要告诉用户结果可能做错 |

人明确选了档位（主智能体带上 `--tradeoff`）就等于预先授权按该档委派：`ccx propose` 返回 `authorized`。
没选档位时照旧“先提议一句”（agent-delegate 第 0 节），档位结果只展示。默认档仍是 `save`，等确认实验再定。

## 自动校准

每次检查通过或失败后，记一次结果（ccx 会自动记）。参数会自动向真实情况靠拢：task-routing 校准成功率和花费，task-split 校准每个模型能做多长的任务。Claude 和 Codex 用的是同一个技能目录，所以学到的东西共用一份。价格表超过 30 天没更新会提醒，提醒后对照官方价格页更新。

## 局限

- 初始参数是带日期的估计值，前几周不准，要靠记录真实结果慢慢校准。
- 成本估计误差大约 ±2 倍，等 ccx 记录到真实用量后再替换。
- “成功”指检查通过；检查本身不严，结论也就不严。
