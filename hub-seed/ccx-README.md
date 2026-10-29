# ccx 状态目录

relayline（原名 claude-codex-bridge，命令 ccx）的运行状态，两边共用：

- `runs/<run_id>/`：每次子任务的简报、完整事件日志、结果（主导只读压缩结果）
- `ledger.jsonl`：每次子任务的 token / 时间 / 成本账本（`ccx stats` 读它）
- `cursors.json`：两边各自读到的共享记忆位置（增量记忆用）
- `tiers.toml`（可选）：覆盖默认分级配置，只写要改的键

可以安全删除 `runs/` 里的旧目录；不要手改 `cursors.json`。
