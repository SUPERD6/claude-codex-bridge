# changes/

[English](README.md) · 中文

每个 PR 加一个文件，不直接改 `CHANGELOG.md`：这样并行的 PR 不会在 CHANGELOG 上互相冲突。

- 文件名用 `changes/<PR 编号>.md`（如 `changes/21.md`）。PR 还没有编号时先用分支名（`changes/fix-site-out.md`），
  开了 PR 再改名，不改也行：合并时先按编号排，其余按文件名排。
- 内容就是它在 `## Unreleased` 下面的样子：一条或几条 `- ` 开头的条目，续行缩进两个空格，每行约 120 列。和
  CHANGELOG 其他部分一样用英文。
- 功能 PR 不改 `CHANGELOG.md` 和 `docs/STATUS.md`。STATUS 只由主会话（统筹）更新；发版时由主会话把这些文件合进 CHANGELOG：

```bash
python scripts/collect_changes.py --check                                  # 只查格式（测试里也会跑）
python scripts/collect_changes.py                                          # 预览
python scripts/collect_changes.py --version 0.5.0 --title "..." --apply    # 写入 CHANGELOG.md，删掉这些文件
```
