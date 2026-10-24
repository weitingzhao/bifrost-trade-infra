# 复核 549 的逐条回应（W-31 4.6 S1，清扫脚本）

被复核范围 `8dd70d59..843a3020`。修改在同一分支 `w31/r4-46-s1` 的新提交 `49f9d864aab733908d00d8418b8e97c3d30e75e1` 里，做法按统筹 10-24 的决定和 549 提的最小修法。
没有推送，没有安装，没有对任何真实目录运行删除模式。对 `~/agent-work` 只跑了 report-only，锁、报告和 journal 都写在 scratchpad。

**验证**
- `python3 -m pytest -q scripts/agent-host`：**126 passed**（agent-host 原有 55 条，disk-guard 71 条）。
- disk-guard 的 71 条用三个解释器都跑过，全部通过：
  - `/usr/bin/python3`（3.9.6）；
  - `/opt/homebrew/bin/python3`（3.14.5），把 DeprecationWarning 当错误跑，仍然通过；
  - pytest 默认用的 3.12。
  - 之所以加跑 3.14：按 LaunchAgent 里的 PATH，实际调用的是 Homebrew 的 3.14，不是系统自带的 3.9（见文末「安装」一节）。
- **阳性对照**：共 97 个变体，91 个让对应测试失败，全是断言失败；6 个是分层对照，测试仍然通过，说明还有另一道保护。
  - 本轮新增 T1–T3、P1–P3、V1–V3、D3、D4、W1；
  - 另外随代码改动更新了 R1、JD2，删掉了 CR2（它对应的放宽已不存在）。
  - 程序在统筹机器的 scratchpad（`mutants2.py`，输出 `mutants6.out`），不进仓库。

## A1 [P2] 续删时只允许清扫自己记下的 chmod —— 已改

- **去掉了对所有目录一律放过 u+rwx 的规则**（`same_entry` 已删除）。
- **chmod 前先留记录**：清扫要给一个目录改 mode 时，先往 `<entry>.chmods` 追加一行（路径、设备号、inode、新 mode），fsync 之后才执行 fchmod。
- **续删时的比对**：只有这里有记录的目录可以和清单不同，而且只能是两种 mode 之一：
  - 原来的 mode（记录写了，但 chmod 前就崩了）；
  - 记录里的新 mode。
  - 其他目录必须和清单完全一致。
  - 每条记录都必须指向清单里的一个目录，设备号和 inode 都要对上，否则整份清单视为不可用。
- **先记录后 chmod**：所以不会出现「已经 chmod、却没有记录」。万一真出现这种状态，目录 mode 对不上，根保留。

测试 `test_disk_guard_trust.py`：
- 清单写好之后、任何 chmod 之前崩溃（新 seam `after_inventory_written`），随后外部把模块目录改成 0755 → 下一轮保留，原因 `changed-since-stopped`。
- 记录过的目录被外部改成别的 mode（0777）→ 保留。
- 547 的「模块目录被清扫改成可写之后崩溃」那条仍然能删完，现在靠的是记录。

阳性对照：
- T1：退回 547 的「任何目录都可多出 u+rwx」→ 外部 chmod 的根被删，测试失败；
- T2：记录过的目录允许任意 mode → 失败；
- T3：chmod 前不写记录 → 547 那条续删不再能删完，失败。

## C1 [P2] 状态文件不受入口 umask 影响 —— 已改

- **文件**：journal、清单、chmod 记录都由写入函数自己用 `os.open(..., 0o600)` 创建；临时文件加 `O_EXCL | O_NOFOLLOW`；再 `fchmod 0600`。之后 fsync 文件、replace、fsync 目录。
- **journal 目录**：
  - 新建时用 0700；
  - 已存在、属于本用户但权限更宽的，收紧到 0700；
  - 属于别的用户的，或者不是目录的，拒绝。拒绝后这一项不改名、不删除，原因 `journal-write-failed`。

