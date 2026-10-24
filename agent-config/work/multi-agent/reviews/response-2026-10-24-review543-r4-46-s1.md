# 复核 543 的逐条回应（W-31 4.6 S1，清扫脚本）

被复核提交 `12938a90`。修改在同一分支 `w31/r4-46-s1` 的两个新提交里：`761e34c4` 是逐条修改；之后按统筹 10-24 对两个问题的决定又补了一个小提交 `d2ff1a285bec8d031e6272002e627840bfce2218`，改动见本文 A3 和 A2 末尾。
不推送、不安装；没有对任何真实目录运行删除模式。对 `~/agent-work` 只跑了 report-only，锁和报告都重定向到 scratchpad，`~/agent-work` 下没有写入。

验证（补提交之后）：`python3 -m pytest -q scripts/agent-host` **95 passed**（agent-host 原有 55 条 + disk-guard 40 条）；本机 Gitea/SSH 夹具都能跑，没有你那边沙箱的 16 项失败。
disk-guard 的 40 条在系统自带的 Python 3.9（`/usr/bin/python3`，即 launchd 下的解释器）也通过。
阳性对照：56 个变体，每次在副本里拿掉一道保护。52 个按要求让对应测试失败，全是断言失败、没有崩溃；另 4 个是「分层」对照，只拿掉其中一道，另一道仍然挡住，测试照样通过（见 A2、A3）。
变体程序在统筹机器的 scratchpad（`mutants2.py`，输出 `mutants3.out`），不进仓库。

## A1 [P1] 开放子树 —— 已改

`disk_guard_layout.py` 改成每一级只接受该布局在这一级会写的条目：

- **npm `_cacache/tmp`**：必须为空，否则整根保留（`unverified-subtree`）。tmp 里的文件分不出是工具的还是人的，按你的建议只报。
- **Go `cache/vcs`**：必须为空（`unverified-subtree`）。里面是 VCS 克隆，和人的仓库分不开。
- **`cache/download/sumdb`**：只接受 `<host>/lookup/**` 下名为 `module@version` 的文件，和 `<host>/tile/**` 下 `N` / `xNNN` / `NNN.p` / `data` 目录里的纯数字文件。规则先对过本机 `~/go/pkg/mod` 的真实 sumdb 再定。
- **`@v`**：文件名必须是 `list`、`list.lock` 或 `<语义化版本>.(info|mod|zip|ziphash|lock|partial)`。以前只看后缀，`notes.zip` 能过。
- **模块路径**：`@` 目录必须是 `<module>@<version>`；模块目录以外的文件不接受；模块内容仍要求只读（Go 解压时就是只读）。
- **源码扩展名兜底**：在解压出来的模块源码以外，凡是 `.go/.md/.txt/.py/.sh/.json/.yaml/.log/...` 这类后缀的普通文件，一律整根保留（`handwritten-file`）。npm `_logs` 和 Go 根上的 `trim.txt` 按名字单独认。
- **其他收紧**：`trim.txt` / `testexpire.txt` 内容必须是时间戳；`cache/lock`、`_update-notifier-last-checked` 必须是空文件；`<hash>-d/` 里只允许一个可执行文件，名字带源码后缀也不行。

测试 `test_material_in_the_formerly_open_subtrees_stays` 覆盖这些用例：npm tmp 放在 git ignored 的根里，tmp 里分别放无后缀文件和 `draft.go`；vcs、sumdb lookup、tile、`@v/notes.zip`、`-d/draft.go`、写坏的 `trim.txt`。阳性对照 A1a–A1g、M3–M5 全部让测试失败。

反向验收，防止收得太紧：
- `test_a_real_sumdb_and_an_empty_tmp_go`：合法的 sumdb、空的 vcs 能删。
- `test_what_the_real_tools_write_is_accepted`：用真的 `go run`（经 `file://` 代理下载依赖，同时产出 `-d/` 可执行项）和 `npm pack` + `npm cache add` 在临时目录里产出缓存，三种都必须判为可删。回答你 B 节说的「real cache 夹具由测试拼装」。
- 对真实 `~/agent-work` 的 report-only：20 个布局确认且有 `run.done` 的复核缓存（10.05 GiB）收紧后仍全部确认，没有误伤。

## A2 [P1] 路径在两次检查之间被换 —— 已改

现在**路径只解析一次，之后只用目录句柄**：

