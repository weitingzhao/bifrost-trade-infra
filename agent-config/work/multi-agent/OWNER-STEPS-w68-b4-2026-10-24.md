# Owner 操作单：W-68 B4 ① 集群外机器的主机监控

起草 2026-10-24（统筹线程派出的子代理）。切法和理由：`CUT-w68-b4-host-monitoring-2026-10-24.md`。

**做完会怎样**：06、NAS、两台 mini 各有报数程序；任何一台失联约 2 分 40 秒后手机收到 `CRITICAL Host <名字> (…) is not answering`；NAS 的盘 SMART 变坏、出坏扇区、阵列少盘、盘消失都推手机；Gitea 两分钟取不到 `/api/healthz` 推手机；Grafana 多一个面板「Bifrost Hosts」（`https://ops.bifrost.lan/grafana/d/bifrost-hosts`）。不停任何服务，不改 Alertmanager，不改 UniFi。

**什么时候做**：统筹线程在线程里说「B4 ① 已合入 main」之后。不挑时间、不用发布窗口（`k8s/monitoring` 不归 Argo，不是一次发布）。

**在哪做**：都在你 Mac Pro 的终端里。第 3、4 步要输口令：**先点开终端面板，在那里粘贴运行，提示一出来马上输**（06 的 sshd 只等 2 分钟；超时的样子是约 2 分半后 `Connection closed by 192.168.10.79 port 22`，重跑同一条即可）。

**每一步怎么跑**：同一个脚本 `scripts/host-exporters/host-exporters.sh` 的一个子命令。命令先把它从 origin/main 取到 `/tmp/b4-host-exporters.sh` 再运行；脚本要用的文件也都从 origin/main 取（不读工作树），出错即停、退出码非 0，不打印任何凭证。每一步都可以重跑。

**怎么回**：每步末尾写了回什么，只回那句话，不用贴输出。

**合计**：你要做的是第 3、4、5 步和第 7 步里 06、NAS 两次演练，约 25 分钟。第 2 步和 mini 的两次演练统筹线程可以代做（要你定，见文末「要你定的」第 1 条）；你自己做再加约 10 分钟。

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

停在 `smartctl_exporter answers no SMART status` 就回「06 SMART 没数」，别的都已装好，我看日志。

做完回：「06 装好了」。

## 第 4 步　NAS（约 8 分钟，k8s_admin 的 NAS 口令问 1 次）

在 NAS 上：建 root 自己的 `/volume1/docker/host-exporters/`，放 `compose.yaml`，从 quay.io 拉两个按 digest 钉死的镜像，起 `node-exporter` 和 `smartctl-exporter` 两个容器。不碰 minio-backup。

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh nas
```

**做完会看到**：`[sudo] password for k8s_admin:`，输入 NAS 上 k8s_admin 的口令；`docker compose pull` 拉两个镜像；`docker compose ps` 里 `node-exporter`、`smartctl-exporter` 两行 running；`node_md_disks{device="md1",state="active"} 3` 等几行；`smartctl_device_smart_status{device="sda"} 1`、`sdb`、`sdc` 三行；最后 `install-nas: OK (node_exporter :9100, smartctl_exporter :9633)`。三块 12 TB 的盘第一次读 SMART 可能要等两分钟。

拉镜像失败（NAS 连不上 quay.io）就回「NAS 拉不到镜像」：备选是在 Mac 上导出镜像包再 `docker load`，和 MinIO 当时一样。

做完回：「NAS 装好了」。

## 第 5 步　集群（约 3 分钟）

把 4 个文件放进 `monitoring`：两份外部主机的 ScrapeConfig、Gitea 探针（一个小 Deployment + Service + ConfigMap + ScrapeConfig）、告警规则、面板。先对 4 个文件全部做服务端 dry-run，任何一个不过就一个都不应用。用你的管理员 kubeconfig（`/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml`，脚本自己指定，不看终端里的 `KUBECONFIG`）。

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh cluster
```

**做完会看到**：`==> server dry-run (nothing changes yet)` 下面 8 行 `… created (server dry run)`：`scrapeconfig…/bifrost-hosts-node`、`scrapeconfig…/bifrost-hosts-smartctl`、`configmap/bifrost-blackbox-exporter`、`deployment.apps/bifrost-blackbox-exporter`、`service/bifrost-blackbox-exporter`、`scrapeconfig…/bifrost-gitea-probe`、`prometheusrule…/bifrost-host-rules`、`configmap/bifrost-dashboard-hosts`；`==> apply` 下面同样 8 行 `created`；`deployment "bifrost-blackbox-exporter" successfully rolled out`；最后 `host-exporters: cluster OK`。