测试：
- `test_state_files_are_private_under_umask_022`：在 umask 022 下，原先 0755 的 journal 目录变成 0700，三类文件都是 0600。
- `test_a_journal_path_that_is_not_a_directory_is_refused`。

阳性对照：
- P1：按 umask 建文件 → 0644，失败；
- P2：不收紧目录 → 失败；
- P3（分层）：去掉「不是目录」的检查 → 往一个文件下面写本来也会失败，测试照样通过。
- 「属于别的用户」的目录需要 root 才能造出来，没有测。

## C2 [P2] 清单字段严格校验 —— 已改

- **整数**：每个整数字段必须是真正的 int，不接受 bool 和 float，也不做 `int()` 转换，并且要落在各自的范围里（设备号、inode、mode、大小、两个 ns 时间各有上下限）。
- **其他字段**：
  - 名单必须是字符串列表；
  - `redact` 必须是 true / false；
  - `leaf` 必须是字符串或 null；
  - chmod 记录逐行按同样规则校验。
- **结果**：任何一项不合规，就是「清单不可用」：遗留项保留并报告（`journal-inventory-unusable`），不会抛异常。

测试：`1e400`、`leaf: []`（同时 `redact: true`）、`redact: 0`、签名里的数写成字符串或 true、名单里混进数字，都保留，也都不抛。

阳性对照：
- V1：用 `int()` 转换 → `1e400` 抛 OverflowError，字符串和 true 被接受，失败；
- V2：不查 leaf → 失败；
- V3：不查 redact → 失败。

## 小项 —— 已改

- **措辞**：「just before / 瞬间」改为「在最后一次比对时对上；不保护的是最后一次比对之后、名称操作（unlink，或 rmdir）之前的替换」，并写明目录的 rmdir 要等它下面的东西全部删完才做。「下一轮会删完」改为「剩下的条目和清单对得上、其余检查也都通过时，下一轮才删完」。`disk_guard_apply.py` 的 docstring 和切法 §4.1 都改了。§4.1 还补了一句：journal、清单和 chmod 记录是可信状态，没有认证。
- **续删 cap 根的说明**：改为「finished the removal a stopped sweep began (what was left may be under the cap)」。测试 `test_a_resumed_cap_root_says_what_it_finished`；阳性对照 W1 失败。
- **journal 计数**：
  - 结束时分别报 `open_entries_at_end`（合格的条目）和 `bad_files_at_end`（坏的 .json）；
  - 目录读不了时，`open_entries_at_end` 报 `"unknown"`，不再报 0。
  - 测试 `test_the_journal_counts`；阳性对照 D3（读不了也报 0）、D4（坏文件算进 open）都失败。
- **清单不在内存里一直挂着**：classify 时读一次遗留项的清单，核对完就释放；到删除时再按根从文件读一次（docstring 写明了）。所以同时有多个遗留根时，它们的清单不会一起驻留。

## 安装：第一步是 `--alongside`，和旧的 disk-guard 并排跑（统筹 10-24 追加）

旧的 LaunchAgent 现在还在清理这些东西：复核缓存、node_modules、`/private/tmp/review*`、Docker 等等。如果直接换成只出报告的新版，这些清理会全部停下，而这正是 Owner 最初抱怨的问题。所以先做并排安装：旧的照常运行，一点不动；新版用自己的 Label，只出报告，`--apply` 会被拒绝。这部分在单独的提交 `8532d06216b5d5c100b7201312c0dfc409da258a` 里。

**你要运行的命令**（在这个分支的 checkout 里；合并之后改在主 checkout 里运行；以运行 Agent 的用户身份，不要 sudo）：

```
bash ~/agent-work/r4-46-s1/scripts/agent-host/install-disk-guard.sh --alongside --dry-run   # 先看：只打印，不写任何东西
bash ~/agent-work/r4-46-s1/scripts/agent-host/install-disk-guard.sh --alongside             # 安装
```

**`--dry-run` 打印的内容**：下面是我刚在这台 Mac 上实跑的输出，完整照录（plist 的说明注释和 XML 头省略）。跑完以后核对过，`disk-guard-next` 目录和 `.next` plist 都不存在。