1. sweep 一开始打开 AGENT_WORK 的句柄。
2. 第一次检查从这个句柄出发，用 `O_DIRECTORY|O_NOFOLLOW` 逐级打开，记下每一级的（设备号，inode）。布局遍历全程走 `dir_fd`：`os.stat(..., dir_fd, follow_symlinks=False)`、`os.open(..., O_NOFOLLOW, dir_fd)`；子目录打开后再比一次 inode，变了就停。
3. 改名前从 AGENT_WORK 重新逐级打开父目录链，每一级身份都要和初查一致；用父目录句柄 `renameat`，改名后核对新名字仍是同一个 inode，不一致就改回并保留。
4. 复查：经父目录句柄打开改名后的目录、核对 inode、全量布局校验。Git 和 lsof 只认路径，所以复查时还要确认从 AGENT_WORK 出发的路径仍然通到同一组目录，AGENT_WORK 本身的身份也要一致。
5. 删除：递归删除用 `unlinkat` / `rmdir(dir_fd)`，每进一级都比 inode 和设备号；只读目录用 `fchmod` 在句柄上补权限，不再出现绝对路径。
6. 任何一步失败，在原父目录句柄里改回原名，并在报告里写原因。

测试 `test_disk_guard_hardening.py` 的 `Paths543` 三条，都用可注入的钩子，只在临时目录里操作：
- 初查后、改名前把父目录换成指向根外一份完整复核目录的链接；
- 改名后把父目录换成链接，根外还预先放了同名的改名目录；
- 改名前把根换成另一个合法缓存目录。

三条都断言：根外的东西还在，原目录还在（或已改回），项目状态是保留。

阳性对照：
- 同时去掉 `O_NOFOLLOW` 和身份比较（A2a、A2b）：根外目录被删，测试失败。
- 只去掉身份比较（A2c）：根被换的那条失败。
- **分层**：只去掉 `O_NOFOLLOW`（A2d），或只去掉身份比较时跑换链接的用例（A2e），测试仍然通过，因为另一道还在。这两条记作纵深防御，不是漏洞。

**与切法的一处偏离（统筹 10-24 已接受，切法 R9 已同步改写，并写明理由）**：R9 共享根超上限时，原来调 `go clean -cache` / `-modcache` / `npm cache clean`。这些工具按路径操作，绕开了句柄锚定，等于重新打开 A2。现在改为和其他根走同一套「改名 → 复查 → 句柄删除」，整根删掉，效果和这三个命令相同（都是清空整份缓存）。测试 `test_shared_roots_over_the_cap_are_removed_after_the_same_checks`，包括修剪期间被写入手写文件的情况，对应你 B 节「工具修剪时发生变化」。

## A3 [P2] lsof 警告 —— 已改（补提交按统筹决定定稿）

第一版加过一个可配置开关 `LIFECYCLE_LSOF_TOLERATED_MOUNTS`。统筹决定**去掉这个开关**：这台 Mac 报警的挂载点路径里带 UUID，配死的路径会过期。

改成固定规则：stderr 只允许一种内容，就是 lsof 的三行 can't-stat 警告。
第一行 `lsof: WARNING: can't stat() <type> file system <path>`，后两行都以空白开头，必须正好是 `Output information may be incomplete.` 和 `assuming "dev=…" from mount table`。
同时要求：`<path>` 是绝对路径；是当前挂载表里的一个挂载点（读 `/sbin/mount` 的输出，不 stat，因为失败的正是 stat）；和 AGENT_WORK、以及被检查的根，在任何方向上都不互相包含。

除此以外一律保留：任何别的 stderr 行、后两行对不上、挂载表读不到或为空、lsof 非零退出。
挂载表的两种格式都能解析：macOS 的 `… on <path> (<type>, …)` 和 Linux 的 `… on <path> type <type> (…)`。报告的 `lsof.tolerated` 列出放过的挂载点。

测试 `test_the_cant_stat_warning_for_an_outside_mount`：
- 真实三行形式、挂载点在根外 → 放行；
- 同样形式，但指向 AGENT_WORK / AGENT_WORK 的上级 / AGENT_WORK 里的挂载点 / 不在挂载表里的路径 / 多一行未知警告 / 第二行不同 / 缺第三行 / 相对路径 / 挂载表读失败 → 都保留。

`test_the_mount_table_in_both_formats` 覆盖两种格式的解析（含带空格的挂载点）。`test_lsof_failure_keeps_everything` 保留了失败、静默失败、祖先挂载点和子挂载点那几个用例。

阳性对照：
- 去掉与 AGENT_WORK 的重叠检查（L1）、挂载表成员检查（L2）、后两行检查（L3）、挂载表读失败处理（L4），或跳过其他 stderr 行（L5、L6），对应测试都失败。
- **分层**：只放开相对路径（L7），挂载表检查仍然挡住；只去掉逐根重叠检查（L8），AGENT_WORK 的检查已覆盖它下面的每一个根。这两条测试仍然通过。

真实 lsof 的「打开文件」测试直接用真的 `/sbin/mount`，不再需要任何配置。对 `~/agent-work` 的 report-only 里，lsof 现在是 `ok=true`，只放过了 1 个挂载点（备份共享）。

