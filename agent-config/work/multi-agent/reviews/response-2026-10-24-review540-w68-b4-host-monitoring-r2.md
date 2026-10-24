# 回应复核 540 — W-68 B4 ① 第三版

回应人：写这份交付的子代理，2026-10-24 01:45–02:30 CDT。
新提交：`2454c62822c4b881a2fd29a775e0c48380e0ec72`，分支 `w31/r4-w68-b4`，接在 `a6cb801` 之后（基于 origin/main `639edc9`）。尾注照旧：`Work: W-68`，Change-Id 是新的。未推送，未 apply，没在任何主机上装东西。

## A1 · P1：第 4a 步通过可能已被植入的账户检查它自己 —— 改了

**新流程**：`host-exporters.sh nas-home`。

- **登录哪个账户**：Owner 的管理账户 **Wzhao**。它在 `admin` 组，家目录 700。10-24 用 k8s_admin 只读读到的账户表：Wzhao 700、k8s_admin 777、Family 是 nologin；`PermitRootLogin no`。
- **怎么提权**：sudo 问一次 Wzhao 的口令，root 再从同一 ssh 会话传进来的 root 临时目录里运行 `nas/check-k8s-admin-home.sh`。
- **为什么不会执行 k8s_admin 的文件**：sudo 的 env_reset 会清掉 SSH_CLIENT，HOME 是 /root；脚本只用 stat 读取，不 source 也不执行那个家目录里的任何东西。
- **列出什么（只读）**：
  - 家目录本身，以及里面每一项的属主、权限、修改时间；
  - 10 种 shell / ssh 启动入口：`.bashrc .bash_profile .bash_login .profile .bash_logout .inputrc .pam_environment .ssh/rc .ssh/environment .ssh/authorized_keys2`；
  - `.ssh` 和 `authorized_keys` 的属主、权限、时间；
  - 每把授权钥匙的指纹，和 Mac 上 `~/.ssh/id_ed25519.pub` 的指纹比对；
  - 钥匙行前面有没有带 `command=` 之类的选项。
- **判可疑、什么都不改的情形**：
  - 家目录或 `.ssh` 是链接，或不是目录；
  - 有哪一项不归 k8s_admin；
  - 出现任何一个启动入口；
  - `.ssh` 或 `authorized_keys` 别人能写；
  - 有不认识的钥匙；
  - 钥匙行带了选项。
  这时退出码 3，不 chmod。
- **全部干净时**：`chmod 700`，然后立刻再查一遍。万一在第一次检查和 chmod 之间有人放了文件，这一遍会抓到。另有 `nas-home check` 只读、不改。
- **操作单 4a**：命令能原样复制运行；列出 10-24 读到的预期输出，包括唯一授权钥匙的指纹 `SHA256:met8nr2+2S8jVKAvzj5nYX0UEhO4Tt3YRYn191HuFr8`；看到 `SUSPICIOUS:` 就停下报告，不做 4b，也不以 k8s_admin 登录。
- **顺带改的**：4b 装报数程序和第 7 步 NAS 演练要 sudo 的命令，也都改从 Wzhao 登录，不再在 k8s_admin 的会话里输口令。
- **切法第 8 节写明了三点**：
  - 本次调研中 Agent 以 k8s_admin 只读登录过 NAS 十来次（没输过口令）。如果 4a 发现可疑文件，这些登录可能已经执行过它。
  - Mac 上这把 `id_ed25519` 若也授权给了 Wzhao（Owner 的 ssh config 里 `Host nas` 就是这么配的），Agent 一样能改 Wzhao 的启动文件。这属于已经披露的 Agent 残余风险。彻底分开需要 Wzhao 只认一把 Agent 用不了的带口令钥匙，超出本切片。
  - 「id_ed25519 能否登 Wzhao」没核实。Agent 没有、也不该用 Owner 的账户去试；登不上就停在第 4 步。
- **单测**（`test_host_exporters.py` 的 `K8sAdminHome`，8 项，HOME 和 SSH_CLIENT 都按 ssh 登录那个账户时的样子设置）：
  - 植入的 `.bashrc` 让 fix 停在退出码 3、权限仍是 777，而且它从未被执行（标记文件不存在）；
  - 其余 9 种启动入口逐个都会让 fix 停下；
  - 不认识的钥匙、带 `command=` 的预期钥匙、组可写的 `.ssh`、被换成链接的 `.ssh`，都让 fix 停下且不改权限；
  - 干净的家目录：check 只读、不改；fix 收成 700；
  - 指纹参数不对是用法错误，权限不变。
  - 另外两条：`HostExporters` 里断言 `nas-home` / `nas` 从 `Wzhao@` 登录，调用里没有 `k8s_admin@`；把 `nas-home` 发出的远端命令在本机执行，确实能解包并跑到检查脚本。

## A1 · P2：已有目录先被 chown/chmod 再检查 —— 改了

- 新增 `nas/prepare-dir.sh <uid> <trusted root> <dir>`：
  - 先用 `secure-dir.sh` 检查 trusted root；
  - 再从 trusted root 往下逐级处理：**已存在**的按原样检查，不安全就退出 1，不 chown、不 chmod，下面的也不建；**不存在**的由运行者（NAS 上是 root）`mkdir -m 0755`，建完立刻检查。