```
install-disk-guard: --alongside --dry-run: nothing is written
would write (directory) /Users/vision-mac-trader/agent-work/bin/disk-guard-next/
would write /Users/vision-mac-trader/agent-work/bin/disk-guard-next/disk-guard.sh
would write …/disk-guard-next/disk_guard.py, disk_guard_base.py, disk_guard_layout.py, disk_guard_roots.py,
            disk_guard_items.py, disk_guard_apply.py, disk_guard_state.py, disk_guard_inventory.py, disk_guard_host.py
            （实际输出里每个文件各占一行）
would write /Users/vision-mac-trader/agent-work/bin/disk-guard-next/cache-roots.tsv
would write /Users/vision-mac-trader/agent-work/bin/disk-guard-next/INSTALLED-BY
would write /Users/vision-mac-trader/Library/LaunchAgents/com.bifrost.disk-guard.next.plist:
      <key>Label</key>                 <string>com.bifrost.disk-guard.next</string>
      <key>ProgramArguments</key>      /bin/bash  /Users/vision-mac-trader/agent-work/bin/disk-guard-next/disk-guard.sh  sweep
      <key>StartInterval</key>         3600        <key>RunAtLoad</key> false   LowPriorityIO true   Nice 10
      EnvironmentVariables:
        PATH                    /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
        AGENT_WORK              /Users/vision-mac-trader/agent-work
        LIFECYCLE_STATUS_DIR    /Users/vision-mac-trader/agent-work/status/disk-guard-next
        LIFECYCLE_LOCK          /Users/vision-mac-trader/agent-work/.lifecycle-next.lock
        LIFECYCLE_MACHINE_ROOTS /Users/vision-mac-trader/agent-work/status/cache-roots.tsv
      StandardOutPath / StandardErrorPath  /Users/vision-mac-trader/agent-work/disk-guard-next.log
would run: launchctl bootout gui/501/com.bifrost.disk-guard.next   (when it is loaded)
would run: launchctl bootstrap gui/501 /Users/vision-mac-trader/Library/LaunchAgents/com.bifrost.disk-guard.next.plist
not touched: /Users/vision-mac-trader/agent-work/bin/disk-guard.sh, /Users/vision-mac-trader/Library/LaunchAgents/com.bifrost.disk-guard.plist, Label com.bifrost.disk-guard
```

上面的 plist 部分为了好读压成了几行；真实输出是完整的 plist XML，逐行缩进打印。

**安装时打印的内容**：我在一个临时 HOME 里用假的 launchctl 实跑了一次，下面是原样输出（`~` 换成了你的 home）：

```
install-disk-guard: installed alongside the old disk-guard, report only
  files:     ~/agent-work/bin/disk-guard-next/ (disk-guard.sh, 9 modules, cache-roots.tsv, INSTALLED-BY)
  plist:     ~/Library/LaunchAgents/com.bifrost.disk-guard.next.plist
  Label:     com.bifrost.disk-guard.next, every 3600 s, first run in an hour: sweep (no --apply)
  log:       ~/agent-work/disk-guard-next.log
  report:    ~/agent-work/status/disk-guard-next/lifecycle.json    lock: ~/agent-work/.lifecycle-next.lock
  registry:  ~/agent-work/bin/disk-guard-next/cache-roots.tsv, then ~/agent-work/status/cache-roots.tsv if it exists
  untouched: ~/agent-work/bin/disk-guard.sh, ~/Library/LaunchAgents/com.bifrost.disk-guard.plist (Label com.bifrost.disk-guard)
  remove:    bash ~/agent-work/r4-46-s1/scripts/agent-host/install-disk-guard.sh --uninstall-alongside
```

假的 launchctl 依次收到两条命令：`bootout gui/501/com.bifrost.disk-guard.next`，然后 `bootstrap gui/501 ~/Library/LaunchAgents/com.bifrost.disk-guard.next.plist`。用真的 launchctl 时，如果 `.next` 还没装过，bootout 会报一个错；这个错被吞掉，不影响安装。

