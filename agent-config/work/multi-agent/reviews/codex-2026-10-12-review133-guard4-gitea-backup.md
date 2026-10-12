VERDICT: fix first
A SEQUENCE FOR (a)–(f): found
RULES THAT ONLY LACK A TEST: 2
范围：merge-base→HEAD（992f7a5、1c931da）；k8s/ 路径相对 guard-4/bifrost-trade-infra。只做静态推演与副本测试；未用集群、网络、Docker、凭据，未提交。
P1 — `k8s/cicd/gitea-backup/backup.sh:112,147,224`、`drill.sh:169,194`【b,d】：DB 副本后创建 B，再复制目录；B 的 fsck/manifest 合格，OK→LATEST，但 DB 没有 B，恢复的 Gitea 不会自动导入孤立目录，HTTP clone B 失败。反向：DB 副本后删除 B，再复制目录；恢复 DB 仍列 B，磁盘无 B，clone B 失败；manifest 只剩 A，演练比较 A 后 PASS。最小修复：核对 DB、归档、manifest 三者仓库集合，并在发布 OK 前用隔离恢复实例验证所有 HTTP refs；不一致就失败。
P1 — `k8s/cicd/gitea-backup/backup.sh:197,201,215,224,236`【b,d】：NAS 暂满，A 行写成而 B 行写失败；空间随后释放，tar/checksum 成功；未检查 printf 退出码，缺 B 的清单仍获 OK，演练只比 A 而 PASS。LATEST.tmp 短写也可被 mv 发布。最小修复：逐项检查枚举、ref 提取及所有写入/改权/发布结果，核对完整性后才写 STATUS；失败不得更新 LATEST 或清理。
P2 — `k8s/cicd/gitea-backup/backup.sh:90,236,250,282`【c】：已有至少七个近期 OK，时钟回拨两个月；新 stamp 未占用，运行 OK，LATEST 指向它，但它落在七份及四周窗口之外，被本次 retention 删除，LATEST 悬空。最小修复：拒绝不大于既有最新 stamp 的时间，或使用单调运行序号并保护当前已发布运行；LATEST 必须选真正最新 OK。
P2 — `k8s/cicd/gitea-backup/backup.sh:94,129,236`【b】：杀 Pod 留 .partial；时钟回到同秒重试，mkdir -p 复用旧 stage，已删仓库可混入新副本。手动作业与定时作业同秒启动也共用 stage/LATEST.tmp，Forbid 不管手动作业。最小修复：独占锁、独占创建临时目录及唯一发布临时文件；禁止复用残留 stage；协调 drill 读者与 retention。
P2 — `k8s/monitoring/bifrost-alerting-rules.yaml:353,367`：首次作业一直 Pending/失败，从未有定时成功；last_successful_time 不存在，max 为空，两告警永不触发。仓库事实依据 `k8s/monitoring/bifrost-cluster-state-rules.yaml:4`。最小修复：添加 absent/从创建时间计龄的未成功分支，并覆盖缺失指标。
P2 — `k8s/cicd/gitea-backup/drill.sh:38,41,47`：克隆均成功，但 NAS 满导致报告 cp 失败或目录不可写，仍 exit 0，定时成功掩盖证据丢失。最小修复：报告持久化/改权失败必须非零退出。
P2 — `k8s/cicd/gitea-backup/rehearse.sh:142,160,174`：push 完成与第二个容器启动落在同秒，即使实际 backup.sh 尚未执行，闭区间秒级比较仍称重叠；start 还包含 commit 时间。最小修复：让 push 与脚本内复制阶段通过握手同步并验证成功完成。
P2-test — `k8s/cicd/gitea-backup/test_gitea_backup.py:50`：当前清单无令牌，但增加 projected.serviceAccountToken 及其 mount 后该测试仍 PASS；最小修复：检查全部普通/init 容器及卷的显式令牌、Secret 来源。
P2-test — `k8s/cicd/gitea-backup/test_gitea_backup.py:92`：当前选择器正确，但把 key 改成 wrong-label，覆盖测试仍 PASS；最小修复：校验 key/operator 和完整 selector 对每个实际 Pod 标签的匹配。
主问题逐项：a 未找到当前清单下改变 live 数据或取得 API/Secret 的具体序列（网络策略实际落实未核验）；b、c、d 已找到上述序列；e 未找到生成令牌/app.ini/密码哈希进入日志或报告的具体序列，stderr、启动日志等错误路径未运行；f 新目录只有五个对象，未见 RWO/亲和造成的重启死锁，详见第 7 点。
1. Brief 1 — met（静态）：`k8s/cicd/gitea-backup/cronjob-backup.yaml:16,18,33,35,58`，UTC、Forbid、镜像、uid/gid、无自动令牌/RBAC；镜像工具实际存在仅有协调者演练证据。
1. Brief 2 — met：`k8s/cicd/gitea-backup/cronjob-backup.yaml:38,45`，required hostname affinity 与 Deployment tolerations 相同。
1. Brief 3 — met：`k8s/cicd/gitea-backup/cronjob-backup.yaml:77,87` 双层只读；`backup.sh:112` mode=ro online backup，未调用 dump。
1. Brief 4 — not met：`k8s/cicd/gitea-backup/backup.sh:112,147,171,200,224,236`，DB integrity/fsck/三次复制具备，但跨时刻集合、元数据写失败及 LATEST 不满足。
1. Brief 5 — met（静态）：`k8s/cicd/gitea-backup/nas-volume.yaml:14`、`backup.sh:32,95,104`、`README.md:41`；有 nfs-cold、0700/0600 和导出访问说明，改权失败处理见 P1。
1. Brief 6 — not met：`k8s/cicd/gitea-backup/backup.sh:231,250,282`，正常失败不轮转，但回拨可删本次 OK 并留下悬空 LATEST。
1. Brief 7 — not met：`k8s/cicd/gitea-backup/cronjob-drill.yaml:70,73,89`、`drill.sh:150,169,196`，隔离恢复/token/HTTP refs/零仓库拒绝具备，但遗漏仓库可 PASS，报告失败仍成功；报告子目录可写是明确例外。
1. Brief 8 — not met：`k8s/cicd/gitea-backup/rehearse.sh:95,100,174,217,243,272`，三个种子仓库及三个故障有实质检查，但秒级计时不能证明 push 发生在备份脚本内。
1. Brief 9 — met：`k8s/cicd/gitea/deployment.yaml:80`，只在第二笔提交关闭注册，与备份目录分开应用。
1. Brief 10 — not met：`k8s/monitoring/bifrost-alerting-rules.yaml:351,365`、`agent-config/MAINTAINERS.yaml:92`、`k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml:92`，登记和阈值满足，但无首次成功时永不告警。
1. Brief 11 — not met：`k8s/cicd/gitea-backup/test_gitea_backup.py:40,50,68,76,85,103` 六项存在且基线 6 passed，但显式令牌挂载及错误选择器未被拦。
2. 副本实测：可写 live mount→`test_live_data_mount_is_read_only` FAIL；automount=true→`test_no_service_account_token_and_no_rbac` FAIL；镜像 1.21.12→`test_image_tag_matches_the_deployment` FAIL；显式挂载 projected token→该令牌测试 PASS，错误策略 key→覆盖测试 PASS。详见本目录 MUTATION_RESULTS.txt；三脚本 bash -n PASS，shellcheck 未安装；使用已有 /opt/anaconda3/bin/python3，默认 Python 缺 pytest。
3. 两 Job 均 `Forbid/startingDeadlineSeconds=3600/activeDeadlineSeconds=3600`，backoff 备份=1、演练=0（各 CronJob:18–25）；Pending 和运行卡住均在 Job 一小时期限后终止，Forbid 只挡同一 CronJob 的活动 Job，错过启动窗口不补无限历史；两 CronJob 可互相重叠，手动 Job 不受 Forbid 管。此前有定时成功：相应告警在 26h+30m、35d+1h 后响；从未成功：两者均不响；手动作业不更新 CronJob 成功时间。
4. `k8s/cicd/gitea-backup/cronjob-drill.yaml:70–88`：正常 subPath bind mount 只允许改 drills 子树，.. 返回只读 /backup，不能借它删/改兄弟 run；可删除旧演练报告。它不是 NAS 客户端之间的隔离边界。
5. 仓库事实：Gitea 明文备份增加同一导出客户端可读的 app.ini 密钥/internal token 和 DB token hashes（`README.md:43–50`）；logical 已在同 NAS 放未加密 Trade public、journal/research/ops_feedback/raw_broker 数据（`k8s/data/logical-backup/cronjob-backup.yaml:83`、`backup.sh:88`），不导出 PG 角色密码且拒绝含密码的 USER MAPPING（`backup.sh:121–125`）。因此增加服务凭据暴露，已有业务数据暴露不能抵消它；不能仅凭仓库量化两者损害。cluster-state 则先 age 加密才落盘（`k8s/data/cluster-state-backup/backup.sh:256–263`）；不作选择建议。
6. 三故障确实到达相应检查：截断后重签 checksum→`drill.sh:91` integrity；改 ref 后重签→`drill.sh:186` mismatch；删除可达对象并先 fsck 证伪→`backup.sh:171–188` 三次失败且 LATEST 不变。未见由恒真条件决定的 PASS；重叠 PASS 可被粗计时误判。未重跑 Docker，输出不作为本次独立实证。
7. Owner 命令不完整且作用说明不全（`guard-4/REPORT.md:138–157`）：create job 不等待，应保存 Job 名、等待备份 Complete/检查 OK/LATEST 后才创建 drill，再等待验证；告警先安装更易观测。新目录应用仅管理 ConfigMap/PVC/两 CronJob/NetworkPolicy，不改 Gitea（动态供给 PVC 还会产生 PV/NAS 子目录）；maintenance 的 -k 还 apply SA/ClusterRole/ClusterRoleBinding/Role/RoleBinding/CronJob（`cronjob.yaml:18–84`），deployment.yaml 还 apply Service（:2）。整对象 apply 可能覆盖现场漂移。RWO 是同节点共享，Gitea 新 Pod 不依赖 backup；required affinity 只约束 backup 调度，旧 Gitea 消失可让 backup Pending，不形成反向死锁；容量/挂载实际条件待 Owner 核验。
8. BEFORE merge：修跨时刻集合和 HTTP 可恢复性、写错误/残留目录/并发发布/时钟保护、无成功告警及报告失败；补两处静态防线和可靠 push 重叠证明，并重跑针对上述序列的演练。
8. BEFORE APPLY：修正文档等待顺序与整对象作用范围；Owner 决定新增 NAS 凭据暴露后，核验同节点只读挂载/重启、NFS 权限与 drills 挂载、策略落实、真实体积/管理员恢复及定时指标/首次失败告警；注册变更另行应用。
END OF REPORT
