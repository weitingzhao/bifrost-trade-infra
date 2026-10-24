# Owner 操作单：W-68 B4 ① 集群外机器的主机监控

起草 2026-10-24（统筹线程派出的子代理）；按 Codex 复核 537 改第 2 版。切法和理由：`CUT-w68-b4-host-monitoring-2026-10-24.md`。

**做完会怎样**：06、NAS、两台 mini 各有报数程序；Grafana 多一个面板「Bifrost Hosts」（`https://ops.bifrost.lan/grafana/d/bifrost-hosts`）。手机会收到这些推送：
- 06、mini-52 失联，或任何一台的报数程序停了：约 2 分 40 秒后 `CRITICAL Host <名字> (…) is not answering`。前提是同一段时间里没有另一台正在推（否则后面那台最多再晚 5 分钟，见「要你定的」第 5 条）。
- NAS 的盘：SMART 判定失败、出读不出的扇区、阵列少盘、盘消失，几分钟到半小时内推；三块盘的 SMART 看不全持续 2 小时也推。
- Gitea 取不到 `/api/healthz`：规则等 2 分钟，加上抓取、评估和推送，约 3 分半。

**还做不到的（不算验收通过）**：.50 整机坏要约 5.5–8 分钟（中转就在它上面，要等 B3）；NAS 整机坏时监控自己的数据也在 NAS 上，多久能推到还不知道（等装 M.2 SSD 那次关机实测）。见文末「要你定的」第 3、4 条。

不停任何服务，不改 Alertmanager，不改 UniFi。

**什么时候做**：统筹线程在线程里说「B4 ① 已合入 main」之后。不挑时间、不用发布窗口（`k8s/monitoring` 不归 Argo，不是一次发布）。

**在哪做**：都在你 Mac Pro 的终端里。第 3、4 步要输口令：**先点开终端面板，在那里粘贴运行，提示一出来马上输**（06 的 sshd 只等 2 分钟；超时的样子是约 2 分半后 `Connection closed by 192.168.10.79 port 22`，重跑同一条即可）。

**每一步怎么跑**：同一个脚本 `scripts/host-exporters/host-exporters.sh` 的一个子命令。命令先把它从 origin/main 取到 `/tmp/b4-host-exporters.sh` 再运行；脚本要用的文件也都从 origin/main 取（不读工作树），出错即停、退出码非 0，不打印任何凭证。每一步都可以重跑。

**怎么回**：每步末尾写了回什么，只回那句话，不用贴输出。

**合计**：你要做的是第 3、4、5 步和第 7 步里 06、NAS 两次演练，约 35 分钟（演练每次要等恢复推送，约 8 分钟）。第 2 步和 mini 的两次演练统筹线程可以代做（要你定，见文末第 1 条）；你自己做再加约 20 分钟。

---

## 第 1 步　确认已合入（只读，几秒）

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && echo "merged at $(git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra rev-parse --short origin/main)"
```

**做完会看到**：`merged at` 后面一个 7 位提交号。看到 `fatal: path 'scripts/host-exporters/host-exporters.sh' does not exist in 'origin/main'` 就是还没合入，停在这里。

不用回。

## 第 2 步　两台 Mac mini（各约 2 分钟，不用 sudo）

只往 `vision` 的家目录写：`~/bifrost-agent/node-exporter/1.12.1/node_exporter`、`~/Library/LaunchAgents/com.bifrost.node-exporter.plist`、日志 `~/bifrost-agent/logs/node-exporter.log`。用的是 Mac Pro 上那把 `~/.ssh/id_ed25519`（Agent 平时只读登 mini 用的同一把），不问口令。

**建议由统筹线程代做**（见文末第 1 条）。你自己做就跑这两条：

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh mini 50
```

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh mini 52
```

**做完会看到**（每台）：`==> node_exporter 1.12.1 (darwin-arm64)`、`installed …/node_exporter`、`node_exporter, version 1.12.1 …`、一行 `node_exporter_build_info{…version="1.12.1"…} 1`，最后 `install-mac: OK on 192.168.10.50:9100`（.52 同样）。

自己做了就回：「mini 装好了」。

## 第 3 步　06（约 5 分钟，节点钥匙口令问 1 次）

在 06 上：从 Ubuntu 装 `smartmontools`；从 github.com 下载 node_exporter 1.12.1 和 smartctl_exporter 0.14.0（按 `versions.env` 里的 sha256 校验，不对就停）；装两个 systemd 服务并启动，只在 `192.168.10.79` 上听。不碰两个 agentd，不改出站规则。

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh agent-06
```