- `install-nas.sh` 里原来那段 `chown root:root` / `chmod 0755` 循环删了，改成调用 `prepare-dir.sh 0 /volume1 /volume1/@bifrost/host-exporters`。已有的 `compose.yaml` 必须是普通文件、不是链接，并通过 `secure-dir` 才会被替换。新文件写完再查一次、`cmp` 一次，然后 compose 才读它。
- **只有它能拦住的单测**（`PrepareDir`，6 项，真的执行脚本，不是查字符串）：
  - **预先放一个 777 的 `@bifrost` → 被拒，权限仍是 777，下一级没建**；
  - 预先放一个链接 → 被拒，链接原样，指向的目录里没有新东西；
  - 挡路的是个文件 → 被拒；
  - trusted root 不安全 → 什么都不建；
  - 都不存在 → 两级都建成 0755；
  - 都已存在且安全 → 原样通过，权限不被改。
  - 字符串层面另有一条：`install-nas.sh` 的代码里不再出现 `chown` / `chmod`，并且顺序是 prepare-dir → 检查已有的 compose → 写 → 再检查 → compose。

## 复核里其余要改的

- **A2「全部目标缺失」缺测试证据**：新增一组规则单测。SMART 和 Gitea 的目标全都没有时，16 分钟时各触发一条 `SmartExporterDown{host=agent-06}`、`{host=nas}`，14 分钟时不触发；11 分钟时各触发一条 `GiteaProbeDown{via=nodeport}`、`{via=service}`，9 分钟时不触发。逐条断言了身份和注解。
- **G3「逐台演练的三分钟判定」**：操作单第 7 步改成：每次演练只有第一台按 3 分钟判，同一次里后面的每一台按 8 分钟判（3 分钟加一个 5 分钟分组间隔），并写明原因：RESOLVED 推出来，不能证明旧组已经销毁。Owner 选 G3-A 并改完以后，才每台都按 3 分钟判；想每台都拿到 3 分钟的证据，就分几次演、每次只演一台。原来「等 RESOLVED 后再过 1 分钟就按 3 分钟判」的说法删了。切法 G3 和验收表跟着改，回报格式里加了「第一台是哪台」。
- **「第 3 轮」计数笔误**：改成「第 4 轮（距它 300–360 秒）」。第一次失败那轮算第 1 轮，轮距 100–120 秒。G1-B 写的「第 2 轮就发」核对过，是对的。
- **C 项**：复核 540 判 C1–C3 已完成，没有新的 C 项。

## 检查（全部在新提交的树上重跑）

| 检查 | 结果 |
|---|---|
| `python3 scripts/check_alert_rules.py`（本机已有的镜像 `quay.io/prometheus/prometheus:v3.13.2-distroless` 里的 promtool） | `ok: 4 rule file(s), 4 promtool test file(s) pass`；`host-rules.test.yaml` 11 组 |
| 阳性对照：旧规则（`bb12194`）跑新单测 | 7 处失败：SmartExporterDown@16m 两组（单缺、全缺）、GiteaProbeDown@11m 两组（单缺、全缺）、TargetsMissing@11m、NasSmartBlind 零盘@2h1m、NasSmartBlind 读错误@2h1m |
| 阳性对照：在新规则里单独拿掉一项 | 拿掉 nas 的 `absent` → 单缺、全缺两组都失败；拿掉 nodeport 的 `absent` → 两组都失败；拿掉读错误分支 → 读错误那组失败；同时拿掉「少于 3 块盘」和「健康指标缺失」 → 零盘那组失败；拿掉 `unless` → 「整机不在」那组在 3h20m 失败。都恢复后：promtool `SUCCESS` |
| 阳性对照：脚本 | `prepare-dir.sh` 改成检查前先 chmod → 2 项 PrepareDir 失败；home 检查漏掉 `.bashrc` → 1 项失败；home 检查有可疑也照样 chmod → 5 项失败；home 检查不管钥匙选项 → 1 项失败；`install-nas.sh` 换回 `a6cb801` 的版本 → 顺序测试失败。全部恢复后 33 项 OK。上一轮的 `secure-dir` 对照这次没有重跑（文件未改） |
| `python3 -m unittest scripts/host-exporters/test_host_exporters.py` | 33 项 OK |
| `check_alert_routing.py`、`check_http_metrics_coverage.py`、`check_maintainers.py`、`check_monitoring_persistence.py` | 都是 ok |
| `kubectl kustomize k8s/monitoring` | 渲染成功，4439 行 |
| 客户端严格校验（只读身份） | 8 个对象都过 |
| `apply-manifest-check.sh`，用 PROD 的 actuation-policy | 4 个文件都判 C 级，都过 |
| 7 个脚本 `bash -n`；`docker compose config --quiet`；面板 JSON | 都过 |

没做的：在真的 NAS 上以 root 跑 `prepare-dir`、`check-k8s-admin-home`、`install-nas`（GNU stat / install 的实际行为、UGOS 的 ACL）；Wzhao 登录和 sudo；服务端 dry-run；Alertmanager 分组时序；现场抓取和手机演练。

## Owner 步骤和用时、统筹线程可代做的

- **Owner 步骤**：数目不变。第 4 步改成两条命令，都从 Wzhao 登录，各问一次 Wzhao 的口令：`nas-home`（以 root 检查，干净才收紧）和 `nas`。第 7 步 NAS 演练的命令也改成从 Wzhao 登录。**用时**：约 35 分钟变成约 37 分钟。
- **统筹线程可代做的**：不变。上一版说「4a 统筹线程技术上也能做」，这次收回：4a 现在要以 Owner 的 Wzhao 账户和口令做，统筹线程做不了，也不该做。