**两边同时跑会不会互相干扰**
- **路径完全分开**：
  - 新版：锁 `~/agent-work/.lifecycle-next.lock/`；报告和 journal 在 `~/agent-work/status/disk-guard-next/`；日志 `~/agent-work/disk-guard-next.log`；Label `.next`。
  - 旧脚本：只写 `~/agent-work/disk-guard.log` 和 `~/agent-work/.cache/docker-pruned-at`，后者新版只读不写。
- **新版只读，不改不删**：它不会去动旧脚本要删的东西。
- **旧脚本删东西对新版的影响**：旧脚本在新版检查时删掉的东西，新版一律记为「保留，原因 `gone`」，本轮照常跑完、照常写报告。三种时机各有测试：
  - 读一个目录的过程中，其中某个条目没了；
  - 根在被找到之后、打开之前没了；
  - 根在检查之后、改名之前没了。
  - 阳性对照 K1–K3 会让这三种情况抛出异常、整轮中止，三条测试都失败。

**同时放进了这个提交的东西**
- 新版和以后的正式安装读同一份机器登记 `~/agent-work/status/cache-roots.tsv`：新增环境变量 `LIFECYCLE_MACHINE_ROOTS`，plist 把它指过去。所以要试登记，只改这一个文件。
- `--apply` 和 `--alongside` 一起用会被拒绝。
- `--uninstall-alongside`（可以加 `--dry-run`）：
  - 只 bootout `.next` 这个 Label，只删它的 plist 和 `~/agent-work/bin/disk-guard-next/`；
  - 报告目录留着，方便你看；
  - 目录里没有安装时写的 `INSTALLED-BY` 标记就拒绝删除。

**测试**：`test_disk_guard_install.py`，用临时 HOME 和假的 launchctl：
- dry run 列出每个文件和完整 plist，跑完 HOME 树一点没变；
- 安装后：文件齐全、plist 每个字段都对、launchctl 的调用都对、旧脚本和旧 plist 一字未变；
- 用 plist 里的环境变量去运行装好的那份副本，确认它只写自己的锁和报告；
- `--apply` 被拒绝；
- 卸载只去掉 `.next`；
- 没有标记文件的目录不删。

阳性对照 I1–I6（对应：放行 `--apply`、用旧的 Label、装进旧目录、和旧版共用默认锁、不检查标记、dry run 真的写了文件），各自让对应测试失败。

**以后切换**（不在这一步）：等报告看下来没问题，再分两步：先用 `--uninstall-alongside` 卸掉试运行；然后由你决定是否用不带 `--alongside` 的安装替换旧的。那一步的行为见下面原来的说明。

## 以后用正式安装替换旧的 disk-guard 时，这台 Mac 上会发生什么（不是这一步）


要在 bifrost-trade-infra 的 checkout 里运行（合并后用主 checkout；现在这个 worktree 是 `~/agent-work/r4-46-s1`），以运行 Agent 的用户身份，不要 sudo。命令：

```
bash bifrost-trade-infra/scripts/agent-host/install-disk-guard.sh --dry-run   # 只打印每一步
bash bifrost-trade-infra/scripts/agent-host/install-disk-guard.sh             # report-only 安装
```

不加 `--apply` 就是 report-only。下面是我刚在这台 Mac 上跑 `--dry-run` 打印出的步骤（`~` 是 `/Users/vision-mac-trader`；`--dry-run` 只在 `$TMPDIR` 里生成一份临时 plist 并做 `plutil -lint`，其他都不动）：

1. 建 `~/agent-work/bin/disk-guard/`，拷入：
   - `disk-guard.sh`（755）；
   - 9 个 `disk_guard*.py`（644）；
   - `cache-roots.tsv`（644，只登记 `.cache/go-build`、`.cache/go-mod`、`.cache/npm` 三个共享根）。
