# agent-delegate（中文说明）

[English: SKILL.md](SKILL.md)

**作用**：通过 ccx 执行已获授权的跨智能体委派，并验收结果；或者在一块大而能检查的活之前，用一句话提议委派（由用户决定）。仅要求拆任务或省 token 不触发委派。

**和另外两个技能的分工**：
- **task-routing**：决定谁做、用哪个模型、用哪档强度、要不要拆开。
- **agent-delegate**（本技能）：负责怎么写简报、怎么派、怎么收、怎么验收。
- **task-checkpoint**：长任务中途断了，从断点接着做。

找不到 ccx 命令时才看 `ccx -h` / `ccx run -h`。

**最大的花费是主智能体自己的上下文**：每一轮都要把整段对话重读一遍。大块阅读（很多文件、长日志、查资料）用只读派出去，只拿回结论。输出很长的命令（跑测试、看日志、`git diff`）用 `ccx sum -- <命令>`：只拿到失败项或按文件的摘要，全文留在磁盘上。`ccx lead` 看你现在每一轮花多少，`ccx lead --breakdown` 看每轮重读的都是什么。

**主智能体是 DeepSeek 时**：ccx 从环境判断谁在当主智能体，不用 `--from`。Windows 上的 dsh 用的是 Windows PowerShell 5.1：用 `& "<python>" "<ccx.py>" run ...` 调用，超过一行的简报写进文件（`--brief-file`）。dsh 要用 `DSH_PERMISSION_MODE=danger-full-access` 运行（否则 ccx 写不了运行记录）；这会让每条命令都带上用户的权限，开口要之前先说明。

## 步骤

0. **提议委派，用户决定**：没人要求委派、但下一块活大（熟练工程师约 15 分钟以上）且能检查时，先 `ccx propose --lead <你的档> --minutes <n> "一句话任务"`。`authorized: true`（总是和 `worth_offering: true` 一起出现；只在用户自己在设置里选了档位 `ccx config set policy.picked <档>` 时才有，你传的任何参数都不会产生它）表示档位已经决定，不用问：把它的 `say` 那句告诉用户，照它的 `next` 为这个任务跑一次（带你提议时给的估计），并按它说的验收（task-routing「档位」）；项目自主级别 L0/L1 仍可能在改文件前停下，那时按输出去问。`worth_offering: false` 就自己做、不提；`worth_offering: true` 但没有 `authorized` 就用它给的那一句话问用户并等待。同意 → `ccx run --proposal <id> ...`（不要加 `--no-ab`），验收后一定 `ccx verify`；不同意 → `ccx propose --no <id>`，自己做，本对话不再提这类活。
1. **沿用已确定的选择**：保留获准的目标、模型、强度和读写范围。指定模型时跳过路由；确实需要选模型才用 task-routing，需要拆任务才用 task-split。必须固定目标/模型时使用 `--no-escalate --no-fallback`。并行也须在授权范围内。自己做、自带子智能体还是 ccx，见 `references/three-way.md`；自己定档（`--tier`）见 `references/rubric.md`。
2. **派得省**（第 5 轮评测，2026-10-26：大任务上用 ccx 的主智能体请求数中位 8 次，用自带子智能体 6 次，多出来的就是下面这些习惯）：
   - **简报 = 用户原话照抄**（尤其接口、名字、精确字符串、数字）+ 你已经知道的文件路径 + 验收命令。不要转述接口（“第一个匹配的提示”被改写成“最早的位置”，结果做错）；不要为了写简报先读代码库或 README/STATUS/文档，子智能体自己读（还会读 `.ccx/context.md`），花的是便宜模型。复用已有 `.ccx/context.md`；只有上下文维护属于本次授权时才更新它。格式见 `references/brief-template.md`。
   - **大活或多文件**：`ccx run --bg ...` 打印 run_id，再 `ccx show <run_id> --wait`，显示还在跑就再调一次。还在跑的运行不要 `ccx resume`。不要把 ccx 输出接到 `tail`/`head`。
   - **几块已获授权的活**：先用 task-split `check` 排计划；改同一个文件的块合成一块或你自己做，绝不并行（干净的 git 检出里，`q run` 让并行的写任务各用一个 worktree；否则都在当前检出里跑）。每块 `ccx q add "<标题>" --brief "..." --check "..."`（有先后用 `--dep <id>`），再 `ccx q run --bg`。自己的块从短到长做，不要碰排队块的文件（它的 undo 快照和验收会把你的改动算进去）。`ccx q ls` 里正在跑的块的 run id 是 `live`：`ccx show <live ids> --any --wait` 谁先结束先交回谁。验收看 check+review 再扫一眼 diff，最后跑所有块验收命令的并集。`waiting` / `unmerged` 下的块是在 worktree 里做的：合并列出的分支，再 `ccx q done <id> --ok 1`，然后重新 `ccx q run`；`dep_blocked` 的块在等一个失败的块（见 `references/three-way.md`）。`last_run` 是 `stopped: backpressure`（额度/登录）时，在额度恢复前不再开新活。
   - **`--review` 保持默认（auto）**；只有高风险或用户能直接看到的改动（以及需要审查通过的 L2 自动合并）才 `--review on` / `--risk visible`。
   - **不要让子智能体提交**（Codex 沙盒禁止写 `.git`）；你验收后自己提交。
   - **用户说到某个项目但没给路径**：先 `ccx where "<用户原话>"`；一个 `pick` 就 `ccx run --project <名字>`，几个候选就问。项目规则讲到审批时 ccx 停下并列出（`approval_rules`）：按规则判断或问用户，之后才加 `--rules-ok` 重跑。细节见 project-manager。
