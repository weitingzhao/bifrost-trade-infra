# 切法：agentd 的执行者只写自己的工作区（TD-371 + 2.3 补强「隔离、根目录只读」）

起草 2026-10-19（侧线 `w31/agentd-confine`，统筹线程 `local_accccb4e…` 派）。只改 `bifrost-platform` 的 agentd；不改公开接口、不加外部依赖、不碰 06、不发版。06 上要 Owner 跑一次的探针在 §8。

## 1. 要解决什么

今天 06 上的单元（`bifrost-agentd*.service`）已经把整个 agentd 进程树关在 `ProtectSystem=strict` + `ReadWritePaths=/home/<agent 用户>` + `PrivateTmp=yes` 里：执行者写不了系统，但**整个 agent 用户的家目录**都能写——令牌文件、`registry.json`、别的任务的工作区、`~/.codex` / `~/.claude` / `~/.cursor` 的配置，和所有尝试共用的 `/tmp`。所以 `share.go` 的 `confined` 一律返回 false，每次尝试独占主机（TD-371，复核 277、278、283）。

做完的标准（统筹线程给的）：

1. 每个执行者（codex、cursor、claude、deterministic，连同 setup 命令）**整个进程树**只能写：自己的工作区 `a.Dir`、自己的输出 `a.Dir.out`、本任务 spec 点名的 sibling 克隆。别处一律写不进（家目录、agentd 根、别的尝试、共用 `/tmp`）。这就是 2.3 的「隔离」与「根目录只读」在 agentd 这一侧的那一半。
2. 每次尝试有自己的配置目录：`HOME`、`CODEX_HOME`、`CLAUDE_CONFIG_DIR`、Go 和 npm 的缓存、`TMPDIR` 都在这次尝试的输出下，新建、空的；凭据由 agentd 放进去；之前的运行写不进来。
3. `confined` 只在这些钉子都在、并且主机上证明过墙挡得住时，才把这个执行者算作可共享主机。

不在这一切里（照旧是第 2 轮的例外，v5 §6.2「同一系统用户」、§7 第 7 条 ②）：**读**。同一用户下令牌文件仍可读；本切只管写。

## 2. 墙用什么：Landlock（不用外层 bubblewrap）

| | A. Landlock（推荐，本切采用） | B. 外层 bubblewrap（像 bench 那样） |
|---|---|---|
| 怎么钉 | 内核 LSM，非特权：进程给自己加一组「只能写这些目录」的规则，之后它和它所有的子孙都改不回去 | 新的 user + mount 命名空间：根只读绑定、`/home` 换成空 tmpfs、只把自己的目录绑成可写 |
| 06 上的前提 | 内核 ≥ 6.2（ABI 3，管住 truncate），Ubuntu 24.04 的 6.8 是 ABI 4；`lsm` 里有 landlock（Ubuntu 默认有）。单元已有 `NoNewPrivileges=yes` | 只有 codex 自带的那个 bwrap 能建 user 命名空间（AppArmor `bifrost-codex`）；再嵌一层 codex 自己的 bwrap，要实测 |
| 经 `/proc/<pid>/root` 逃出去 | 堵住：同一挂载命名空间里路径就是原路径，照样按规则拒；另外 Landlock 的 ptrace 规则不让域里的进程打开域外进程的 `/proc/<pid>/{root,cwd,environ,mem}` | **堵不住**：没有新的 pid 命名空间（单元的 `ProtectKernelTunables` 等让新 `/proc` 挂不上，bench 10-18 实测），域里进程能经 agentd 或 launcher 的 `/proc/<pid>/root` 回到完整视图去写 |
| codex 自己的沙箱 | codex 的 bwrap 在 Landlock 下 mount 会被拒，所以 codex 改用它自带的 Landlock + seccomp 沙箱（`-c features.use_legacy_landlock=true`，0.162 里标 deprecated、仍可用）：两层 Landlock 叠加，命令照旧没网 | 嵌套 bwrap，要 AppArmor 在嵌套里照样放行 |
| 要不要改单元 | 不用 | 要关掉 `ProtectKernelTunables` 一类才能给新 `/proc`（Owner 改 infra） |
| macOS（本机） | 没有 Landlock：没有墙 | 没有 bwrap：没有墙 |

