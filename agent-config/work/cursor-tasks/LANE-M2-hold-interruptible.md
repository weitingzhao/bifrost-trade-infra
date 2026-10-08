# LANE-M2 — `release.sh hold` 要能被干净地停下（TD-269，infra）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支；infra 的**纯脚本 / 文档**改动可以推 main，但本道**只推分支**，因为它改的是发布脚本本身）。报告写到 `cursor-tasks/reports/LANE-M2.md`。
分支：`cursor/m2-infra`（bifrost-trade-infra，从当前 `origin/main` 新开）。

## 背景（台账 `### TD-269`，2026-10-08 一天内撞到两次）

`release.sh hold` 结尾是 `while true; do sleep 3600; done`。bash 会把捕获到的信号**推迟到前台命令返回之后**才处理，所以：

- `kill -TERM <holder>` 最多要等一小时才生效 —— 实测发完信号进程仍然活着。
- `kill -9` 能杀掉，但跳过 EXIT trap，于是窗口文件和 ConfigMap `cicd/bifrost-release-window` 留成**残留锁**；而清锁是 `release.sh window --clear`，规则上归 Owner。10-08 第一次就是这样，花掉了一次 Owner 往返。
- 实际可行的办法是**对它的 `sleep` 子进程**发信号（`pgrep -P <holder>` 再 `kill -TERM`），bash 从等待里返回、trap 正常执行，窗口文件和 ConfigMap 都干净清掉 —— 但这个办法哪儿都没写。

## 要做

1. 让 `hold` 可被信号中断：等在一个信号能打断的东西上。可选做法（你挑一个并说明理由）：
   - `sleep 3600 & wait` —— `wait` 可被信号中断；
   - `read -t` 之类带超时的内建；
   - 直接 `trap … TERM INT` 配合短轮询。
   要达到的效果：`kill -TERM` 之后**一两秒内** trap 跑完、窗口文件与 ConfigMap 都已删除。
2. 在 `docs/RELEASE.md`「发布窗口」一节写清**怎么正常结束一个 hold**，以及残留锁出现时该怎么办。
3. 防线：一条 shell 测试 —— 起一个 `hold`，发 SIGTERM，断言窗口文件在几秒内消失。放进 `scripts/release/` 现有的测试里（那里已经有 `test_release_policy.sh` 这类）。

## 注意

- 不要改窗口的**语义**（互斥、`what` 比对、`--clear` 归 Owner 这些都不动），只改「怎么等」和「怎么收尾」。
- `release.sh` 是所有发布的入口：改完务必自己验一遍 `release.sh window`、`hold`（起停各一次）、以及 `stg --dry-run` 仍然正常。把这三条的输出贴进报告。
- 本道**不推 main**（它改发布脚本，要 Claude Code 验收后合）。不发版、不 apply。

## 验收（Claude Code 会照跑）

起一个 `hold --what bifrost-ui`，`kill -TERM` 它，2 秒后 `release.sh window` 退出码为 0 且 `kubectl -n cicd get cm bifrost-release-window` 为 NotFound。
