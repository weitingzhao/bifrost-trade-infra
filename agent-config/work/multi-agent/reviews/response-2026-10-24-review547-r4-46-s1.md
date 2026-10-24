# 复核 547 的逐条回应（W-31 4.6 S1，清扫脚本）

被复核范围 `d2ff1a28..8dd70d59`。修改在同一分支 `w31/r4-46-s1` 的新提交 `843a3020af40e73a934edc7b25a8c26b014a7524` 里，各条做法按统筹 10-24 的决定。
没有推送，没有安装，没有对任何真实目录运行删除模式。对 `~/agent-work` 只跑了 report-only，锁、报告和 journal 都写在 scratchpad，`~/agent-work` 下没有写入。

**验证**
- `python3 -m pytest -q scripts/agent-host` **117 passed**：agent-host 原有 55 条，disk-guard 62 条。
- disk-guard 的五个测试文件在 `/usr/bin/python3`（3.9）下也全部通过。
- 本机全量跑没有你那边沙箱里的 16 项失败（Gitea 替身绑定 127.0.0.1、SSH-agent 夹具）。
- 阳性对照：86 个变体，每次在副本里去掉一道保护。81 个按要求让对应测试失败，都是断言失败；5 个是「分层」对照，去掉一道后另一道仍然挡住，测试照样通过。
- 本轮新增和改写的变体：M19、M20、R1–R3c、R5、R5b、J1、J3、J4、G1、G1b、E1、E2、CR1–CR4、JD1、JD2。程序在统筹机器的 scratchpad（`mutants2.py`，输出 `mutants5.out`），不进仓库。

## A1 [P1] 最后一次核对与 unlink/rmdir 之间的换名；删除中目录被搬出 —— 按统筹决定作为残余风险接受，不改代码

威胁模型写进了两处：`disk_guard_apply.py` 的模块 docstring，以及切法 §4.1 新增的一条（「删除的保护范围」）。

- **防的是什么**：误删。不防故意和清扫对着干的进程——清扫和所有生产者是同一个用户，那样的进程自己就能删掉自己的材料。
- **保护的**：只有三件事同时成立才删：
  - 根已离开登记名；
  - lsof 没看到其中有打开的文件；
  - 每个删掉的条目，删之前刚和第二次检查的清单对上。
- **不保护的**：
  - 最后一次比对之后、unlink 或 rmdir 之前那一瞬间，把某个名字换成别的材料；
  - 删除进行中把一个目录搬出 quarantine（已打开的句柄会跟着它走）。

## A2 [P2] 空 run id 的后缀 —— 已改

- 现在明确区分两种状态：「没有后缀」记为 `leftover is None`，「有后缀」即使 run id 为空也算（`is_leftover()`）。所有需要 journal 的分支都改为判这个状态，不再看字符串真假。
- `<name>.lifecycle-del-`（run id 为空）直接保留，原因 `unrecorded-quarantine-name`，说明「没有 run id」。报告里显示 `leftover: ""`。
- 测试：`test_an_empty_suffix_is_not_a_leftover`（一个没登记的兄弟目录、空后缀、没有 journal → 保留）。
- 阳性对照 E1：把空字符串当成「没有后缀」→ 被删，测试失败。

## A3 [P2] 清单签名加入完整 st_mode 和文件的 ctime_ns —— 已改

- **签名**：现在是（设备号，inode，完整 st_mode，文件的 size、mtime_ns、ctime_ns）。目录的时间不放进签名，因为删目录里的条目本来就会改变它。
- **清扫自己的 fchmod**：在一次删除里，它发生在这个目录已经比对过之后，所以不会被当成外来变化。续删（见 C1）时只额外允许一种差别：目录的 mode 恰好等于「原 mode 加 u+rwx」（`same_entry(..., swept=True)`），其他任何差别都算变化。
- **测试 `test_a_chmod_after_the_second_check_stops_the_removal`**：第二次检查之后把模块目录 chmod 成可写，或把模块里的一个文件 chmod 成可写，删除都会停下、一件不删、改回原名。
- **测试 `test_a_rewrite_that_keeps_size_and_mtime_stops_the_removal`**：同长度改写文件并恢复 mtime，也会停下。
- **阳性对照**：
  - R3c（只比文件类型）、R3b（不比 ctime）、R3（不比 size/mtime/ctime）都让测试失败。
  - 做 R3c 时发现，对文件做 chmod 本身就会改 ctime，所以只测文件时 R3c 杀不掉。因此测试加了目录这一例：目录没有时间可比，只能靠 mode 发现。
  - 分层：R3a（去掉 size 和 mtime）时，追加内容这一例照样被 ctime 发现。

## A4 [P2] 非规范的 LIFECYCLE_EXCLUDE —— 已改

不再自动改写，而是当作配置错误拒绝，sweep 以 4 退出并写明原因。拒绝的写法：
- 以 `/` 开头或结尾；
- 空段（`//`）、`.` 段、`..` 段；
- 首尾带空白。