选 A：不加依赖（只用标准库 `syscall`，自己写 444/445/446 三个系统调用号）、不改单元、不靠命名空间和 AppArmor，`/proc` 的口子也一起堵上。B 的口子要改单元才补得上。

Landlock 管不住的（写进 §7）：`chmod`/`chown`/`utimes`/xattr（改属性不算写内容，能让 agentd 读不了自己的文件——拒绝服务，不是篡改）；连接同用户别处的 Unix socket（`connect` 不过 Landlock）；给同用户的进程发信号（ABI 6 才有 scope，06 的 6.8 没有）。

### 2.1 墙怎么套上

新子命令 `agentd confine --write <dir> [--write <dir>…] -- <argv>`（和 `launch`、`setup`、`verify` 一样是 agentd 自己调自己，不是公开接口）：锁住线程 → `PR_SET_NO_NEW_PRIVS` → 建规则集 → 每个 `--write` 目录给全部写权 → 设备文件（`/dev/null`、`/dev/zero`、`/dev/full`、`/dev/tty`、`/dev/ptmx`、`/dev/pts`）只给写和截断 → `landlock_restrict_self` → 同一线程 `exec` argv。

- 管的权利：写文件、截断、建 / 删文件与目录、建链接 / 设备 / FIFO / socket 文件、跨目录改名链接（REFER）。读和执行不管（读的例外照旧）。
- ABI < 3、任何一个目录打不开、任何一条规则加不上：**不 exec，退出非零**。尝试失败，不会无墙地跑。
- 套在最外层：`launcher → confine → [agentd setup →] 执行者`。launcher 自己留在墙外，照旧当进程组组长、结束后清组。
- **墙里再套一层更窄的墙**（复核 300 A3）：setup 的每条命令、deterministic 检查（`agentd verify`）的每条命令都跑在 `agentd confine` 里，只能写工作区、siblings 和 `a.Out/tmp`——写不了执行者的家（配置目录）和 `a.Out`（`verify.json`、`setup-spec.json` 等）。setup 还有自己的 `HOME`（`a.Out/tmp/home`），不是执行者的。setup 跑完、执行者启动前，`agentd setup` 再看一遍 cursor 不许有的文件（`--refuse`）。
- **agentd 在墙外对尝试目录做的文件操作，都不跟执行者留下的链接**（复核 301 A）：cursor / claude 的 `report.md` 由 agentd 写成新文件再改名替换（不写穿执行者留下的链接或硬链接）；`checkChanges` 往 `log.txt` 追加一行时也是写一个新文件（旧内容拷进去、加一行、改名替换，复核 302：原地追加会写穿硬链接）；这些写入和 `.git` 的打开都从 agentd 根逐级打开尝试目录（输出目录或工作区本身被早先的运行换成链接也不跟，复核 302 B）；检查点和改动检查的临时索引经工作区根打开的 `.git` 建和删（`.git` 被换成链出工作区的链接就报错）；清理和登录读取的输出目录逐级打开、每级核对 inode。
- **agentd 自己在工作区里跑的 git 也进墙**（`c4ea228`，等复核时自己查出来的）：git 读工作区的 `.git/config` 和 hooks，墙里的执行者或 setup 能写它们（fsmonitor、filter、hook 都是命令），而 agentd 的检查点 diff、改动检查、commit、push 会在墙外执行它们。有墙的主机上，从检出完成起（重启接管也一样），这些 git 都跑在 `agentd confine --write <工作区>` 里；接管时的 git 也不读用户全局和系统配置。

### 2.2 主机先自证，再算有墙

