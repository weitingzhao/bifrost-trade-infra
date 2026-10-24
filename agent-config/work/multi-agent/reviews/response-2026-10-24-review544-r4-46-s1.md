# 复核 544 的逐条回应（W-31 4.6 S1，清扫脚本）

被复核范围是 `12938a90..d2ff1a28`。修改在同一分支 `w31/r4-46-s1` 的新提交 `8dd70d59a432d16be5a78ea539650b33818352ab` 里。各条怎么改，按统筹 10-24 已做的决定执行。
没有推送，没有安装，没有对任何真实目录运行删除模式。对 `~/agent-work` 只跑了 report-only，锁、报告和 journal 都写在 scratchpad，`~/agent-work` 下没有写入。

**验证**
- 全量：`python3 -m pytest -q scripts/agent-host` **107 passed**（agent-host 原有 55 条，disk-guard 52 条）。
- 四个 disk-guard 测试文件在 `/usr/bin/python3`（3.9）下也全部通过。
- 阳性对照：73 个变体，每次在副本里拿掉一道保护。69 个按要求让对应测试失败，都是断言失败，没有崩溃；另 4 个是分层对照，只拿掉一道，另一道仍挡住，测试照样通过。本轮新增的是 R1–R5、J1–J5、X1–X2、G1、N1–N2、K1、D1–D2，列在下文各条。
- 变体程序在统筹机器的 scratchpad（`mutants2.py`，输出 `mutants4.out`），不进仓库。

**关于 NODE_USE_SYSTEM_CA**：你那边真实工具测试里 `npm pack` 以 -11 退出（`SecItemCopyMatching failed -50`）。原因是继承了 `NODE_USE_SYSTEM_CA=1`，node 去读钥匙串，而沙箱拒绝。现在测试自己清掉这个变量。本机这个变量本来就是 1，测试照样通过；用 `env -u NODE_USE_SYSTEM_CA` 跑也通过，所以测试不再依赖调用者的环境。

## A1 [P1] 删除绑定到第二次检查的清单 —— 已改

- **清单**：`Walker` 现在记下它接受的每个条目，键是相对根的路径，值是（设备号，inode，类型，文件的 size 和 mtime_ns），还记下它完整读过的每个目录的名单。第二次 `validate()` 返回的就是这份清单（`disk_guard_layout.py`）。
- **只删清单**（`disk_guard_apply.py` 的 `remove_checked`）：
  1. 先拿整棵现存树逐项对照清单，全部对上才动手。任何条目是新的、缺失、被替换或内容变了，就一件都不删，把根改回原名，记为 `stopped-before-removal`。
  2. 删除时每一级再对一次：目录名单必须和清单一致，每个条目的特征都要相同；子目录打开后再核对 inode。第一处不一致就停下。
  3. 删目录用 `rmdir`。删的过程中有人往里放了东西，`rmdir` 会失败，同样停下。
- **从不删清单之外的东西**，没有「重新列一遍、全部删掉」这条退路。旧的 `_empty` / `remove_at` 已删除。
- **中途停下时**：已删的部分是检查过的缓存条目，对缓存来说可以接受，这一点写在模块 docstring 里。剩下的留在 quarantine 名字下，journal 条目也保留，报告写 `partly removed, stopped: <条目> …`，新放进去的东西原样留着。下一轮按 journal 把它当遗留项接上，因为里面有了新材料，布局检查不过，照旧保留并报告。
- **标记文件最后删**：`README`、`cache`、`_cacache` 放在最后，停下后留下的仍能认出是哪种缓存。
- **新增 seam**：`between_recheck_and_remove`，位置在 Git 和 lsof 复查之后、删除之前。另有 `during_removal`，每删一项后调用。

测试 `test_disk_guard_removal.py` 的 `Removal544` 四条：
- 第二次检查之后加一个文件 → 一件不删、改回原名、新文件在；
- 换掉一个子目录 → 同上，原子目录完整在根外；
- 原地改写一个文件 → 停下；
- 删的过程中往还没删到的目录里加文件 → 部分删除、留在 quarantine 名字下、新文件在、标记文件还在、journal 还在。下一轮复跑仍然保留。

阳性对照：
- R1：退回「重新列目录全部删除」，第一、二条失败；
- R2：去掉删前整树对照，原地改写那条失败（变成部分删除）；
- R3：不比 size 和 mtime，原地改写那条失败；
- R5：标记文件不放最后，部分删除那条失败。

## A2 [P2] 遗留项只认 journal —— 已改

- **新模块 `disk_guard_state.py`**：每次改名之前，在状态目录的 `lifecycle-journal/` 写一条记录（原路径、quarantine 路径、根的设备号和 inode、run id），写完 `fsync`。根删掉或改回原名之后删掉这条；写不了 journal 就不改名。
- **只认有记录的遗留项**：一个 `.lifecycle-del-` 目录，只有 journal 里有条目、而且原路径和身份都对得上，才算遗留项。否则记为 `unrecorded-quarantine-name`，只报告。quarantine 路径已经不存在的条目没有用处，加载时删掉并在报告里写一句。
- **Git 检查回到原路径**：恢复遗留项时，对原路径重新做完整的 Git 检查（新函数 `check_original`）：原路径下没有被跟踪的文件，并且 `git check-ignore` 仍判它为忽略（原路径不存在也能查）。本轮正常改名的项，复查时也对原路径做同样的检查。
- **一个实测发现**：`check-ignore` 不接受 `GIT_LITERAL_PATHSPECS`，会报「pathspec magic not supported」，所以这一处单独以 `./<路径>/` 的形式传参。没有哪种 pathspec magic 以 `./` 开头；结尾的 `/` 让 `dir/` 这类只匹配目录的规则对一个不存在的路径也能生效。两点都在本机核对过。