**做完会看到**：先问 `Enter passphrase for key '/Users/vision-mac-trader/.bifrost-owner/ssh/node':`；然后 `==> smartmontools` 和它的版本，`wrote /usr/local/bin/node_exporter` 等几行，`no nftables input chain: 9100 and 9633 are reachable on 192.168.10.79`，一行 `node_exporter_build_info{…} 1`，一行 `smartctl_device_smart_status{device="sda"} 1`，最后 `install-linux: OK on 192.168.10.79 (node_exporter :9100, smartctl_exporter :9633)`。SMART 第一次读可能要等一分钟。

停在 `smartctl_exporter answers no SMART status` 就回「06 SMART 没数」，别的都已装好，统筹线程看日志。

做完回：「06 装好了」。

## 第 4 步　NAS（约 9 分钟）

### 4a　先收紧 k8s_admin 的家目录（TD-433，几秒，不用 sudo）

现在 `/home/k8s_admin` 是 777：NAS 上任何账户都能在里面放文件，包括 shell 启动文件，而 4b 要在这个账户的会话里输 sudo 口令。家目录归 k8s_admin 自己，改它不用 sudo：

```bash
ssh -o IdentitiesOnly=yes -i /Users/vision-mac-trader/.ssh/id_ed25519 k8s_admin@192.168.10.20 'chmod 700 ~ && stat -c "%A %U %n" ~ && ls -A ~'
```

**做完会看到**：`drwx------ k8s_admin /home/k8s_admin`，下面列出家目录里的东西（10-24 读的是 `.bash_history .DS_Store Music Photos .ssh .sudo_as_admin_successful`）。**列表里多出 `.bashrc`、`.profile`、`.bash_profile`、`.bash_login` 里任何一个，先别做 4b**，回「NAS 家目录里有启动文件」，统筹线程先看内容。

这只挡住其他 NAS 账户；Agent 的钥匙本来就能以 k8s_admin 登录（切法第 8 节）。UGOS 升级可能把权限改回去，第 6 步统筹线程会复查。万一改完 UGOS 里 k8s_admin 的「个人文件夹」打不开，告诉统筹线程，不要自己改回 777。

### 4b　装报数程序（k8s_admin 的 NAS 口令问 1 次）