agentd 在 Linux 上启动时（领活之前）自己跑一遍探针：在 `<root>/confine-proof/` 下建一个墙内目录和一个墙外目录，`agentd confine --write <墙内> -- agentd confine-probe …` 逐项试：

| 试什么 | 要的结果 |
|---|---|
| 写墙内的新文件 | 成功 |
| 在墙外目录建文件、写墙外已有文件（追加）、`truncate` 墙外文件 | 都被拒 |
| 把墙内文件改名到墙外、把墙外文件硬链接进墙内、墙内放一个指向墙外的符号链接再经它写 | 都被拒 |
| 经 `/proc/<agentd 的 pid>/root/<墙外文件>` 写、读 `/proc/<agentd 的 pid>/environ` | 都被拒 |
| 在 `/tmp` 建文件（单元里所有尝试共用的 `PrivateTmp`） | 被拒 |
| 写 `/dev/null` | 成功 |

每项拒绝必须是 EACCES / EPERM / EXDEV（别的错误，比如路径不存在，不算拒绝）；检查跑完最后一行打印 agentd 给的随机串，父进程要看到它、看到墙内文件真的写了、墙外文件内容没变、墙外目录没多东西（复核 300 B6），才认为这台主机有墙；否则日志写明哪一项，所有执行者都不算 confined（照旧独占）。codex 另加一项：墙里跑 `codex sandbox`（带下面 codex 那组钉子），沙箱里的命令写工作区成功、写工作区外被拒；不过就 codex 不套墙、不加 legacy 开关、照旧独占（和今天一样，不会更差）。

## 3. 每个执行者的钉子

所有执行者共同的（不分 Linux / macOS，都由 agentd 在执行者的 builder 里设）：

| 钉子 | 值 |
|---|---|
| `HOME` | `a.Out/home`（agentd 新建，0700；只有执行者能写，setup 和被检查的代码写不了） |
| `TMPDIR` | `a.Out/tmp`（setup、执行者、codex 的命令共用） |
| `GOPATH` / `GOMODCACHE` / `GOCACHE` | `a.Out/tmp/go`、`a.Out/tmp/go/pkg/mod`、`a.Out/tmp/go-build`（不再继承 agentd 的；setup 下好的模块执行者能用，codex 沙箱里的命令也写得了） |
| 墙（只 Linux、自证过） | argv 以 `<agentd> confine --write a.Dir --write a.Out [--write <sibling>…] --` 开头；有 setup 时接着是 `<agentd> setup … --home a.Out/tmp/home --write a.Dir [--write <sibling>…] --write a.Out/tmp [--refuse …] --`；deterministic 是 `agentd verify … --write`（同一组窄目录） |

| 执行者 | 它自己的钉子 |
|---|---|
| codex | `CODEX_HOME=a.Out/home/.codex`，里面只有 agentd 复制进来的 `auth.json`（§4）；原有的 `-c` 钉子不变（`features.hooks=false`、`--ignore-rules`、`notify=[]`、`model_provider="openai"`、writable_roots 只有 `a.Out/tmp`、排除 `/tmp` 和 `$TMPDIR`）；有墙时加 `-c features.use_legacy_landlock=true` |
| claude | `CLAUDE_CONFIG_DIR=a.Out/home/.claude`、`DISABLE_AUTOUPDATER=1`；原有 `--setting-sources ""`、`--settings '{"disableAllHooks":true}'`、只读工具、空 MCP |
| cursor | `HOME` 是新的（`~/.cursor` 的配置和钩子都不在）；工作区里有 `.cursor/hooks.json` 或 `.cursor/mcp.json` 就**不开跑**，尝试失败并写明原因；key 照旧从环境来 |
| deterministic | 共同钉子；`agentd verify` 在墙里跑 |

本机实测（2026-10-19，codex 0.162，macOS）：全新 `CODEX_HOME` 下，工作区 `.codex/config.toml` 里的 MCP server 不加载（`codex mcp list` 为空）；把这个项目在家目录 config 里标成 trusted 才加载；`-c projects={}` 去不掉这个信任。所以 codex 的钉子是「全新的配置目录」本身，复核 283 里那条「受信任检出的 `.codex/config.toml`」由它关掉。