测试：
- `test_a_rename_left_by_a_dead_sweep_is_finished_or_kept`：有记录 → 删除，journal 条目跟着删；有记录但含手写文件 → 保留；没有记录 → 保留；记录的身份不同 → 保留。
- `Journal544`：改名前 journal 已写、删完即删；原路径的忽略规则被撤销 → 保留，规则还在 → 删除。

阳性对照：J1（无记录也算遗留项）、J2（不比身份）、J3（不查忽略规则）、J4（改名前不写 journal）、J5（删完不删 journal 条目），都失败。

> **更正（复核 547 指出）**：这里的 J3 只去掉了 `git-not-ignored` 这个分支，后面「返回码非 0 即报错」的判断仍然挡住它，所以测试失败只是因为保留原因变成了 `git-error`，不是「拿掉保护就误删」的证据。现在的 J3 把「不再被忽略」当作通过，实测会被删；见 `codex-review-547/RESPONSE.md`。

## A3 [P2] 排除规则双向，并对原路径生效 —— 已改

`LIFECYCLE_EXCLUDE`，以及锁目录和状态目录，现在对候选的当前路径和逻辑原路径都做双向重叠判断。
测试 `test_exclusions_overlap_both_ways` 覆盖你给的两个例子：
- 排除 `.cache/go-build` 时，有 journal 记录的 `.cache/go-build.lifecycle-del-…` 保留；
- 登记 `lane/cache`、排除 `lane/cache/00` 时整根保留。

阳性对照 X1（只判一个方向）、X2（只看当前路径）失败。

## A4 [P2] Git 路径一律按字面 —— 已改

清掉继承的 `GIT_*` 之后，固定设 `GIT_LITERAL_PATHSPECS=1`；`check-ignore` 的例外见 A2。
测试 `test_a_directory_named_like_pathspec_magic`：名为 `:(literal)cache`、其中有被跟踪文件的已登记目录 → 保留（`git-tracked-inside`）。阳性对照 G1（不设这个变量）让它被删，测试失败。

> **更正（复核 547 指出）**：G1 实际没有让它被删，只是保留原因从 `git-tracked-inside` 变成了 `recheck-git-not-ignored`，因为复查时的 `check-ignore` 仍然挡住它。同时去掉 literal 和这道检查的 G1b，才会被删；见 `codex-review-547/RESPONSE.md`。

## C1 npm 的 `_lastverified` —— 已改；按设计保留的几类分开写原因

- `_cacache/_lastverified`：只在它是普通文件、内容只有 1–20 位数字（npm 写的毫秒时间戳）时接受。类型、链接、身份检查照旧。
- 真实工具测试在 `npm cache add` 之后加了 `npm cache verify`，并断言产物里确实有 `_lastverified`、整根可删。
- 测试 `test_npm_lastverified`：内容是时间戳 → 可删；内容是一句话 → 保留。阳性对照 N1（不认这个文件，真实工具测试也一起失败）、N2（不查内容）失败。
- 按 544 同意的取舍继续保留、但各自写明原因，让 Owner 看得出为什么这份缓存没被回收：

  | 原因 | 情况 |
  |---|---|
  | `npm-npx-installs` | npm `_npx` |
  | `npm-tmp-not-empty` | `_cacache/tmp` 非空 |
  | `go-vcs-checkouts` | Go `cache/vcs` |
  | `go-download-tmp` | `@v` 里的 `.tmp` 残留 |
  | `writable-in-module` | 模块目录可写，说明写明「手放的，或 -modcacherw」，并改正了原来「可写一定是手写」的注释 |

  这些原因都进报告的 `kept_reasons`。测试 `test_kept_by_design_says_why`；阳性对照 K1（`_npx` 退回 unknown-entry）失败。

## D 次要项 —— 已改

- **`/private/tmp/review*`**：每一项都写进结构化的 `entries`（名字、大小、大小是否完整、天数）。超过 500 项时写明截断和剩余数量。目录可用 `LIFECYCLE_TMP_ROOT` 指定，测试用它指到临时目录。测试 `test_every_tmp_review_entry_is_listed` 列 25 项；阳性对照 D2（截到 20）失败。
- **`du()`**：现在返回（字节数，是否完整），遍历中有读错就标 `bytes_complete=false`，用于 node_modules、未登记缓存和临时目录。测试 `test_sizes_with_read_errors_are_incomplete`；阳性对照 D1 失败。
- **切法 R9 改了措辞**：整个根都删，只删第二次检查清点过的条目；npm 根里的 `_logs` 和 `_update-notifier-last-checked` 也一起删，而 `npm cache clean` 只删 `_cacache`、会留下这两样。模块 docstring 和 `cache-roots.tsv` 里原来「效果同 go clean / npm cache clean」的说法一并改了。

## 文件

scripts/agent-host：
- 修改 `disk_guard{,_base,_layout,_roots,_items,_apply,_host}.py`；
- 新增 `disk_guard_state.py`（锁和 journal）；
- 修改 `test_disk_guard{,_runs,_hardening}.py`；
- 新增 `test_disk_guard_removal.py`；
- `install-disk-guard.sh` 的模块清单加上 state 模块，已有测试会核对清单和目录一致；
- `cache-roots.tsv` 注释更新；
- 切法 `agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md` 的 R9 一行。

每个文件都不到 500 行。

## 仍然没做到

- 跨文件系统和 bind mount 的实测；
- 真实安装与调度、Linux 实跑；
- 会话恢复（S3）；
- 派活前的实时余量门槛与并发预算（S6）；
- 七天增长观察（S9）。

所以仍然不能承诺装上之后磁盘不会再满。