另一种做法（不用你跑命令）：统筹线程对这 4 个文件各做一次 `plan_manifest` + `apply_manifest`，你在 Console 的 Needs you 里批 4 张 C 级单。两种只选一种，以后改这几个文件也用同一种（见切法第 7 节）。建议用上面这条命令：一次 dry-run 看全 4 个文件，一条命令做完。

做完回：「集群放好了」。

## 第 6 步　核对（统筹线程做，约 10 分钟；你不用看）

统筹线程跑 `bash /tmp/b4-host-exporters.sh check`（只读：6 个端点各打一次，全是 `ok` 才算过），再在 Prometheus 里核对切法第 7 节第 6 步列的那几个数，打开面板「Bifrost Hosts」看每块都有数。核对完在线程里报。

## 第 7 步　演练：每台停一次报数，看手机（每台约 5 分钟）

每台：停掉 node_exporter → **3 分钟内**手机收到 `CRITICAL Host <名字> (<地址>:9100) is not answering` → 恢复 → 收到 `RESOLVED Host … is not answering`。记下停的时刻和推送到的时刻。中转对同一条告警 30 分钟内只推一次，**同一台 30 分钟内别演第二次**。

mini 两台统筹线程可以代做（文末第 1 条），用的是 `ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 vision@192.168.10.52 'launchctl bootout gui/$(id -u)/com.bifrost.node-exporter'`，恢复是同一处换成 `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bifrost.node-exporter.plist`（.50 同样）。

**06**（每条问一次节点钥匙口令）。停：

```bash
ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey -i /Users/vision-mac-trader/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -n systemctl stop node-exporter.service && date'
```

收到推送后恢复：

```bash
ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey -i /Users/vision-mac-trader/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -n systemctl start node-exporter.service && systemctl is-active node-exporter.service'
```

**NAS**（每条问一次 k8s_admin 的口令）。停：

```bash
ssh -t -o IdentitiesOnly=yes -i /Users/vision-mac-trader/.ssh/id_ed25519 k8s_admin@192.168.10.20 'sudo docker stop node-exporter && date'
```

收到推送后恢复：

```bash
ssh -t -o IdentitiesOnly=yes -i /Users/vision-mac-trader/.ssh/id_ed25519 k8s_admin@192.168.10.20 'sudo docker start node-exporter'
```

**做完会看到**：停的那条打印当时的时间；手机上 ntfy 先后两条推送；恢复的那条打印 `active` 或 `node-exporter`。

做完回：「演练完了：06 x 分钟、NAS x 分钟」（mini 是你自己演的也写上）；哪台 3 分钟内没收到就回「<名字> 没收到」。

---

## 要你定的（在线程里回一句）

1. **mini 两台由谁装、谁演练。** 建议：统筹线程。理由：不用 sudo，只写 `vision` 家目录，用的是 Agent 已有的只读 SSH 钥匙；你少两步、约 10 分钟。回「mini 由统筹线程装和演练」，或「mini 我自己来」。
2. **第 5 步用哪种。** 建议：你跑 `cluster` 那一条。回「集群用命令」，或「集群走审批单」。
3. **.50 自己整机坏（切法 G1）。** 现在靠 .52 的看门狗，约 5–6 分钟，达不到 3 分钟。建议 A：放进 B3「告警转发成对」一起解决，B4 ① 先接受。另有 B：现在就在 platform 仓库把看门狗的默认等待从 5 分钟改成 1 分钟、重新部署 .52（统筹线程做）。回「G1 按 A」或「G1 按 B」。
4. **NAS 整机坏时 Prometheus 可能先卡住（切法 G2）。** 建议 A：NAS 装 M.2 SSD 那次本来要关机，就在那次验；卡住了再给 .52 的看门狗加一项直接探 NAS。回「G2 按 A」。
5. **两台接连坏时第二条推送可能晚 5 分钟（切法 G3）。** 建议现在不改。不回就按不改。

## 撤销（只在要退回时用）

- mini：`launchctl bootout gui/$(id -u)/com.bifrost.node-exporter`，再删 `~/Library/LaunchAgents/com.bifrost.node-exporter.plist` 和 `~/bifrost-agent/node-exporter/`。
- 06：`sudo systemctl disable --now node-exporter.service smartctl-exporter.service`，再删两个服务文件 `/etc/systemd/system/{node,smartctl}-exporter.service` 和 `/usr/local/bin/{node,smartctl}_exporter`；`smartmontools` 留着无害。
- NAS：`sudo docker compose -f /volume1/docker/host-exporters/compose.yaml down`。
- 集群：管理员 kubeconfig 下对同样 4 个文件 `kubectl delete -f`。先删 `bifrost-host-rules.yaml`，否则 `BifrostHostTargetsMissing` 和 `BifrostGiteaProbeDown` 会报一次 warning。