`confined` 的判定（`share.go`）：执行者在钉子表里、主机自证过墙、（codex）codex 自证过。领到之后、启动之前，agentd 再核一遍**拼好的** Spawn（`checkPins`，复核 300 A2 后改成逐字比对）：墙前缀和写目录集合一字不差；setup 段的 home、窄墙、refuse 一字不差；执行者自己的命令和 builder 做出来的一字不差（不能多一个开关、少一个、重复一个，codex 的 `-c` 每个只许一次且只许那几个，`-s workspace-write` 必须在）；环境变量只许 allowed 的和这个执行者自己的（多一个 `XDG_CONFIG_HOME` 也拒），每个只出现一次，钉住的值都是这次尝试自己的。钉子不齐就失败，不会无墙地和别人一起跑。

## 4. 凭据怎么放

- claude、cursor：照旧由 agentd 从 `AGENTD_CLAUDE_TOKEN_FILE`、`AGENTD_CURSOR_KEY_FILE` 读出来放进环境（`CLAUDE_CODE_OAUTH_TOKEN`、`CURSOR_API_KEY`），不落盘。
- codex：**一台主机上一次只跑一个 codex 尝试**（`codexTurn`，复核 300 B5）：每个尝试拿的都是主份的拷贝，并发时一个刷新会让别人手里的 refresh token 作废。别的执行者照样可以和它同时跑。
- codex：06 上是 `codex login --device-auth`（ChatGPT 登录，`auth.json` 里有会轮换的 refresh token）。agentd 把主份 `$CODEX_HOME/auth.json`（没设就是 `~/.codex/auth.json`）复制进这次尝试的 `CODEX_HOME`。**刷新后要回写**：codex 刷新时把新令牌写进尝试里的那份，旧的 refresh token 随之作废；不回写，主份过几天就登不上了。回写规则：执行者退出后（以及重启接管时），尝试里的 `auth.json` 是普通文件、不超过 64 KiB、只取已知字段（`auth_mode`、`OPENAI_API_KEY`、`tokens.{id_token,access_token,refresh_token,account_id}`、`last_refresh`；尝试文件里别的键不理会、不回写，主份原有的别的字段保留，复核 301 B），`auth_mode`、`OPENAI_API_KEY`、`account_id` 和主份相同，`last_refresh` 比主份新、不超前于现在 5 分钟以上——全部成立才原子地替换主份（同目录临时文件 + rename，0600，进程内一把锁）。尝试的 `auth.json` 经 agentd 根逐级校验过的输出目录读（不跟符号链接）。执行者能写回的只有这几个令牌字段；`account_id` 是文件自己说的，agentd 验不了令牌签名，所以一次运行**能把主份登录写坏**（Owner 要重新 `codex-login`），但写不进别的字段（复核 300 B5 改了措辞：不再说「不会是别人的账号」）。

## 5. 代价

- Go 和 npm 缓存每次尝试都是冷的（模块要从 proxy 下、编译全量）。共享可写缓存会让一次尝试往下一次的构建里下毒（Go 构建缓存按输入哈希取，能预先算出来），所以不共享。执行者退出后 agentd 删掉这次尝试的 `tmp`（Go 缓存在里面）、`home/.npm`、`home/.cache`，codex 的会话目录留着（用量读它的限额）。删之前经 agentd 根逐级打开输出目录，路上任何一段是符号链接就不删（复核 300 A1：早先没墙的运行可能把 `a1.out` 换成指向家目录的链接）。
- 写死 `/tmp` 的工具会失败（`TMPDIR` 之外），`/dev/shm` 不可写。codex 的沙箱早就排除了 `/tmp`，10-18 实测照常跑。

## 6. 测试与防线（Ratchet）