3. **运行**：`ccx run`（带打分参数时自动选模型；默认允许改文件）、`--model/--effort`（自己指定，加 `--minutes` 才能用来校准路由）、`--mode read`（只分析）、`--check CMD`（验收命令，子智能体跑完 ccx 再跑一遍）、`--risk visible` / `--review on|off`（由另一家的便宜模型审改动；auto 时风险高、代码改动 50 行以上、子智能体没把握、说的和实际改动对不上，或证据弱（没有 `--check`、check 不跑测试、跑的测试没提到改动的文件或函数、或验收命令放过过做错的结果；只用另一家最便宜的一档，每天最多 20 次，`weak_daily`）才审）、`--worktree`（在单独的分支上改）、`--bg` + `ccx show <run_id> --wait`、`ccx stop <run_id>`（停掉正在跑的委派，之后可 `ccx resume`）、`--task/--step`（会话 ID 写进 task-checkpoint）、`ccx batch`（并行）、`ccx resume`（同一个子会话里追问或接着做）、`ccx way --risk low|visible|critical`（按风险选做法；critical 约贵一倍，先问用户）。
   - 额度用完/限流：自动换另一个智能体再试一次（`--no-fallback` 关掉）。
   - 超时、崩溃或 `ccx stop`：会话 ID 已经存下，`ccx resume <run_id>` 接着做。
4. **验收**：已经打印出带 `run_id` 的结果就别再派同一份简报，要补充用 `ccx resume <run_id>`。总结只是说法。
   - 结果里有 `needs_lead`、`edited_tests` 或 `namecheck` 时**先看它们**（`namecheck`：改动的函数里没有任何作用域定义的名字，多半是测试没覆盖到的 NameError）。
   - `check` 通过且跑的是相关测试，再看 `files_changed` / `diffstat` 就够了，**不要自己重跑**（H11 实测 2026-10-24）。只有 check 失败、没有、带 `weak`（这个命令在这里放过过做错的结果），或状态是 partial/blocked 时，才自己跑测试或读完整 diff。
   - `check_broken` = 验收命令什么都没测：`ccx resume <run_id> --check "..."`。任务点名了一个入口（命令、CLI）却没有测试把它当真实进程跑：resume 一次，要求补一个。
   - `verification: not-run` 就照实说“没验证”。
   - `review` 是独立审查：`pass` 或 `issues`（带文件:行）。ccx 自己会跑一轮修改（`show --wait` 会等它）；之后的 `needs_lead` 由你决定，`review_failed` 见下一条。`kind` 只按 `ccx show <run_id> --wait` 的结果判断（不带 `--wait` 的 `show` 可能在修改轮开始前看到第一条记录，这时续跑会和修改轮撞上）。`--wait` 之后仍是 `review_issues`，说明修改轮没跑成（没有可续的会话，或没能启动）：自己改，或重新派。
   - `review_failed`（修改轮之后审查仍不过）：对着 diff 逐条核对 `[must]` 项，属实的自己修，不属实的放下；不要为此 `ccx resume`。
   - 然后 `ccx verify <run_id> --ok 1|0 [--reason unfinished|wrong|overreach|other]`：校准路由（给了 `--minutes` 还校准拆分），并把 checkpoint 的这一步标成完成。没人判断的运行，12 小时后验收或自查通过、审查也通过会记成“大概率对”；`ccx undo --apply` 撤回的等你判，加 `--wrong` 同时记成“错”。只要真的看过，就记一下。
5. **换主智能体**：用户说“交接给 X”时，自己还能写就 `ccx handoff --by <你> --to X "…"`；原主智能体写不了（额度用完、崩了、窗口关了）就 `ccx handoff --from-transcript <原主智能体> --to X`。接手方先核对其中的说法。自己的对话太长、下一块又是新活时：先问用户，再 `ccx fresh`（用本对话的记录写交接，新对话开局就能看到）。
6. **记忆**：只有记忆维护已获授权时，才用 `ccx mem add` 保存必要的长期事实（`--project` 写进本项目 `.ccx/` 的日志；`ccx project status` 看这一层）；委派任务本身不授权写入记忆。
7. **代价高的决定**（难撤回、涉及安全或钱、用户说很重要）：像第 0 步一样先一句话提议 `ccx discuss`（`--dry-run` 给出参与者、最多几次调用、估价和各自用的模型；不带 `--confirmed` 只给估价，不会真跑），用户同意才 `ccx discuss --confirmed "问题"`；结果只是建议，用户可在 `ccx ui` 看讨论过程。