在 NAS 上：建只有 root 能写的 `/volume1/@bifrost/host-exporters/`（从 `/` 往下每一级都查一遍，有任何一级别人能写或是链接就停），放 `compose.yaml`，从 quay.io 拉两个按 digest 钉死的镜像，起 `node-exporter` 和 `smartctl-exporter` 两个容器。不碰 `/volume1/docker/` 和 minio-backup。

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh nas
```

**做完会看到**：`[sudo] password for k8s_admin:`，输入 NAS 上 k8s_admin 的口令；`==> /volume1/@bifrost/host-exporters (root's alone, from / down)`；`docker compose pull` 拉两个镜像；`docker compose ps` 里 `node-exporter`、`smartctl-exporter` 两行 running；`node_md_disks{device="md1",state="active"} 3` 等几行；`smartctl_device_smart_status{device="sda"} 1`、`sdb`、`sdc` 三行；最后 `install-nas: OK (node_exporter :9100, smartctl_exporter :9633, 3 disks)`。三块 12 TB 的盘第一次读 SMART 可能要等两分钟。

停在 `refusing: … is not root's alone` 就回「NAS 路径不安全」并把那一行的路径告诉统筹线程。拉镜像失败（NAS 连不上 quay.io）就回「NAS 拉不到镜像」：备选是在 Mac 上导出镜像包再 `docker load`，和 MinIO 当时一样。停在 `reports health for N disks, not 3` 就回「NAS SMART 只有 N 块」。

做完回：「NAS 装好了」。

## 第 5 步　集群（约 3 分钟）

把 4 个文件放进 `monitoring`：两份外部主机的 ScrapeConfig、Gitea 探针（一个小 Deployment + Service + ConfigMap + ScrapeConfig）、告警规则、面板。**第 2–4 步都做完再做这一步**：脚本先查 6 个报数端点都在，缺一个就停（否则规则会为还没装的主机报警，NAS 的 SMART 2 小时后还会推手机）。然后对 4 个文件全部做服务端 dry-run，任何一个不过就一个都不应用。用你的管理员 kubeconfig（`/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml`，脚本自己指定，不看终端里的 `KUBECONFIG`）。

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh cluster
```

**做完会看到**：先是 6 行 `ok       <主机> <地址> (<指标>)`；停在 `MISSING` 就回「集群步骤缺端点」并带上那一行。然后 `==> server dry-run (nothing changes yet)` 下面 8 行 `… created (server dry run)`：`scrapeconfig…/bifrost-hosts-node`、`scrapeconfig…/bifrost-hosts-smartctl`、`configmap/bifrost-blackbox-exporter`、`deployment.apps/bifrost-blackbox-exporter`、`service/bifrost-blackbox-exporter`、`scrapeconfig…/bifrost-gitea-probe`、`prometheusrule…/bifrost-host-rules`、`configmap/bifrost-dashboard-hosts`；`==> apply` 下面同样 8 行 `created`；`deployment "bifrost-blackbox-exporter" successfully rolled out`；最后 `host-exporters: cluster OK`。

另一种做法（不用你跑命令）：统筹线程先跑 `check` 确认 6 个端点都在，再对这 4 个文件各做一次 `plan_manifest` + `apply_manifest`，你在 Console 的 Needs you 里批 4 张 C 级单。两种只选一种，以后改这几个文件也用同一种（见切法第 7 节）。建议用上面这条命令：一次 dry-run 看全 4 个文件，一条命令做完。

做完回：「集群放好了」。

## 第 6 步　核对（统筹线程做，约 15 分钟；你不用看）

统筹线程跑 `bash /tmp/b4-host-exporters.sh check`（只读：6 个端点各打一次，全是 `ok` 才算过），再在 Prometheus 里核对切法第 7 节第 6 步列的那几项（四台、两个 SMART、两条 Gitea 路全是 `up=1`；NAS 三块盘的 SMART 和 `md1`；三块盘一直有读写；06 根分区不是只读；mini 登录后指标齐全；blackbox 不在 ubt-k3s-01；NAS 家目录还是 700），打开面板「Bifrost Hosts」看每块都有数。核对完在线程里报。

## 第 7 步　演练：每台停一次报数，看手机（每台约 8 分钟）

**一次只演一台**（统筹线程代演 mini 时也一样，和你的 06、NAS 错开，先在线程里说一声）。每台：停掉 node_exporter，记下时刻 → 等 `CRITICAL Host <名字> (<地址>:9100) is not answering` → 恢复 → 等 `RESOLVED Host … is not answering`。

**等多久算正常**
- 停之后：**3 分钟内**收到 CRITICAL（单测算的是约 2 分 40 秒）。超过 3 分钟没到，先看下一条是不是没等够。
- 上一台的 RESOLVED 还没到、或刚到不足 1 分钟就停下一台：这一台的 CRITICAL 会和上一台排进同一组，**最多再晚 5 分钟**（约 8 分钟内到）。这是切法 G3 说的分组延迟，不算演练失败，但这一台的时间不能算进「3 分钟」。所以：等上一台的 RESOLVED 到了、再过 1 分钟，才停下一台。
- 恢复之后：RESOLVED 在 CRITICAL 之后约 **5 分钟**到（Alertmanager 每 5 分钟才发一次同组的变化）；恢复得晚，就落在下一个 5 分钟刻度。恢复后 10 分钟还没到才算不正常。
- 同一台 30 分钟内别演第二次：中转对同一告警同一状态 30 分钟内只推一次，第二次不会响。

**这次演练证明不了的**：停 .50 的 node_exporter 时中转还活着，所以验证不了「.50 整机坏」（切法 G1）；停 NAS 的 node_exporter 时 NFS 还在，验证不了「NAS 整机坏」（G2，等装 SSD 那次）。

mini 两台统筹线程可以代做（文末第 1 条），用的是 `ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 vision@192.168.10.52 'launchctl bootout gui/$(id -u)/com.bifrost.node-exporter'`，恢复是同一处换成 `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bifrost.node-exporter.plist`（.50 同样）。

**06**（每条问一次节点钥匙口令）。停：

```bash
ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey -i /Users/vision-mac-trader/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -n systemctl stop node-exporter.service && date'
```

收到 CRITICAL 后恢复：

```bash
ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey -i /Users/vision-mac-trader/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -n systemctl start node-exporter.service && systemctl is-active node-exporter.service'
```

**NAS**（每条问一次 k8s_admin 的口令；等 06 的 RESOLVED 到了再过 1 分钟再停）。停：

```bash
ssh -t -o IdentitiesOnly=yes -i /Users/vision-mac-trader/.ssh/id_ed25519 k8s_admin@192.168.10.20 'sudo docker stop node-exporter && date'
```

收到 CRITICAL 后恢复：

```bash
ssh -t -o IdentitiesOnly=yes -i /Users/vision-mac-trader/.ssh/id_ed25519 k8s_admin@192.168.10.20 'sudo docker start node-exporter'
```

**做完会看到**：停的那条打印当时的时间；手机上 ntfy 先后两条推送；恢复的那条打印 `active` 或 `node-exporter`。

做完回：「演练完了：06 停后 x 分钟到、NAS 停后 x 分钟到」（mini 是你自己演的也写上）；哪台按上面的「等多久算正常」还是没到，就回「<名字> 没收到」。

---

## 要你定的（在线程里回一句）

1. **mini 两台由谁装、谁演练。** 建议：统筹线程。理由：不用 sudo，只写 `vision` 家目录，用的是 Agent 已有的只读 SSH 钥匙；你少两步、约 20 分钟。回「mini 由统筹线程装和演练」，或「mini 我自己来」。
2. **第 5 步用哪种。** 建议：你跑 `cluster` 那一条。回「集群用命令」，或「集群走审批单」。
3. **.50 自己整机坏（切法 G1）。** 现在靠 .52 的看门狗，按脚本推算约 5.5–8 分钟，达不到 3 分钟；改等待时间（B）推算约 2 分–3 分 40 秒，也不保证。建议 A：放进 B3「告警转发成对」一起解决，在那之前这一条不算验收通过。回「G1 按 A」或「G1 按 B」。
4. **NAS 整机坏（切法 G2）。** Prometheus 和 Alertmanager 的数据都在 NAS 上，NAS 坏时它们可能先卡住，多久能推到不知道。建议 A：NAS 装 M.2 SSD 那次本来要关机，就在那次验，在那之前这一条标「待验收」；卡住了再给 .52 的看门狗加一项直接探 NAS。回「G2 按 A」。
5. **几台在同一段时间坏，后面几台最多再晚 5 分钟（切法 G3）。** 两个选择，**不回不算接受**：A 改 Alertmanager 路由，让每台单独成组（helm upgrade，你来跑，切法里有草稿）；B（建议）明确接受「第一台 3 分钟内到，同一段时间里后面几台最多再晚 5 分钟」。回「G3 按 A」或「G3 接受 B」。

## 撤销（只在要退回时用）

- mini：`launchctl bootout gui/$(id -u)/com.bifrost.node-exporter`，再删 `~/Library/LaunchAgents/com.bifrost.node-exporter.plist` 和 `~/bifrost-agent/node-exporter/`。
- 06：`sudo systemctl disable --now node-exporter.service smartctl-exporter.service`，再删两个服务文件 `/etc/systemd/system/{node,smartctl}-exporter.service` 和 `/usr/local/bin/{node,smartctl}_exporter`；`smartmontools` 留着无害。
- NAS：`sudo docker compose -f /volume1/@bifrost/host-exporters/compose.yaml down`（新路径；旧路径 `/volume1/docker/host-exporters` 不用了）。家目录的 700 不用撤。
- 集群：管理员 kubeconfig 下对同样 4 个文件 `kubectl delete -f`。先删 `bifrost-host-rules.yaml`，否则 `BifrostHostTargetsMissing`、`BifrostHostSmartExporterDown` 和 `BifrostGiteaProbeDown` 会各报 warning。