- `TestExecutorPins`：四个执行者的 argv 和环境带着 §3 的钉子（有墙、无墙两种）。
- `TestCheckPins`：Run 拼出来的 Spawn（有 setup、没 setup）通过；去掉、重复、改写任一钉子都被拒（codex 去掉 `-s workspace-write`、追加 `-c features.hooks=true`、同一 `-c` 两次；claude 去掉 `DISABLE_AUTOUPDATER`；多一个 `XDG_CONFIG_HOME`；setup 没有窄墙、用执行者的 home、窄墙里放 `a.Out`；cursor 不在 setup 后再查…）。
- `TestConfined`：没有自证过的墙，谁都不 confined；有墙时只有它认的执行者；被算作有墙、钉子不齐的尝试不启动。
- `TestAfterExecutorTakesNoLinkedOutput`（复核 300 A1，旧提交上失败）、`TestSetupRefusesWhatItLeft`（A3）、`TestCursorRefusesRepoHooks`、codex 登录回写的表驱动测试（换账号、旧的 `last_refresh`、符号链接、超大文件都不回写；尝试文件里多出来的键不回写，合法刷新的已知字段照样回写，主份原有的别的字段保留）。
- Linux 上的 `TestWallHolds`（§2.2 那张表 + 孙进程写墙外被拒）和 `TestSetupWallKeepsTheExecutorsHome`（A3：setup 写不了执行者的家和 `a.Out`）：没有 Landlock 的内核跳过并写明原因，macOS 不编译。**本机 Docker Desktop 的 Linux 内核（6.12，Landlock ABI 6）里实测全部通过**（用本机已有的 busybox 镜像跑 arm64 测试二进制，没有下载）。06 的探针（§8）是最终证明。

## 7. 留下的（不在本切）

1. 读：同用户的令牌文件、别的尝试的工作区都读得到（第 2 轮例外）。Landlock 也能管读（规则列出 `/` 下各目录、`/home` 只放行自己的），是下一步的候选，要先在 06 上量执行者读了哪些家目录里的东西。
2. Landlock ABI 3/4 管不到的（复核 300 B4，按前提写准）：对同用户文件 `chmod` / `utimes` / xattr、给同用户进程（agentd、别的尝试）发信号——在 06 上是真的拒绝服务（比如 SIGSTOP agentd、把 registry.json 改成 000），不能改内容；`connect` 同用户的 Unix socket、经 SCM_RIGHTS 收别人递来的可写描述符、设备 ioctl——**如果**主机上有同用户、肯代写的服务或早先逃出去的进程递描述符，就能真的改墙外内容。目前没找到 06 上有这样的端点，但没证明不存在；06 探针之后盘点一次同用户的 Unix socket。`/dev/pts` 可写，能往同用户别的终端里写字（执行者没有终端，影响小）。ABI 6（内核 6.12+）的 signal / 抽象 socket scope 能关掉其中两项，06 的 6.8 没有。
3. 同一任务的两次尝试同时在一台主机上：sibling 目录是任务级的，两者都能写；平台不会同时把一个任务租给同一主机两次（租约丢了 agentd 先杀旧组），不另加锁。
4. setup 留下的、`setsid` 甩掉进程组的进程（在窄墙里）还能在 `--refuse` 检查之后、cursor 读之前往工作区放 `.cursor/hooks.json`；钩子跑在 cursor 的墙里。事后 `checkChanges` 会让留了执行者配置的尝试失败，但钩子自己删掉文件就看不出来。要彻底关，得按尝试放进 cgroup（单元加 `Delegate=yes`，结束时 `cgroup.kill`）——改单元，交统筹线程定。
5. 进程组：执行者 `setsid` 甩掉组（v5 §6.2 已接受）；甩掉的进程仍在它自己的墙里。
6. codex 探针用的是 `codex sandbox -P :workspace`，生产跑的是 `codex exec -s workspace-write`（复核 300 B6）：探针证明 0.163 的 legacy Landlock 沙箱能在墙里跑命令、命令没网；探针**没有**证明 `codex exec` 在墙里的命令能启动、有没有网、可写目录是什么（复核 301 B：两条路径对 legacy 开关或配置的处理可能不同，最坏是 exec 仍用 bubblewrap、mount 被外层墙拒、命令全失败）。STG 走查时要跑一次带 setup、Go 模块缓存和真实命令的 codex 尝试。写墙外这件事不靠 codex 自己的沙箱（外层墙兜住）。