2. 把现有的 `~/agent-work/bin/disk-guard.sh`（旧脚本）改名为 `disk-guard.sh.pre-repo-<UTC 时间>`，用 `mv -n`，不覆盖任何文件。原位置写一个一行的转接脚本：`exec bash ~/agent-work/bin/disk-guard/disk-guard.sh "$@"`。所以派活前跑的 `bash ~/agent-work/bin/disk-guard.sh check` 照常可用。
3. 把现有的 `~/Library/LaunchAgents/com.bifrost.disk-guard.plist` 同样改名留底，装上新的；然后 `launchctl bootout gui/501/com.bifrost.disk-guard`，再 `launchctl bootstrap gui/501 <plist>`。
4. **新 plist 的内容**：
   - Label `com.bifrost.disk-guard`；
   - 运行命令 `/bin/bash ~/agent-work/bin/disk-guard/disk-guard.sh sweep`，没有 `--apply`；
   - `StartInterval 3600`（每小时一次），`RunAtLoad false`（装上后不立刻跑，第一次在一小时后）；
   - `LowPriorityIO`、`Nice 10`；
   - 环境变量 `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin` 和 `AGENT_WORK=~/agent-work`；
   - stdout 和 stderr 都写到 `~/agent-work/disk-guard.log`，和旧的一样。
   - 按这个 PATH，用的是 `/opt/homebrew/bin/python3`（3.14.5）。

**report-only 每小时会做的事**：
- **会写的地方**：
  - 锁：`~/agent-work/.lifecycle.lock/`（目录，里面有 `lock` 和 `owner` 两个文件）；
  - 报告：`~/agent-work/status/lifecycle.json`；
  - 日志：`~/agent-work/disk-guard.log`；
  - Python 自己的 `~/agent-work/bin/disk-guard/__pycache__/`。
- **不会写**：report-only 不会改名或删除任何东西，也不会写 journal。
- **只读不写的操作**：
  - 读两份登记：装好的那份 `cache-roots.tsv`，和 `~/agent-work/status/cache-roots.tsv`（目前不存在）；
  - 全深度读一遍候选缓存；
  - 跑一次 `lsof`，lsof 报 can't-stat 警告时还会读 `/sbin/mount`；
  - 主机步骤：`go env GOCACHE`、对默认 Go 缓存做 `du`、`ipcs -ma`、`docker info`、查看 Cursor 数据库的大小、列出 `/private/tmp/review*`；
  - 登记根如果在 git 仓库里，还会跑 `git rev-parse` / `ls-files` / `status` / `check-ignore`（目前三个共享根都不在仓库里）。
- **耗时**：今天对 `~/agent-work` 用同一 PATH 实跑，约 13 秒；结果是能删的为 0，保留 100 项。

**装上之后，旧 LaunchAgent 每小时做的这些事会停下**，要等以后用 `--apply` 重装才恢复：
- 删已结束复核的 gocache/tmp；
- 删闲置 24 小时的 node_modules/gocache；
- 删 `/private/tmp/review*`；
- 清泄漏的 SysV 共享内存；
- 每周一次的 Docker 清理；
- 低于 15 GiB 时精简 Time Machine 本地快照；
- 默认 Go 缓存超过 30 GiB 时的清理。

这台 Mac 现在剩 359 GiB，report-only 跑一段时间没有风险。

**怎么回退**：
- 改名留底的两个文件（`disk-guard.sh.pre-repo-…`、`com.bifrost.disk-guard.plist.pre-repo-…`）改回原名；
- 再 `launchctl bootout gui/501/com.bifrost.disk-guard`，然后 `launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.bifrost.disk-guard.plist`。

## 仍然没做到

- 逐个系统调用点的 SIGKILL、掉电、跨卷 / bind mount、真实的生产者并发、Linux systemd 都没有实测；
- 大量遗留清单时的内存和耗时没有测过；
- S3、S6、S9 都没做。
- journal、清单和 chmod 记录是可信状态：能改动它们的同用户进程，不在防护范围内。
