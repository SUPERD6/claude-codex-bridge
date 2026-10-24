# 调研：怎么量化 token 节省（2026-10-23）

[English](2026-10-23-token-cost-quantification.md)

来源：用后台调研工具对论文、官方价格页和工程博客做的一次调研。完整的来源列表在文末。

## 结论

1. **统一单位：按 API 价格折算的美元（折算费）**，不直接比较 token 数。
   - 缓存读取只要原价的 1–10%。
   - Claude 和 OpenAI 的分词器不同，同一段文字 Claude 大约多出 30% 的 token。
   - Codex 的额度点数 = 折算费 × 25（按当前 GPT-6 价格表推算），所以对 Codex 很准。
   - Claude 订阅没有公开换算比例，折算费只是近似值，要用 `/usage` 的百分比来校准。
2. **核心指标：每成功一次的花费（CPS）**，要和“主智能体全部自己做”的对照组比。
   - 节省 = 1 − CPS_ccx ÷ CPS_对照，旁边必须写出成功率的变化，并附 95% 置信区间。
   - 辅助指标：缓存命中率（目标 ≥ 80%）、升级率、开销占比、强模型花费占比、每次成功的耗时、额度消耗。
3. **自己做还是派出去，可以用公式算**。派出去的主要省钱来源是：主智能体不用把文件和日志读进自己的上下文，否则后面每一轮都要再读一遍。主要成本是子智能体的启动开销（实测 Claude Code 每轮约 4.8 万 token，大多是缓存读取）、简报、读回结果和失败返工。
4. **级联规则**：先用便宜的，失败再升级；只有当 C_low < p_low · C_high 时才划算，而且前提是失败能被检查出来。Anthropic 实测：“先用低强度，失败了再用高强度重跑”，成功率不变，成本少约 40%。
5. **对照组从哪来**：实测 A/B（约 10–20% 的任务随机让主智能体自己做）> 固定测试集 > 换价估算。三种必须分开标注。
6. **自适应路由**：每种“任务类型 × 一级”记一组贝塔分布的成功计数；默认选“有把握的最便宜一级”，约 10% 的次数试更便宜一级，旧数据每周 × 0.95 衰减。数据量小时不要用需要上千条标注的复杂路由器（RouterBench 发现它们常常赢不过简单混合）。

## 公式

Claude（`input_tokens` 不含缓存）：

```
AE$ = (in·P_in + w5m·1.25·P_in + w1h·2·P_in + cache_read·k·P_in + out·P_out) / 1e6
```

k = 0.1，Opus/Sonnet 5.5 为 0.05，Fable 5.1 为 0.025。

Codex（缓存是 `input_tokens` 的一部分）：

```
AE$ = ((in − cached)·P_in + cached·P_cached + out·P_out) / 1e6
```

自己做 vs 派出去：

```
C_self  = 自己干活 + 读进来的 token · (P_写缓存 + 剩余轮数 · P_读缓存)
C_deleg = 简报 + 启动开销 + 子任务 + 读回 · (P_写缓存 + 剩余轮数 · P_读缓存) + (1 − p̂) · 返工
C_deleg < C_self 的 85% 才派
```

## 价格（每百万 token，美元，2026-10-23 读取；以官方页面为准）

| 模型 | 输入 | 缓存读取 | 输出 |
|---|---|---|---|
| Claude Opus 5.5 | 4 | 0.20 | 20 |
| Claude Sonnet 5.5 | 2 | 0.10 | 10 |
| Claude Haiku 5.5（≤100k） | 0.10 | 0.01 | 0.50 |
| gpt-6-astra | 10 | 1.00 | 50 |
| gpt-6.1-sol | 2 | 0.10 | 10 |
| gpt-6-luna | 0.10 | 0.01 | 0.50 |

## 要注意的

- 价格和模型每个月都在变，账本里要记下用的是哪一版价格表，以便以后重算。
- 论文里“省 98%”（FrugalGPT）、“省 2 倍以上”（RouteLLM）都是在单次问答上测的。多轮编程智能体的收益会小得多，要用自己的任务验证。
- Claude 订阅的额度换算没有公开，折算费只是近似。

## 来源

- RouteLLM — https://arxiv.org/pdf/2406.18665
- FrugalGPT — https://arxiv.org/pdf/2305.05176
- RouterBench — https://www.alphaxiv.org/abs/2403.12031
- AI Agents That Matter — https://agents.cs.princeton.edu/
- Anthropic：按成本与能力选模型 — https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- Anthropic 价格 — https://platform.claude.com/docs/en/about-claude/pricing
- OpenAI 模型与价格 — https://developers.openai.com/api/docs/models
- Codex 额度换算表 — https://help.openai.com/en/articles/20001106-codex-rate-card
- Claude Code 成本统计 — https://code.claude.com/docs/en/agent-sdk/cost-tracking
- Claude Code 子智能体 — https://code.claude.com/docs/en/sub-agents
- Claude 订阅与 Claude Code — https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