## 8. 06 上要 Owner 跑一次的探针

`agent-06-owner.sh` 加一个子命令（草案，infra 另提交）：

```bash
# confine-probe prod|stg: run agentd's write-wall probe on 06 as that agent
# user, under the same systemd confinement as its unit (TD-371). No model is
# called. Prints each check; exits non-zero on the first that does not hold.
step_confine_probe() {
  local u
  u=$(user_of "${1:-}")
  node_ssh "sudo bash ~/agent-host/confine-probe.sh $u"
}
```

`scripts/agent-host/confine-probe.sh <user>`（照 `codex-sandbox-probe.sh` 的样子，root 跑，`systemd-run` 带单元的全部限制、以 agent 用户身份）：

```bash
systemd-run --quiet --wait --pipe --collect --uid="$u" --gid="$u" \
  -p NoNewPrivileges=yes -p PrivateTmp=yes -p ProtectSystem=strict \
  -p ProtectHome=tmpfs -p BindPaths="/home/$u" -p ReadWritePaths="/home/$u" \
  -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectKernelLogs=yes \
  -p ProtectControlGroups=yes -p ProtectClock=yes -p ProtectHostname=yes \
  -p RestrictSUIDSGID=yes -p RestrictRealtime=yes -p LockPersonality=yes -p UMask=0077 \
  -p WorkingDirectory="/home/$u" \
  -E HOME="/home/$u" -E USER="$u" -E LOGNAME="$u" -E LANG=C.UTF-8 \
  -E PATH="/opt/bifrost/codex/bin:/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
  /usr/local/libexec/bifrost/agentd confine-probe --root "/home/$u/agent-work/agentd"
```

它打印内核的 Landlock ABI、§2.2 每一项和 codex 那一项的结果；都对才退出 0。探针用的是装在 06 上的 agentd，所以顺序是：分支合进平台主线、按 `agentd.sha256` 构建 → `agent-06-owner.sh update-agentd`（`confine-probe.sh` 随 `copy` 一起过去）→ `agent-06-owner.sh confine-probe stg`、`… prod`。新 agentd 起来时自己也会跑同一套自证；探针是给 Owner 看的那一份，并且多一个「每个执行者都在墙里」的总判定。另外 `check-agent-06.sh` 加两条：`/sys/kernel/security/lsm` 含 `landlock`；`/etc/cursor` 不存在（cursor 的托管钩子，和 claude 的 `/etc/claude-code` 同理）。agentd 起来后它的 journal 也会写一行自证结果（`agentd: write wall: …`）。

**06 上还要实测的三件**（探针跑完就知道）：codex 0.163 的 `use_legacy_landlock` 还在不在、在墙里能不能跑命令；cursor-agent 在新 `HOME` 下能否登录（只靠 `CURSOR_API_KEY`）；claude 在新 `CLAUDE_CONFIG_DIR` 下能否登录（只靠 `CLAUDE_CODE_OAUTH_TOKEN`）。后两件探针不调模型、证不了，要 STG 走查时各跑一次真尝试。

## 9. 复核记录