`LIFECYCLE_DISCOVER` 走同一个解析函数。测试 `test_non_canonical_exclusions_are_refused` 逐一覆盖：`./lane/cache/00`、`lane//cache/00`、`lane/cache/00/`、`lane/./cache`、`/lane/cache`、` lane/cache`、`lane/../x`。阳性对照 E2（只拒绝 `..`）失败。

## C1 [P2] 中途崩溃后能接着删完 —— 已改

- **新模块 `disk_guard_inventory.py`**：放清单和按清单删除。
- **先写清单**：删第一个条目之前，把第二次检查的清单写到 journal 条目旁边（`<entry>.inventory`）。写完对文件和所在目录都做 fsync。写不了就不删，改回原名。
- **续删**：遇到一个有记录、并且带清单的遗留项，只有满足下面这些才接着删，然后用同一套按清单删除的逻辑删完：
  - 剩下的每个条目都在清单里、签名一致（目录 mtime 不比，允许清扫自己加的 u+rwx）；
  - 没有任何新条目；
  - 不见了的条目视为之前已经删掉（标记最后删，所以标记不见也属正常）。

  这时不再做布局检查，也不再要结束证据和 cap 条件。原因：
  - 上一轮已在完整检查下接受过这份清单；
  - 半删的树本来就过不了布局检查；
  - 删掉条目会改动目录 mtime，于是撞上 `written-after-run-done`，正是你说的永久卡死。

  Git（对原路径做完整检查，含忽略规则）、lsof、排除规则、journal 的身份核对，照旧都做。没有清单的遗留项（崩在删除开始之前）仍走原来的完整复查。
- **标记在每一级都最后删**：包括 go-build-chain 叶子里的 README。
- **测试 `test_disk_guard_recovery.py`**：三个中断点用 `during_removal` 抛出模拟进程死亡，下一轮都能删完，journal 和清单也跟着删掉：
  - 删了桶里第一个文件之后（完整复查会判 `written-after-run-done`）；
  - 0555 模块目录被清扫改成 0755 之后（完整复查会判 `writable-in-module`）；
  - 最后一个标记删完、根还没 rmdir 时（完整复查会判 `layout-marker-missing`）。

  另外两条：
  - 链式缓存叶子里 README 是最后删的；
  - 清单文件损坏 → 保留，原因 `journal-inventory-unusable`。

  原来那条「删除中有新文件写进来」的测试，下一轮现在报 `changed-since-stopped`，新文件保留。
- **阳性对照**：
  - CR1：续删时不用清单，回到完整复查，三个中断点都失败；
  - CR2：不允许清扫自己加的 u+rwx；
  - CR3：删之前不写清单；
  - CR4：续删时要求条目一个不少；
  - R5b：标记只在根一级最后删。

  以上都让测试失败。
- **还没证明的**：清单大小随根里的条目数增长，约每个条目 150 字节；今天最大的共享 go-build 根约 6.7 万个文件，清单约 10 MB。大根的耗时和内存没有专门测过。fsync 只能保证进程崩溃后不丢；掉电没有测。

## D —— 已改

- **坏的 journal 记录**：每条先检查是不是 JSON 对象；不是的写进报告的 notes，不再抛出。测试用 `[]` 和 `null` 两条记录；阳性对照 JD1（不做这个检查）让测试失败。
- **fsync**：journal 和清单都在 replace 之后再对所在目录做 fsync。
- **报告计数**：改为 `journal.loaded_entries`（开始时加载的条数）和 `journal.open_entries_at_end`（运行结束时还没结的条数）。崩溃测试里下一轮应为 1 和 0；阳性对照 JD2 失败。

## 更正 544 回应里 J3 和 G1 的说法

你指出得对。旧 J3 去掉 `git-not-ignored` 这个分支后，后面「返回码非 0」的判断仍然挡住它，结果只是保留原因变成了 `git-error`；旧 G1（不设 literal）同样只把原因改成了 `recheck-git-not-ignored`，因为 `check-ignore` 还在把关。两者都不是「拿掉保护就误删」的证据。

现在：
- **J3**：改成「把返回码 1（不再被忽略）当作通过」，实测记录变成 `deleted`，是真正的阳性对照。
- **G1**：保留原来的变体，但如实写为「只改变保留原因，check-ignore 仍然挡住」。
- **G1b**：新增，同时去掉 literal 和 check-ignore 的「不再被忽略」判断，实测被删。

544 的 RESPONSE 里相应两句已加了更正说明。

## 文件

scripts/agent-host：
- 修改 `disk_guard{,_base,_layout,_items,_apply,_state}.py`；
- 新增 `disk_guard_inventory.py`；
- 修改 `test_disk_guard_removal.py`；
- 新增 `test_disk_guard_recovery.py`；
- `install-disk-guard.sh` 的模块清单更新；
- 切法 §4.1 补了威胁模型一条，锁的写法也更新为 flock。

每个文件都不到 500 行。
