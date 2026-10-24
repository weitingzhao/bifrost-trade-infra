# 复核 550 的逐条回应（W-31 4.6 S1，清扫脚本）

被复核范围 `843a3020..49f9d864`。修改分两个新提交，都在 `w31/r4-46-s1` 上：
- `8532d06216b5d5c100b7201312c0dfc409da258a`：统筹另外要的 `--alongside` 安装器。说明在 `codex-review-549/RESPONSE.md`。
- 本轮 550 的修改：`9f2b3c5666ba6e090514c304ee3e69edd8bf8847`。

没有推送，没有安装，没有对任何真实目录运行删除模式。对 `~/agent-work` 只跑了 report-only，锁、报告和 journal 都写在 scratchpad。

**验证**
- `python3 -m pytest -q scripts/agent-host`：**141 passed**（原有 agent-host 55 条，disk-guard 86 条）。
- disk-guard 的 86 条在 `/usr/bin/python3`（3.9.6）和 `/opt/homebrew/bin/python3`（3.14.5，DeprecationWarning 视为错误）下也全部通过。你说得对：本机的 `python3` 本来就是 3.14，所以 3.9 是单独用系统自带的解释器跑的。
- 阳性对照：116 个变体，每次在副本里去掉一道保护。109 个让对应测试失败，都是断言失败；7 个是分层的，测试仍通过，因为还有另一道检查兜住。
  - 本轮新增 S1–S5、L1–L3、C5、F1；
  - 另外修正了 R1、R2、J1、CR1 这几个变体的替换文本，因为对应代码这轮改了位置。
  - 变体程序在统筹机器的 scratchpad（`mutants2.py`，输出 `mutants8.out`），不进仓库。

## A1 [P2] 读取和续删也走目录检查 —— 已改

- **每轮先查目录**：`journal_load` 一开始就检查 journal 目录。每轮都会加载它，report-only 也一样。
  - 本用户的目录：权限宽了就收紧到 0700，并把目录里每个本用户的普通文件收紧到 0600。不管这些文件这一轮会不会被读到，都会收紧。
  - 不是目录，或属于别的用户：拒绝。拒绝时所有遗留项都保留，原因 `journal-refused`（带上拒绝的原因），没有一项能续删。新的根这时写不了 journal，也不会改名，原因是原有的 `journal-write-failed`。
- **读每个状态文件也查**：journal 条目、清单、chmod 记录都经 `_read_private` 读取：
  - 打开时用 `O_NOFOLLOW`；
  - 必须是本用户的普通文件，否则按「不可用」处理；
  - 权限比 0600 宽就收紧。
- 测试 `test_disk_guard_state.py`：
  - **只有一个旧遗留项**：模拟上一版留下的状态，journal 目录 0755、文件 0644。这个遗留项被排除，所以它的清单这一轮根本不会被读。跑一轮 report-only 之后，目录变成 0700，所有文件变成 0600。
  - **别的用户的目录**：用桩函数把「本用户」换成另一个 uid。遗留项保留，原因 `journal-refused`，说明里写着属于哪个 uid；新的根保留，原因 `journal-write-failed`，没有动。
- 阳性对照：
  - S1（只在写入时查目录）、S2（加载时不收紧文件）、S4（不报拒绝原因）、S5（接受别的用户的目录）都让测试失败。
  - S3（读文件时不收紧）是分层的：整个目录那一遍仍会收紧，测试通过。

## A2 [P2] 诊断信息不带状态文件里的原文 —— 已改

- **只给字段名和序号**：清单和 chmod 记录的校验错误里，不再出现路径、键或名字：
  - `inv entry <i>`、`listed entry <i>`、`chmod record <i>: …`；
  - journal 注记只在文件名是本清扫器自己的命名格式时写文件名，否则写 `#<序号>`；
  - JSON 和 I/O 错误只报异常类型。
- **链式缓存一律脱敏**：只要登记类型是链式（go-build-chain），续删时的提示就强制脱敏，不看清单文件里 `redact` 写的是什么。
- **报告也是 0600**：`status/lifecycle.json` 改用和 journal 相同的写法：0600、`O_EXCL` 临时文件、fsync、原子 replace。
- 测试，用含 `postgres:fake-secret` 的链式夹具：
  - **坏名单**：链式清单里一个键的名单被改成含数字；
  - **坏 chmod 记录**：chmod 记录指向一个带秘密的路径。
  - 两种情况都判 `journal-inventory-unusable`，秘密不出现在报告文件里，也不出现在各次运行的输出里。
  - 另有 umask 022 下报告文件是 0600 的测试。
- 阳性对照：L1（把名单的键写进错误）、L2（把 chmod 记录的路径写进错误）、L3（报告按 umask 建文件）都失败。

## C1 [P3] 清单只放在局部变量里 —— 已改

- `classify` 里的清单只存在局部变量里，`finally` 中清空；Item 上不再有 `resume` 字段，只留一个续删标记。
- 删除时按根从文件再读一次（549 已经这样做）。
- 测试 `test_a_classified_leftover_holds_no_inventory`：直接调 `classify`，让一个遗留项在续删检查时失败；之后这个 Item 的字段里、它的 journal 记录里，都没有清单对象。
- 阳性对照 C5（把清单挂到记录上）失败。

## chmod 记录首次创建时 fsync 目录 —— 已改

- `.chmods` 文件第一次创建并写入后，对 journal 目录做一次 fsync。
- 测试：在模块目录 chmod 时中断，确认目录 fsync 时 `.chmods` 已经在了。
- 阳性对照 F1 失败。
- 范围仍然只覆盖进程崩溃，掉电没有测。

## 对 `~/agent-work` 的 report-only

- 结果和上一轮一样：能删的为 0；20 个复核缓存（10.05 GiB）布局完整确认；lsof `ok`；journal 为 0。
- 报告文件是 0600。
- `~/agent-work` 下没有写入。

## 仍然没做到

- 别的用户真正拥有的目录：要 root 才能造出来，只做了桩测试；
- 逐个系统调用点的 SIGKILL、掉电、短写；
- 跨卷 / bind mount；
- Linux systemd；
- 大量遗留清单时的内存；
- S3、S6、S9。