| 轮 | 结论 | 处理 |
|---|---|---|
| 300（第 1 轮，`e99a2e0`） | 3 A：① 清理跟着输出目录的符号链接删到别处（旧运行可构造）；② `checkPins` 漏查 `-s workspace-write`、`DISABLE_AUTOUPDATER`，追加的相反开关也放过；③ setup 在检查之后跑，能在执行者的配置目录里重新放配置、在工作区放 `.cursor/hooks.json`。3 B：④ ABI 3/4 管不到的不全是拒绝服务；⑤ 登录回写的账号是自报的、并发刷新的窗口比写的大；⑥ 探针证明的是 `codex sandbox` 不是 `codex exec`，任何错误都算拒绝 | ① 经 agentd 根逐级、不跟链接地打开输出目录（`openOutput`），登录也经它读；② 逐字比对；③ 布局改成执行者的家只有执行者能写、setup 和检查命令跑在更窄的墙里、setup 有自己的 home、setup 后再查 cursor 的禁止文件；④ §7 第 2 条按前提写准；⑤ 一次一个 codex 尝试、改措辞；⑥ errno、随机串、父进程核文件，§7 第 6 条 |
| 自查（`c4ea228`） | agentd 在工作区里跑的 git 会执行工作区 `.git/config` 里的命令（fsmonitor、filter、hook），在墙外 | 有墙时这些 git 全部跑在墙里（`Workspace.wall`）；`TestWorkspaceGitGoesThroughItsWall` |
| 301（第 2 轮） | Codex 第一次运行被 OpenAI 的安全过滤拦下（简报措辞像找逃逸），没有报告；改成防御性代码复核的措辞重跑 | — |
| 301（第 2 轮重跑，`c4ea228`） | 上轮 3 个 A 确认已修。2 A：① agentd 在墙外写 `report.md` 会跟随执行者留下的链接，覆盖别的尝试的文件；② 临时索引的建删在墙外跟随 `.git` 链接。3 B：③ bench 预热的模块缓存执行者没用上；④ §4「多一个键都不收」与代码不符；⑤ §7 把 codex 两条路径的差别只说成网络 | ① `writeOwn` 新文件改名替换、`appendOwn` 经根追加；② `.git` 经工作区根打开、索引在句柄里建删；`openOutput` 逐级打开并核对 inode；③ bench 的执行者用预热的模块缓存；④⑤ 改措辞。回归测试 `TestReportAndLogNotWrittenThroughLinks`、`TestIndexFilesNotThroughALinkedGitDir` 在旧提交上失败 |
| 302（确认轮，`d0a1042`） | 301 的两个 A 中索引那个确认已修、报告那个只修了一半。1 A：`appendOwn` 原地追加，日志是硬链接时写穿到另一个文件。1 B：写入和 `.git` 的起点目录按路径打开，输出目录或工作区本身是早先运行留下的链接时会被跟随。1 C：§6 的措辞 | A：追加改成写新文件再改名；B：起点都从 agentd 根逐级打开（`openWithin`），工作区记着根；C：改措辞。回归测试 `TestReportAndLogNotWrittenThroughLinks`（硬链接日志，旧提交上失败）、`TestIndexFilesNotBehindALinkedCheckout` |
| 303（窄确认，`d8d3995`） | 302 的 A、B、C 都确认已修；0 A。1 B：执行者把 `log.txt`（或 `report.md`）留成没有写端的 FIFO 时，agentd 读日志尾部会一直等，交付卡住（旧问题，不是写穿） | `readTail`、`readAtMost` 只读普通文件、不跟链接、不等待（`b1be372`）；`TestResultsDoNotWaitOnAFIFO` 在旧提交上失败。**按停线规矩收线** |

收线时的状态（2026-10-19 03:2x）：分支 `w31/agentd-confine` 头 `b1be372`，基于平台主线 `d788296`；`go test ./...`（PG、Redis、`AGENTRT_TEST_REQUIRED=1`）全过；agentd 两个包的 golangci-lint 与主线相同（全仓 108 条都是主线原有的）；code-health 通过（最大的 `run.go` 741 行）；Landlock 相关测试在本机 Docker Desktop 的 Linux 内核（6.12，ABI 6）里全过。复核 300–303 的报告在 `~/agent-work/codex-review-30{0,1,2,3}/REPORT.md`。