## A4 [P2] AGENT_WORK 在 Git 仓库里 —— 已改

`git_top()` 现在一直往上找到 `/`，并以 `git rev-parse --show-toplevel` 为准。调用前清掉继承的 `GIT_*` 环境变量（包括 `GIT_CEILING_DIRECTORIES`），并设 `GIT_DISCOVERY_ACROSS_FILESYSTEM=1`。

只有在「往上没有任何 `.git`」**并且** Git 也说不是仓库时，才当作不在仓库里。其余情况，比如有 `.git` 但 Git 报错、Git 给的顶层不包含这个根，一律 `git-error` 保留。

测试 `test_a_repository_above_agent_work`：AGENT_WORK=`repo/scratch`。被跟踪的保留，未忽略的保留，被忽略的可删。阳性对照 A4（恢复「找到 AGENT_WORK 就停」）让测试失败。

## B 测试覆盖 —— 能并的都并了

| 你指出的缺口 | 处理 |
|---|---|
| 单独的 `git status` 读取失败 | 新测试，用假 `git` 只让 status 失败 → 保留；阳性对照 B |
| 改名后没有重验原路径的 ignore | 改名**之前**在当时的名字上跑完整 Git 检查（ls-files 加 `status --ignored`）；改名后原路径已不存在，只能查 tracked，所以复查只跑 ls-files |
| `run.done + 60 秒` 的放行 | 宽限期去掉：缓存里任何一项比 `run.done` 新就保留。新测试覆盖同一时刻可删、晚 5 秒保留；阳性对照 M12d |
| 两个清扫器同时接管死锁 | 锁改为 `mkdir` 锁目录加锁目录里文件的 `flock`。持有者死了内核自动放锁，不再有「判死锁 → 接管」这一步，竞争也就不存在了。`owner` 文件只用来报告是谁持有。阳性对照 M18、M18b |
| 工具修剪时发生变化 | 见 A2：共享根也走改名加复查，有测试 |
| real cache 夹具是拼的 | 见 A1：真 go/npm 产物的验收测试 |
| 跨文件系统、真实安装与调度、Linux 实跑、七天观察、会话恢复 | **没做**。跨文件系统要真挂载；安装和七天观察属于 S8/S9；会话恢复属于 S3。都记在这里，没有当作完成 |

## B 与旧脚本的差异，以及会让磁盘重新涨满的风险

| 差异 | 处理 |
|---|---|
| 闲置 node_modules 不再按时间删 | 不恢复按名字删。现在把 AGENT_WORK 下 4 层以内的每个 node_modules 逐个列进报告（路径和大小，原因 `unmanaged-node-modules`）。今天 13 个，1.79 GiB。删除要等 S3 的登记和结束记录，在那之前由统筹按清单处置。更深的层级没有遍历 |
| `/private/tmp/review*` 只报不删 | 报告里列出每一项的大小和天数，今天没有。登记格式只认 AGENT_WORK 以内，以后由产生它们的工具改用登记根 |
| Docker 周期时间戳换位置 | 新旧两个时间戳都读，取较新的那个，首次 apply 不会重复清。今天显示 2.5 天前清过 |
| lsof 的可见范围 | 和旧脚本一样只看得到本用户的进程，报告里写明。警告的处理见 A3：备份共享那条三行警告按挂载表放过，本机的清扫不再因它而全部保留 |
| 默认装成 report-only | 报告 `mode` 字段和安装脚本的输出都写明当前模式。验收时要记录实际的安装模式，不能把「定时器装上了」当作「容量治理已生效」 |
| 默认登记只有三个共享根 | 历史的 20 个复核缓存要先写进机器本地的 `status/cache-roots.tsv` 才会清（539 的 A 选项）。派活前接 `check`、§4.5 的实时 statfs 与并发预算是 S6 的事，也没有七天数据，**所以现在不能承诺不会再满** |

## C 非有限数 —— 已改

`_float()` 拒绝 NaN 和 ±Inf（`1e400` 也算），check 遇到退回 2，sweep 遇到退出 4。
登记表里 `cap=inf/nan/1e400` 作为登记错误报告，同时捕获了 `OverflowError`。阳性对照 C 失败。

## 文件

scripts/agent-host：
- `disk_guard{,_base,_layout,_roots,_items,_host}.py` 修改；
- 新增 `disk_guard_apply.py`（锁、改名、复查、句柄删除），由原来的 items 模块拆出，每个模块都不到 500 行；
- `test_disk_guard.py`、`test_disk_guard_runs.py` 修改；
- 新增 `test_disk_guard_hardening.py`；
- `install-disk-guard.sh` 的模块清单更新，并新增一条测试保证它与目录里的 `disk_guard*.py` 一致；
- `cache-roots.tsv` 注释更新。
