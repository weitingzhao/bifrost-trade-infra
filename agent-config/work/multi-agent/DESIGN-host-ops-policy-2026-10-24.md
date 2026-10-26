# 主机操作策略与带外执行器

2026-10-24 · Work 560 · W-31 第 4 轮 4.7 / W-50。
状态：复核 573 修订稿（2026-10-26 · Work 577），未签名，未实施。
复核 1 原文在 `~/agent-work/codex-work-560/REVIEW-1.md`；
复核 573 在 `~/agent-work/codex-review-573/REPORT.md`，逐项回应见同目录 `RESPONSE.md`。
本次只改设计和准入条件，没有完成执行器或部署验收。

Owner 已决定三层授权。
只读直接做；例行操作按签名策略自动做；高风险操作逐次批。
本设计落实这些决定，不重新讨论逐条命令审批。
执行器由平台管理，节点钥匙不交给 Agent。

## 1. 依据与现状

本次只读本地仓库，没有查询运行环境。
infra 基线为 `70bc5e8`，platform 为 `52a95303`。
“本周”指 10-18 至 10-24；旧操作单也全部纳入目录。
操作单证明操作范围，不证明每一步已经执行。

| 依据 | 本设计采用的事实 |
|---|---|
| [ADR §5、§12](../../ADR-ops-architecture.md) | 签名放宽、即时收紧、过期从严；修复链保留 statefile |
| [发布策略提案 §3、§7](../release-approval/PROPOSAL-2026-10-08.md) | 授权绑定规则；失败即关；主动提醒续签 |
| [WORK 4.7、W-50](../../WORK.md) | 减少终端搬运；`.50` 领单；专用受限凭证 |
| platform `actions/{catalog,runner,normalize}.go` | 现有 A/B/C/D/X；host runner 已定义；未知参数会被忽略 |
| platform `approvals/{service,execution,types}.go` | 参数哈希、单次租约、unknown；statefile 保留 500 条闭单 |
| platform `server/actions_wire.go` | C/D 直接调用被拦；发布策略例外；内部执行路径单独标记 |
| platform `actions/actuation.go` | `owner_run_command` 只交接，不在 API 内执行 shell |
| platform `network/fixed_ip.go` | 校验子网、冲突、MAC；写后三字段读回；不确定写入不重试 |
| platform `releasepolicy/{policy,sshsig}.go` | SSHSIG 验签、有效期、冻结与防旧解冻重放 |
| platform `agentrt/rules/{rules,yaml}.go` | 闭合 YAML 解析；未知字段、别名、多文档拒绝 |
| [agent-host 服务](../../../scripts/agent-host/bifrost-agentd.service)、[出站规则](../../../scripts/agent-host/agent-egress.nft) | 分用户、无 sudo、私有临时目录；禁止节点 SSH |

上表 platform 路径均相对 `api/internal/`。
`owner_run_command` 和 `unifi_client_fixed_ip` 当前都是 D 级。
新策略需要专门接线，不能直接沿用发布自动批准入口。
W-50 的“现在”列描述选定方案；其状态仍是搁置。
因此不能宣称带外执行器已经上线。

## 2. 三层目录

`R` 为只读，对应 A。
`M` 为例行操作，命中规则才自动执行。
`H` 为高风险操作，保留 C/D 的逐次审批。
`X` 是三层之外的禁止项。
本表动作名除明确标为“现有”者，均为拟新增。

参数只能引用登记对象，不能传任意路径、URL 或 shell。
`host` 绑定资产 ID、主机钥匙指纹、系统和生命周期。
`bundle` 绑定审阅过的脚本、配置及制品摘要。
`plan` 绑定前态、影响对象和回退方案。
表中来源编号见 §2.4。

### 2.0 资产登记的信任根

全部登记表合成版本化 `host-ops-inventory` 制品。
Owner 以 `bifrost-host-ops-inventory` 域签名完整字节。
Agent 可提案；只有 Owner 签名才能发布或替换。
执行器和 helper 均在本地验签并原子安装。
文件及父目录归 root，Agent 与平台服务不可写。
安装记录版本、摘要和有效期，拒绝回放旧版本。
签名、有效期或本地副本缺失，R/M/H 都不执行。

| 登记对象 | 签名内容 |
|---|---|
| host | ID、环境、系统、host key、MAC、固定 IP、生命周期初值、允许的 executor |
| service/project | 规范服务名及别名、配置摘要、`stateful`、依赖、允许动作和维护范围 |
| root_id/install_id | 根路径、属主、用途、可重建证明、文件清单、安装 execution ID |
| endpoint_id/repo_set | 固定地址、端口、只读方法、仓库集合和合法映射 |
| protected registry | VIP、共享地址、禁止目录、数据卷、受保护服务及凭证位置的标识 |

R 的 allowlist 直接来自已签登记制品，不来自请求或可写数据库。
`host_logs` 在 helper 内先限制来源、过滤字段，再脱敏。
未经脱敏的日志不离开目标主机；失败时抑制整段。
平台再次脱敏，不能代替 helper 的第一道处理。
登记表扩权不自动扩大旧 M 策略；摘要不符须重新签策略。
运行状态另存只增的 journal，不能改写签名登记表。
安装归属由签名清单和 helper 的安装回执共同证明。

### 2.1 R：直接执行并留审计

| 具名动作与参数 | 可触碰范围、实际执行 | 回退 | 来源 |
|---|---|---|---|
| `host_status(host, check)` | 固定 `systemctl show/is-active`、`launchctl print`、`docker ps`、版本与主机身份 | 无写入 | O2/O3/O13 |
| `host_logs(host, service, since, lines)` | 固定服务的 journal、容器或 launchd 日志；最多 200 行 | 无写入；输出先脱敏 | O2/O13 |
| `host_storage_status(host, root_id)` | `df`、受限 `du`、RAID、SMART 只读探测；不遍历备份内容 | 无写入 | O13/W1 |
| `host_network_probe(host, endpoint_id, kind)` | 已登记端点的 DNS、TCP、ping、健康 GET；禁止重定向和任意端口扫描 | 无写入 | O13/B |
| `host_integrity_check(host, profile)` | 检查属主、权限、服务摘要、隔离配置；钥匙只回指纹 | 无写入 | O2/O3/O13 |
| `host_inventory_plan(host, operation)` | 生成缓存、工作目录、节点卷、安装对象的只读清单 | 无写入 | O2/O11/W1 |
| `platform_state_check(scope, check)` | 平台只读动作查窗口、运行、备份时间、Pod 摘要、UniFi 客户端 | 无写入 | O1/O4–O13 |

`R` 不包括读 Secret、数据库备份、私人目录或进程环境。
需要提权的 SMART 仍由固定 helper 执行。
隔离探针可能启动子进程，归 M，不冒充严格只读。

### 2.2 M：规则匹配后自动执行

| 具名动作与参数 | 可触碰范围、实际执行 | 回退或停止条件 | 来源 |
|---|---|---|---|
| `host_service_restart(host, service)` | 登记服务的 `systemctl restart` 或 `launchctl kickstart`；排除 never-M | 重启不恢复内存；健康失败停自动循环 | O2/O13 |
| `host_service_state(host, service, state)` | 固定 unit 的 start/stop/disable；排除 never-M；含旧 Mac agentd 退役 | 恢复原启用及运行状态；agentd 先停派并排空 | O2/O8 |
| `host_container_restart(host, project, service)` | 固定容器 `docker restart`；不变镜像、挂载、权限 | 健康失败恢复旧配置；内存不可恢复 | O13/B |
| `host_compose_reconcile(host, project, bundle)` | 仅 `stateful=false`；签名 compose 的 `pull`、`up -d` 或重建 | 保留旧 digest/config；用旧版重建；不执行 `down -v` | O13/B |
| `host_image_stage(host, artifact)` | 校验归档后 `docker load`；只导入已登记镜像 | 删除本次未引用镜像；不改运行容器 | O13 |
| `host_monitoring_install(host, bundle)` | mini 安装 LaunchAgent；06 安装 exporter；NAS 固定 compose | 恢复旧文件与服务；首次安装可撤登记对象 | O13 |
| `host_monitoring_remove(host, install_id)` | 仅移除本执行器安装回执对应的 exporter 与文件 | 重装原签名 bundle；不接管其他安装；先协调告警 | O13 |
| `host_monitoring_drill(host, exporter, duration_s)` | 停一个 exporter，记录告警，再恢复；最长 10 分钟 | 主机本地定时恢复；一次只演一台 | O13 |
| `host_agentd_update(host, bundle, environment)` | 停派、排空、只替换已签二进制、启动、核对；unit 不变 | 回到上一 digest；unit、隔离、凭证、出站规则变化转 H | O2/O8 |
| `host_toolchain_install(host, bundle)` | 已登记目录内安装固定 Go/Node/CLI/测试 DB 工具 | 切回旧版本；不运行可变远程安装脚本 | O2/O3 |
| `host_validation_run(host, profile, bundle)` | 固定 sandbox、隔离、bench、exam、Git 保护探针 | 停指定进程组；只清合成测试资源；不放宽保护 | O2/O8 |
| `host_temp_cleanup(host, plan)` | 重建缓存、node_modules、登记临时日志；先移入隔离区 | 7 天内恢复；到期只清可重建对象 | W1/O2 |
| `host_lifecycle_collect(host, plan)` | 调现有生命周期检查；按任务归属归档已结束 worktree | 恢复 bundle；脏目录、无归属目录只报 | W1 |
| `host_netplan_apply(host, plan)` | 仅 `new/out-of-cluster`；签名配置、备份、generate、apply、双路探测 | 先装本地超时回退；集群内一律 H | B |
| `host_new_node_join(host, runbook, cluster_id)` | 新空白 worker；固定 K3s 版本、标签和初始 taint | 无负载时撤本次安装；已有工作负载转 H | B/W2 |
| `host_new_node_fixed_ip(host, plan)` | 平台调用现有 UniFi 实现；只写目标 MAC 的三字段 | 恢复 before；原为 DHCP 时需新增受限恢复动作 | B/N |
| `host_git_endpoint_set(host, repo_set, mapping)` | 固定 origin/insteadOf；只允许登记的 Gitea 地址 | 恢复原配置；不接触 credential helper | O8 |

M 不是“任何可撤回命令”。
重启有短时中断，先检查依赖和维护锁。
MinIO、Gitea、registry 必须登记为 `stateful=true`。
有状态项目换镜像或 recreate 一律 H，不能假定降版能回退数据格式。
M 仅允许同 digest、同配置的容器 restart，仍须依赖检查。
未知 `stateful` 按有状态处理；NAS 旧 MinIO 不纳入自动重建。
never-M 固化在 catalog 和 helper 代码，两边都检查。
名单为 `k3s`、`k3s-agent`、`containerd`、`docker`、`postgresql`、`sshd`、`bifrost-host-exec`、`systemd-networkd`。
匹配包含 `.service`、实例及 launchd 别名，先解析规范身份。
签名策略也不能覆盖名单，其他动作不能代替服务入口绕行。
名单限制既有服务维护；join 仅允许签名 runbook 中新 worker 的首次启动。
join 不得调用既有 K3s 服务的 restart/state 来完成修复。
执行器始终不得操作自己的账户、服务、钥匙或 helper。
自维护由 Owner 的独立维护入口逐次执行。
目录位于可写父目录时直接拒绝，不自动 chown 修补。

`prepare-agent-06.sh` 同时改防火墙、AppArmor 和凭证。
现有 `update-agentd` 会调用它，不能整体列入 M。
必须拆出仅换二进制的更新动作。
安装监控不自动授予新 sudo、特权挂载或端口权限。
这些能力先经 H 安装，后续复用才按 M。

临时清理只涵盖可重建且无活跃引用的对象。
身份由受保护登记表决定，不靠目录名猜测。
helper 在锁内重算候选、活跃引用、属主、inode 和字节上限。
请求中的 plan 只是提示，不能授权其列出的路径。
实际候选必须属于签名登记范围，且不超出已绑定的计划。
候选变化即拒绝并重做 plan；隔离及到期清理都复查。
删除唯一代码、证据、备份或业务数据，永远归 H。
已清缓存只能重建，不能宣称原字节可恢复。

netplan 自动范围只含集群外单机地址、DNS 等登记变更。
任何集群成员，包括 PROD Postgres 节点，一律 H。
涉及路由拓扑、共享 VIP 或无法证明回退，转 H。
新节点加入前须证明不在集群、无业务卷。
加入时保持 `NoSchedule`；放开调度另走平台动作。
join 开始时先持有 host 锁，原子 CAS `new → joining`。
生命周期记录带 generation，先持久化，再签票据、再做副作用。
helper 同样先持久化 `joining`，才允许本次 join 的步骤。
有效生命周期取登记初值与两侧 journal 中最保守的状态。
任何一侧不一致、失联或已开始 join，都不能再视作 new。
成功转 `in-cluster`；失败留 `joining/unknown`，回退不恢复 new。
重设 new 只能通过更高版本的 Owner 签名登记变更。
重设前须证明无集群成员身份、业务卷及运行负载。
已有 join credential 仅由 helper 消费，不交给 Agent。
创建、轮换或扩权该 credential 仍逐次批准。

UniFi 自动入口只适用于登记为 `new` 的机器。
MAC、IP、hostname 必须与资产记录完全匹配。
现有 `unifi_client_fixed_ip` 保留 D 级入口。
新入口复用其校验，额外检查生命周期与期望前态。
补齐 DHCP 恢复、跨进程互斥后才能签入策略。
UniFi 从未见过的客户端返回 `ErrClientNotFound`，本动作不写入。
不附带“先 DHCP 一次”的隐含网络步骤；返回登记缺口供处理。
固定 IP 还要排除登记的 VIP、静态地址和共享地址。
例如 `192.168.10.100` 不因未出现在 UniFi 列表就可分配。
fixed-IP 与 join 共用 host/lifecycle 锁；join CAS 后不能再领 fixed-IP。

### 2.3 H：逐动作批准；X：禁止

每行是一类具名模板，不是一张包办全部动作的审批单。
参数、目标 UID、制品摘要和回退范围全部入审批哈希。

| 具名动作与参数 | 可触碰范围、实际执行 | 回退及限制 | 来源 |
|---|---|---|---|
| `host_disk_provision(host, disk_id, layout)` | 指定序列号的分区、格式化、存储池 | 无原地回退；需已验备份；装 SSD 由人做 | B/W2 |
| `host_data_delete(host, object_ids, plan)` | 精确数据、卷、备份或唯一文件；包括解密副本清理 | 从备份恢复；不能当临时缓存处理 | O2/O7/W1 |
| `host_network_security_change(host, plan)` | firewall、VLAN、nftables、路由拓扑 | 独立管理路径回退；不经 M netplan 绕行 | O2/B |
| `host_netplan_apply(host, plan)`（H 条件） | 任一集群成员的 netplan；包括数据节点 | 单次签名；独立管理路径与本地回退 | B/复核 A4 |
| `host_compose_reconcile(host, project, bundle)`（H 条件） | 有状态项目的镜像变更或重建 | 先验证备份和恢复；旧 digest 不等于数据回退 | O13/复核 A4 |
| `host_service_restart/state`（H 条件） | never-M 服务的逐次维护；执行器自身除外 | 显式影响及恢复计划；本执行器不得自维护 | O2/复核 A4 |
| `host_node_power(host, operation, plan)` | 已入集群节点 reboot/poweroff；NAS 停机也纳入 | 开机与恢复负载；不可恢复内存 | O2/W2/B |
| `host_node_retire(host, step, plan)` | cordon、卷备份/删除、drain、K3s uninstall、删除 Node | 每个高风险步骤单独批准；按 UID 复核 | O2 |
| `host_access_change(host, account, plan)` | 新账户、sudoers、authorized_keys、AppArmor、helper 安装/升级、NAS 权限修复 | 逐次批准；执行器自身由 Owner 维护；不回退成不安全权限 | O2/O3/O13 |
| `credential_install(target, credential_ref, operation)` | 生成、复制、轮换、撤销 Secret/令牌；CLI 登录、钥匙串、pgpass | 重新签发；不输出值；Owner 完成设备登录 | O2/O3/O4/O5/O8/O12 |
| `host_backup_verify(host, backup_id, plan)` | 指定加密备份、私钥引用、隔离解密目录 | 清理副本另有明确授权；不读回明文 | O7 |
| `rule_publish(rule_id, version, digest)` | 规则签发、续签、信任锚、公钥更换 | 新签版本；不得回退到更宽旧规则 | O2/O9 |
| `host_execution_resolve(execution_id, evidence_hash, outcome)` | 只对账并关闭 unknown；不执行原命令 | Owner 签本次 resolve plan；证据不足不释放锁，见 §4.3 | 复核 B13 |
| `platform_manifest_apply(plan_id)` | 现有 `plan_manifest/apply_manifest`；固定对象与提交 | 旧清单；删除对象或回退安全护栏仍逐次批 | O1/O6/O7/O10–O13 |
| `platform_access_change(plan_id)` | RBAC、准入策略、NetworkPolicy、仓库权限 | 精确旧策略；扩大权限必须新批准 | O4/O5/O6/O8/O12 |
| `platform_database_migrate(database, migration_id)` | 角色、建库、schema、授权；PROD DDL | 按迁移回退；破坏性 DDL 不自动 | O5 |
| `platform_retention_apply(plan_id)` | Tekton TTL CronJob 与不可恢复的运行记录删除 | 旧规则只影响以后；已删记录不回来 | O11 |
| `gitea_repository_admin(repo, operation, plan)` | 转普通仓库、复制分支、归档、删仓库/组织、注册开关 | 按动作恢复；删除可能需整库恢复 | O7/O8 |
| `platform_release_request(release_id)` | 现有发布动作；仍按专门发布策略判断 | 依原发布回退约定；主机策略不扩大授权 | O1/O4/O6/O8/O12 |
| `platform_backup_start(backup_id)` | 现有具名备份/Job 动作；保留原级别 | 无需撤回成功备份；清理失败产物另判 | O5/O7 |
| `owner_run_command(command, reason, runner)`（现有） | 未覆盖操作逐次 D 级兜底；Owner 手工运行 | PROD 拒绝 `runner=host`；新 executor 永不领自由 shell 单 | ADR/W-50 |
| `live_trading_operation(target, operation)`（X） | D10 禁止的真实发单、实盘对冲及执行扩容 | 不生成可批准执行单；本策略不能解锁 | B/spine |

H 表含操作单中的非主机事项，防止遗漏或误收进 M。
它们继续走原平台动作，不改为 SSH 执行 kubectl。
普通观测清单可按现有专门策略自动处理。
含 critical 告警、RBAC 的整包不能按观测例外放行。
同一次发布可关联一个展示卡，不能吞并 H 的独立授权。
启用实盘交易始终禁止；相关其他高风险维护仍逐次批准。

### 2.4 操作单覆盖索引

| 编号与本地来源 | 覆盖范围 |
|---|---|
| O1 [OWNER-STEPS-2026-10-13](OWNER-STEPS-2026-10-13.md) | PROD 发布、试跑、流水线应用与回退 |
| O2 [OWNER-STEPS-agent-host-06](OWNER-STEPS-agent-host-06.md) | 出集群、安装、凭证、隔离、更新、启动、退役 Mac 服务 |
| O3 [OWNER-STEPS-agentd-user](OWNER-STEPS-agentd-user.md) | 专用账户、CLI 安装与登录、launchd、状态检查 |
| O4 [OWNER-STEPS-gate-a-stg](OWNER-STEPS-gate-a-stg.md) | STG 接线、令牌、Git 权限与常驻服务 |
| O5 [OWNER-STEPS-agentrt-21](OWNER-STEPS-agentrt-21.md) | Secret、pgpass、Redis、角色、库、迁移、网络、备份 |
| O6 [OWNER-STEPS-digest-s1](OWNER-STEPS-digest-s1.md) | 构建 Task、镜像摘要记录及回退 |
| O7 [OWNER-STEPS-gitea-backup](OWNER-STEPS-gitea-backup.md) | 备份安装/启动、注册开关、挂载、解密、清理、卸载 |
| O8 [OWNER-STEPS-gitea-primary](OWNER-STEPS-gitea-primary.md) | 凭证、团队、保护、仓库迁移、端点、服务、归档与删除 |
| O9 [OWNER-STEPS-rules-o18-o19](OWNER-STEPS-rules-o18-o19.md) | 签名钥匙、信任锚、初始规则与续签 |
| O10 [OWNER-STEPS-digest-s2-s3](OWNER-STEPS-digest-s2-s3.md) | RBAC、四次试跑、摘要核对、两环境流水线；试跑会创建对象 |
| O11 [OWNER-STEPS-s7-tekton-ttl](OWNER-STEPS-s7-tekton-ttl-2026-10-24.md) | TTL 应用与不可恢复的 TaskRun 清理 |
| O12 [OWNER-STEPS-td432](OWNER-STEPS-td432-2026-10-24.md) | 只读账号、Secret、准入、webhook、挂载、撤权与轮换 |
| O13 [OWNER-STEPS-w68-b4](OWNER-STEPS-w68-b4-2026-10-24.md) | 四台监控、NAS 权限、镜像搬运、集群规则、演练与卸载 |
| W1 [LESSONS 第 188 条](LESSONS-from-practice.md)、[CUT-lifecycle](CUT-lifecycle-2026-10-24.md) | 本周磁盘不足、缓存清理、工作目录归属与归档 |
| W2 [WORK W-68](../../WORK.md) | SSD、NAS 停机、新 R7 worker；仍是计划 |
| N platform `network/fixed_ip.go` | 本周新增固定 IP 动作；未查询上线状态 |
| B 本任务 `BRIEF.md` 的 Owner 决定 | netplan、容器重建、新节点和固定 IP 的明确授权方向 |

未找到本周 netplan 实际执行记录，故只标为 B。
旧文件里的 `bifrost-agents` 仅作迁移历史，不当活跃组织。
O7 的共享挂载/卸载只作为受批备份会话的子步骤。
编译、Git 取文件和本地临时暂存属于制品准备。
远端安装只消费固定摘要，不执行工作树里的新脚本。

## 3. 签名规则、匹配与冻结

建议新增 `host-ops` 规则族，沿用 agentrt 的五字段头。
它使用独立签名域 `bifrost-host-ops-policy`。
验签复用现有 SSHSIG 库和 Owner 信任锚。
规则及收紧记录存在修复链 statefile，不依赖 agentrt PG。
Console 将它展示为规则集成员。

### 3.1 签名规则与收紧方向

#### 2026-10-26 修订 · Work 601 / Review 595 B2 · 方案 A

依协调决定采用 Work 598 的方案 A，保留 §4.1 九项选择及首批七个 M 动作。
原 `maintenance_scope: string[]` 退场；候选登记对象改用必填 `action_scopes`，
每个 variant 有唯一 `id`、`action`、完整请求 `params` 约束和分开的 `forward` / `rollback` 效果集。
这不是对依赖字符串赋予新含义。范围随 inventory 完整原字节签名；M 的 `inventory_digest`
继续固定该签名登记，任何目标、操作、参数或阶段变化都要重新签登记及引用它的策略。
尚未安装的 S1 候选 schema 不做旧格式回落，旧候选必须重新生成、审阅和签名。

- 每个效果条目固定 `object_id`、`operation`、`source_digest` 和完整 `parameters`；
  对象必须存在且与主对象同 host。正向与回退各自是完整集合，顺序无关；多项、漏项、
  重复、跨主机、跨目标、错操作、换来源、参数增加/缺失/变化及阶段交换都拒绝。
  同一次请求恰好匹配一个 variant；零个为 unsupported，多个为歧义拒绝。
- 参数约束为封闭类型 `enum`、`object`、`log_since`、`log_lines`。
  enum 是具体有限值；object 固定登记 ID、类型和主机，仅接受规范名/登记别名
  （`root_id` / `endpoint_id` / `install_id` 只接受 ID）。没有通配符或隐式路径授权。
  日志保留 §6.4 的时间和 1–200 行硬限制。
- `service` 必须绑定主服务；container 的 `project` 明确绑定已登记项目，
  compose 的主对象就是该项目。实际每个效果携带独立观测的项目 ID，逐项相等。
  `profile` / `plan` 是单值选择器，不能把多个 profile/plan 合并后任意选效果；
  实际效果上下文必须等于该签名选择器。当前七个 R 包含 profile 校验；
  首批之外使用 plan 的 M 模板仍 unsupported，不因此契约开放。
  已有 H Plan 则分别把正向参数和回退参数中的 project/profile/plan 与相应效果上下文绑定，
  连同观察到的 host 一起签入完整 Plan；有效签名也不接受相互矛盾的字段。
- `state` 操作必须携带明确的 `state=start|stop|disable`，正向值等于请求，
  回退值按签名效果单独固定。七个 M 各有封闭操作族，不接受通用 `access` 之类替代。
  R 只接受 `read`，全部七个 R 都检查登记范围和配置摘要，不再仅保护 logs。
- 实际身份先精确匹配已签规范名/别名，再与独立 safety catalog 交叉验证；
  systemd 名称归一化只用于硬禁令，不自动扩大授权别名。别名冲突或未知身份拒绝。
- `Dependencies` 与 §4.4 隔离锁闭包仍表示受影响资源。**affected ≠ allowed**：
  遍历依赖不产生效果权限；多个对象只有逐项写进对应阶段的签名效果集才可操作。
  合法 compose 闭包可同时包含项目与具名服务，同时保留仅加锁的共享资源。
  依赖完整性、实际锁持有和 unknown 隔离仍由 S2/S3 证明，不用范围匹配代替。

验收保持 Review 590 五个原反例及 Review 595 两个 B2 测试；另测七 M/七 R 阳性、
规范名与登记别名、多对象闭包、只在依赖中的对象越界、跨目标/主机、错操作、
阶段交换、state/project/profile/plan 绑定、缺失/歧义契约和未知模板拒绝。
实现使用测试锚与合成数据；这些是共享库模型证据，不是 S2/S3 运行时准入。


下面是格式示意，不是可签发的有效规则。
摘要和资产集合必须在签前具体化。

```yaml
rule_id: host-ops:prod
rule_version: 1
direction: initial
effective_at: 2026-10-25T00:00:00Z
expires_at: 2027-01-23T00:00:00Z
schema_version: 1
environment: prod
inventory_digest: sha256:<reviewed-inventory>
catalog_digest: sha256:<reviewed-action-contracts>
executor_ids: [host-exec-mini-50]
clauses:
  - clause_id: restart-exporter-06
    action: host_service_restart
    hosts: [agent-06]
    params:
      service: [node-exporter.service, smartctl-exporter.service]
    handler_digest: sha256:<reviewed-helper>
    conditions: [identity_matches, config_unchanged, no_conflicting_run]
    timeout_s: 120
    rollback: restore_previous_service_state
    max_per_day: 4
    max_per_week: 12
    repeated_success: {window_s: 3600, max_count: 3}
limits:
  global_writes: 1
  per_host_writes: 1
  cooldown_s: 300
  max_automatic_recovery_attempts: 1
reminders_days: [14, 3, 1]
digest:
  timezone: America/Chicago
  weekday: monday
  local_time: "09:00"
```

签名覆盖原始 YAML 全部字节。
拒绝未知字段、重复键、错误类型、别名和多文档。
有效期上限 90 天，时间必须带时区。
版本必须单调递增；新版本过期不退回旧版。
初始、扩权、延期、换 helper 或资产范围须 Owner 签名。
无法证明是收紧，就按放宽处理。
规则没有任意表达式，也没有命令正则授权。

**免签名修改只能追加限制，不能删除参与求交的约束。**
Owner 签名基线中的每个 clause 固定一个适用域：环境、action、hosts、
executor_ids 和参数允许集合；不以条件是否满足、限额是否耗尽或当前有效期筛选它。
规则的适用域为其基线各 clause 适用域的并集；这是找约束的范围，不是授权并集。
免签名记录保留基线和稳定 rule/clause/quota ID，不能重算或缩小这个适用域。
缩小 hosts、executor_ids 或参数集合，是在原适用域内增加准入谓词；
被排除的请求在该条款下得到拒绝，不能因条款退出匹配而回落到其他较宽条款。
删除 clause/rule 是在原适用域留下永久拒绝墓碑，不是移除约束。
到期、禁用、冻结也保留适用域并返回拒绝；物理文件缺失视为策略集不完整，拒绝 M。
解除这些限制或替换适用域须 Owner 新签，显式绑定被替换规则、收紧链和完整生效策略摘要；
单独新增一条较宽规则不能覆盖旧限制，不能重置历史计数或解开 unknown 锁。

| 字段 | 无需 Owner 新签的收紧方向 | 其他变化 |
|---|---|---|
| clauses / rules | 原适用域内追加拒绝墓碑，保留原条款与计数 | 物理删除、移除墓碑或改变适用域须签名 |
| hosts、executor_ids、参数允许集合 | 在原适用域内追加子集谓词；被排除者拒绝 | 新增、替换须签名 |
| conditions | 增加已定义的合取条件 | 删除条件为放宽；未知条件拒绝 |
| global/per_host_writes、次数与恢复上限 | 降低，包括降至零 | 增大须签名 |
| cooldown_s | 增大 | 减小须签名 |
| expires_at / effective_at | 提前到期 / 推迟生效 | 延期或提前生效须签名 |
| repeated_success | 降低 max_count；固定 window 内更早熔断 | 改 window 不可比较，须签名 |
| timeout_s、watchdog、rollback | 不支持自动比较 | 缩短也可能中断写；任何变化须签名 |
| inventory/catalog/handler/bundle 摘要、环境、签名锚 | 不可比较 | 替换须签名 |
| 审计、通知、时钟阈值、schema 和日历 | 不支持自动变更 | 须签名；不能关闭审计告警 |

收紧记录同时绑定完整生效策略集的父摘要、被限制规则摘要及单调版本，保留完整链。
完整策略集包含签名基线、收紧记录、墓碑及版本；并发更新用父摘要 CAS，过时更新重算。
平台、执行器、helper 都验证同一完整策略集及上述追加限制的语义，不能只信 `direction`。
字段方向表只是必要条件；丢失任何相交约束、缺链、未知转换或无法证明整体单调均拒绝免签更新。
在相同请求 x、时间 t、历史/额度/冻结/锁状态 h 下，必须满足
`Allow(P_new, x, t, h) ⇒ Allow(P_old, x, t, h)`；不能拿清空后的状态作比较。
S1 用三端共用的参考模型及 property tests 验证完整策略的授权集合子集性质。
覆盖传递性、混合字段、删条件、cooldown 反向和非法回退变化。
次数、状态和已执行副作用也纳入测试，不能只测静态参数。
收紧影响未启动步骤；已签的安全回退不能被缩短超时截断。

以下反例必须成为 S1 准入测试；不是本轮已经跑过的产品测试：

| 基线与变更 | 必须得到的结果 |
|---|---|
| 同目标 A 每天 4 次、B 每天 1 次；已用 1 次，删除 B | B 留拒绝墓碑，仍拒绝第二次；同规则内两个条款及跨规则各测一遍 |
| 同上，将 B 的 hosts/执行器/参数集合收窄，使原请求被排除 | 原请求仍落在 B 的固定适用域，被子集谓词拒绝；不能仅按 A 放行 |
| 删除最后一条 clause 或最后一条 rule | 墓碑拒绝；原本无任何覆盖的请求也默认拒绝 |
| 较严 B 到期、禁用或文件丢失 | 不回落到 A；到期/禁用拒绝原域，文件丢失拒绝 M |
| 无重叠的两个条款，收紧其中一个 | 另一条款域不受影响；验证局部收紧不会误作全局拒绝 |

### 3.2 签名制品清单

#### 2026-10-26 修订 · 类型化范围与制品证据的交集

§3.1 的每阶段效果条目签入精确来源摘要；来源还必须是已验证 handler、相关登记配置，
或本请求已签、已安装且实际字节复验通过的 bundle entry。
manifest 证明来源和字节，不能代替目标/操作/参数授权；反过来，签名范围也不能代替字节复验。
多对象作用及回退都必须从真实制品重建为 `host + identity + operation + source_digest + parameters`，
按完整集合匹配。source_digest 相同不能掩盖不同目标、不同操作或不同阶段。
未知脚本/模板、未重建效果、仅凭 capability 名称均拒绝；D10、never-M 和自维护禁令仍独立生效。

#### 2026-10-26 修订 · Work 606 制品选择绑定（Review 604 B1）

请求的 `params.bundle` 是精确 manifest 摘要，必须属于请求承诺的 `bundle_digests`，
也必须属于本次准入实际接收、已安装且验签、有效期、作用域和字节检查全部通过的集合。
请求承诺集合与接收集合必须完全相同且无重复；不能用另一个允许制品的相同 entry SHA256
替代所选 manifest，也不能借此绕过所选 manifest 的过期或安装检查。
策略允许集合仍可大于请求集合；合法正向及回退多 manifest 保留，不强制缩成一个包。
永久回归覆盖三个 bundle 动作的原替代/过期反例、所选制品未承诺/未接收/未安装、
签名或字节无效、真实不同来源的回退多包阳性及集合重排。
S1 仅检查可信适配器提供的安装标记和文件观测；持久化、实际文件身份与权限证据仍属 S2/S3。


`bundle` 必须来自 Owner 批量签名的 manifest。
签名域为 `bifrost-host-ops-bundle`，覆盖 manifest 完整字节。
manifest 绑定版本、环境、允许动作/主机集合、有效期及 helper 兼容摘要。
每个条目列出相对路径、大小、SHA-256、属主、权限和用途。
用途区分执行文件、配置、unit、compose、镜像归档和回退文件。
镜像同时固定 OCI digest；禁止可变 tag、联网安装脚本和隐含下载。
netplan 的配置字节也须签入 manifest，plan 只引用其摘要。
包内不放 Secret；凭证只引用已授权的目标端安装。

CI 仅生成候选包、差异和校验结果，不能签发。
Owner 审阅后批量签清单；M 条款固定允许的 manifest 摘要集合。
新制品须新签 manifest，并更新引用它的签名条款。
源码来自 main、CI 成功或 handler_digest 正确，都不能替代该签名。
执行器和 helper 都校验签名、范围、期限及实际收到的字节。
安全解包拒绝绝对路径、链接、重复条目和未列出的文件。
执行前从受保护暂存区重新核对字节，固定文件句柄与镜像 digest。
回退制品同时验证；旧制品未保留时不启动 M。
缺少有效 manifest 的 bundle 动作不能自动执行，转 H 审阅。
H plan 仍必须明确授权全部制品字节，不能接受任意新包。

### 3.3 匹配、限额与冻结

请求结构为 `action + params + host + work_id + requester_thread`。
调用身份由认证层取得，不信自报 requester。
执行器身份也由凭证绑定，不能只信 `executor_id`。
接线需补此校验；现有 host claim 的角色限制不足。

新 M 动作默认按需审批处理，不能简单设成 TierB。
专用 gate 命中后原子写入系统授权的执行记录。
记录标明 `authorization=host_policy`，不伪造 Owner 点击。
沿用审批租约协议，但不沿用“call directly”的自动批准分支。
所有入口共用校验；内部 executor 标记也不能跳过冻结复查。

匹配顺序固定：

1. 严格解析请求；未知参数直接拒绝，不沿用静默丢弃。
2. 查动作硬边界；X 拒绝，H 建逐次审批。
3. R 走本地签名登记的只读 allowlist；不依赖 M 策略有效期。
4. M 校验签名、版本、环境、有效期、冻结与信任锚。
5. 核对本地登记、生命周期、参数、helper 和签名制品字节摘要。
6. 生成确定性 plan，绑定前态、检查、回退和锁范围。
7. 原子登记授权结果、`params_hash`、`plan_hash`、幂等键。
8. 领单及每个副作用前重查策略、冻结、前态与租约。

两层合成固定如下：先按签名基线的固定适用域找规则，再在每个规则内找基线适用条款。
规则内所有适用条款取交集；规则之间也取交集，任何一项拒绝就拒绝，冲突即拒绝。
两层都不选“最宽的一条”，也不把条件失败的条款从匹配集合剔除。
没有任何基线覆盖默认拒绝；删除、收窄和到期按 §3.1 保留原域限制。
任一必需规则、收紧链或墓碑缺失就拒绝，不以剩余规则继续授权。
策略失效、读取错误、时钟异常、资产未知均不自动执行。
回退缺失、审计落盘失败、无法取得锁同样拒绝。
“不匹配”返回具体原因，并保留申请入口。
签名损坏或冻结不自动转成人工绕过路径。
未知请求不降格为自由 shell。

每条 clause 强制 `max_per_day/max_per_week`，缺少限额不签发。
按 UTC 日/周持久计数；更换版本、条款名或重启不清零。
条款变更须保持稳定 quota ID，相关目标合并计数防拆单。
平台原子预占；执行器独立复核并落盘后才能签票据。
失败和 unknown 均消耗次数；没有副作用的拒绝另记审计。
同 host/action 的反复成功也触发 `repeated_success` 熔断。
达到阈值暂停该条款目标并推送，不能靠持续重启假装已修复。
恢复须 Owner 签定范围的解除记录，不能重命名绕过。

冻结单独存为 `host_ops_freeze`，含单调 `epoch`。
任何已认证 operator 可冻结；冻结立即持久化。
解冻必须由 Owner 签 `bifrost-host-ops-unfreeze`。
签名绑定环境、当前 epoch、`min_rule_version` 和原因。
执行器与 helper 持久保存 `max_rule_version`，低版本一律拒绝。
解冻后版本不得低于本地最高值及签名要求的最低值。
高水位缺失或回拨保持冻结，由 Owner 恢复，不能回退旧规则。
删除冻结文件、回放旧解冻或回拨 epoch，均视为冻结。
缺少冻结记录也视为冻结。

`.50` 提供本地 `stop-writes` 入口，Owner/operator 无需平台即可触发。
入口只能停写，不能执行动作或解冻；状态归 root 并持久化。
平台 freeze 与本地 stop 任一成立即停止签票据。
冻结还撤销已发票据；每个写步骤须查当前 epoch 和短期执行许可。
helper 不能只凭未过期票据写入；撤销检查失联即停止新步骤。
冻结在执行器与 helper 收到后立即生效；失联许可最多存活 5 秒。
Console 显示各端确认和未确认主机，不宣称瞬时全网停止。
不再发许可后，即使持有旧票据也不能开始下一步。

冻结停止排队、新领单及未开始的副作用步骤。
已开始的命令进入动作定义的安全停止点。
不承诺瞬间撤销已经发生的网络或容器变更。
已登记的本地安全回退仍允许完成。
回退范围和期限在原 plan 中固定，不能扩大。
策略到期同样停止新步骤，不自动续期。
到期前 14/3/1 天提醒；过期有等待任务时再提醒一次。
续签页逐字段显示旧值、新值、方向、资产/制品差异和执行统计。
展示最终签名字节的摘要；批量续签逐项绑定摘要，不能签隐藏扩权。
规则签发前必须通过 S2 告警、周报骨架和存活检测验收。

## 4. 执行器与主机边界

### 4.1 架构选项

下表九项选择均为 Owner 已定，本轮保留原选择。
表中的其他选项仅保留决策背景，不重新投票。
以下安全约束收紧所选方案，不新增架构选择。

| 架构点 | 选项 A | 选项 B | 选项 C | 推荐与理由 |
|---|---|---|---|---|
| 执行器位置 | platform 集群 Pod；易部署，随集群故障 | mini `.50` 独立账户；带外可达 | agent-06；与任务共宿主 | B；符合 ADR §3 与 W-50 |
| 钥匙与提权 | 一把通用节点钥匙；影响全部主机 | 每主机/环境独立钥匙，forced-command 与受限 sudo | SSH CA 短证书；新增签发服务 | B；可单机吊销，不新增 CA |
| 调度传输 | platform SSH 推送；API 持节点钥匙 | mini 用 executor 身份主动领单 | 新消息总线与 runner 协议 | B；复用 claim/renew/result |
| 策略与账本 | agentrt PG 存全部；修复依赖 PG | statefile 修复链；PG 只收可重建展示事件 | mini 自建另一套审批真相 | B；符合 ADR §12.3 |
| 执行实现 | shell 文本匹配 | 版本化具名 helper，固定 argv | Ansible 控制器 | B；规模小；W-68 已将 Ansible 延后 |
| UniFi 范围 | 原 D 动作整体改 B | 新节点窄入口复用现有实现 | 永远逐次批全部 IP 修复 | B；满足新决定，保留其余 D |
| 高可用 | `.50` 单写，`.52` 看守 | 双机抢单，远端 fencing 后接管 | 两边各自离线执行 | 先 A，完成 fencing 后 B；拒绝 C |
| 断平台处理 | 不启新写，完成本地安全回退 | mini 独立授权应急子集 | 无期限缓存授权继续写 | 先 A；B 单独切片设计，不采用 C |
| 自动授权接线 | 放宽 `owner_run_command` | 新 host 动作与专用 policy gate | 给 Agent admin 身份 | B；不能从任意 shell 获得自动授权 |

mini 执行器是确定性程序，不运行模型、仓库测试或 Agent CLI。
持节点钥匙的 `.50` 整机不得运行 LLM 或 Agent 进程。
不能仅靠不同账户宣称隔离；参谋长可在无节点钥匙的 `.52`。
若 `.50` 已有模型进程，S3 安装钥匙前必须完成迁出验收。
这是执行器位置 B 的启用约束，不改变 mini 放置决定。
账户 `bifrost-host-exec` 与 operator-plane 分开。
operator-plane 只转交元数据，不直接加载私钥。
源码及候选包可随同一平台制品构建；普通平台发布不得安装或覆盖执行器。
执行器安装和升级只走 §6.2 的 Owner 独立维护入口，运行权限仍隔离。
首片没有自动跨 mini 接管，也不复制节点私钥给 `.52`。

平台不可用时，已启动动作按本地 plan 完成或回退。
未启动步骤不凭缓存继续执行。
因此首片不提供“平台全停仍自动修平台”的能力。
应急仍由 Owner 经 mini 本地入口处理。
这一限制必须显示在 Console，不能写成完全自治。

### 4.2 凭证与确定性执行

Owner 在执行器账户安装专用节点钥匙。
每把钥匙只对应一台主机及一个受限账户。
远端 `authorized_keys` 固定 `command` 和来源地址。
禁止 PTY、端口转发、agent forwarding、用户 rc。
固定 host key 校验失败就拒绝，不自动接受新指纹。
NAS 的 UGOS 强制命令机制必须单独验兼容性。

远端只运行 root 所有的 `bifrost-host-action` helper。
非特权账户不加入 docker/admin 组。
sudoers 只允许这个固定 helper，不允许 shell、编辑器或任意 systemctl。
helper 再检查动作、参数、资产、摘要和授权票据。
票据签名私钥只在 `.50` 执行器账户，不在 platform Pod。
平台提交候选授权；执行器自己复核后才能签发。
M 在执行器重新匹配完整策略、收紧链、冻结、限额和本地登记。
helper 再独立验证，不能只相信平台或执行器报出的层级。

H 必须携带 Owner 对 `plan_hash` 的 SSHSIG。
签名域为 `bifrost-host-ops-approval`；普通 admin 批准记录不足以执行。
Console/手机展示最终计划，再由 Owner 控制的签名端签署。
签名私钥不传给 API、执行器或 Agent；缺签名端就保持待批。
不以 admin bearer token 或“已批准”字段代签。
plan 使用固定 schema 的规范编码，拒绝重复键和未知字段。
hash 覆盖 action、参数、目标身份/环境、前态和全部制品字节摘要。
同时绑定 inventory、catalog 和 handler_digest，不能换执行实现。
还覆盖 execution/approval ID、一次性 nonce、期限、executor、回退及锁范围。
任何变更都重做 plan 并重新签名，不能复用旧批准。
执行器及 helper 都验证 Owner 签名、nonce 未消费和前态未变。
H 仍受本机预装能力和 X 边界限制，不能扩展 helper 权限。

### 4.2.1 Owner 签名端的准入边界

S3 必须交付并独立验收签名端，不能以旧 O9 操作单或“私钥不可读”代替。
签名程序、依赖、配置及更新入口不得由 Agent、平台普通部署或待签仓库脚本改写。
Owner 经受保护的独立更新入口逐次批准签名端版本/摘要；初装和恢复见 §6.2。
签名端自己严格解析规范 plan、计算 hash，并从**同一不可变对象**渲染确认内容再签署。
必须显示动作、规范目标身份、环境、前态、制品/实现摘要、有效期、执行 ID、回退及锁范围。
不签调用者直接提供的裸 hash；理由、日志、线程文字均标为非授权文本，不解释为指令。
Console/手机页面只是候选 plan 的传输入口，不能代替签名端的可信确认画面。
确认期间对象、版本或字节变化，作废本次确认，重新展示并要求 Owner 本人确认。

每份 plan 都要 Owner 在可信签名端主动确认；一次解锁不授权后续静默签名。
Agent 不能借已解锁 ssh-agent/钥匙串、签名 socket、本地 IPC 或浏览器接口调用签名能力。
远端禁用 agent forwarding 不是这项本地隔离的证据。
S3 以 Agent 身份覆盖上述入口、伪造点击/跨源请求、重放确认、显示 A 送签 B、确认后替换字节；
均须无签名产出，且 Owner 正常确认的同一规范对象可被执行器/helper 独立验签。
同一展示与字节绑定要求适用于策略、登记、manifest、解冻和 resolve 的签名。
缺少满足这些要求的签名端，H 保持待批，生产 M 策略也不签发。

### 4.2.2 执行票据与调用隔离

票据绑定 plan_hash、目标、环境、executor、有效期、freeze epoch 和 fencing generation。
M 附完整签名策略及收紧链；H 附上述 Owner 签名。
冻结、过期、未知 helper 或 handler_digest 不匹配均拒绝。
远端只持验签公钥，不持 Owner 的签名私钥。
这把执行票据钥匙须独立安装并逐次批准轮换。
helper 安装/升级本身是 `host_access_change`，不能靠 M 更新自己。
安装新 helper 后，旧 handler_digest 条款不得继续运行。

传输只发送严格 JSON 和制品字节，不拼接命令字符串。
helper 使用固定 argv、干净环境和固定 PATH。
不继承请求者的环境、SSH 配置或 Git 配置。
源码、unit、compose、回退文件及所有父目录不可由 Agent 修改。
路径逐层验证且禁止符号链接穿越。
写前重新核对 inode、属主与摘要，避免检查后被替换。
制品按 §3.2 的签名 manifest 验证，不能只接受调用方给的哈希。

Agent 仅持请求/只读身份，不持 executor 身份。
mini 私钥目录 0700、文件 0600，不挂进 Agent 环境。
执行器不提供读文件、读环境或任意 SSH 工具。
agent-06 的现有出站规则继续拒绝 SSH、NAS 和 UniFi。
本机进程隔离与网络限制必须实测，不能仅靠提示词。
STG 只接测试主机身份，不能领 PROD 的真实节点单。

executor token 在服务端绑定 `executor_id + environment + host_ids`。
claim 只返回该身份在签名登记范围内的 `host_*` 动作。
renew/result 也绑定原执行器、lease 和目标，不能跨单报结果。
host claim/renew/result 明确排除 `RoleAdmin` 的角色继承捷径。
Owner 签名是 H 执行授权，仍不能替代 executor 身份领单。
S2 即在 PROD 拒绝 `owner_run_command(runner=host)`。
已有排队的自由 shell 单同样拒领并记原因，不留迁移后门。
其他 `platform_*`、credential 动作保留原专用执行链。
本设计的 `host_*` executor 不接管它们。

### 4.2.3 系统适配与前态

| 系统 | 固定适配与准入验收 |
|---|---|
| Linux | systemd、固定 sudo helper；断线进程组和本地 watchdog 演练 |
| macOS | launchctl 固定 domain/label；用专用非 Agent 用户加载；保存 plist、loaded/disabled/running 前态 |
| UGOS | 单验 forced-command、sudo 路径、Docker socket 隔离、NAS 文件权限；失败则该主机不准入 |

受管 mini 的 helper 不能管理本机执行器；`.50` 自维护仍由 Owner 做。
NAS 离线镜像在受保护目录暂存，验证归档字节及 OCI digest 后 load。
不透传 Docker socket，不隐含从公网拉镜像。
前态快照先持久化，再签 plan 和开始写入。
包括文件摘要/权限、镜像、挂载、enabled/running 状态及依赖。
快照不可读取 Secret 内容，只保存受控引用。
回退按快照恢复；验证 disable 后恢复原 enabled 与 running 状态。
没有可用前态、旧制品或足够空间，就不执行 M。
有状态项目的数据恢复单独验证，配置快照不替代数据备份。

执行器和 helper 都检查 NTP 同步状态及最近成功同步时间。
签票与验票要求同步观测不超过 5 分钟，绝对偏差不超过 5 秒。
未知 NTP、时钟回拨或超过阈值，拒绝新写并报警。
租约、watchdog 用单调时钟；R 只能提供受限诊断，不签写票据。

### 4.3 执行、超时与并发

`global_writes=1` 是可调度活动槽的上限，每台主机最多一个可调度写动作。
它不保证物理上永远只有一个有副作用的进程：unknown 的旧进程可能尚未停止。
R 并发最多四个；网络变更和演练全局串行。
主机维护还锁住依赖项目及对应发布窗口。
窗口和资源锁不是授权，不能代替策略。

| 阶段 | 约束 |
|---|---|
| 领单 | 复用 60 秒 lease、20 秒续租；队列最长 24 小时 |
| 开始 | 先落本地 journal，再发远端命令；票据 TTL 不超过 60 秒 |
| 检查 | 默认 30 秒；目录容量扫描最多 120 秒 |
| 常规写 | 重启 120 秒；compose 300 秒；安装 900 秒；join 1200 秒 |
| 网络变更 | 本地 watchdog 120 秒；新旧地址双探测成功才取消回退 |
| 失败 | 最多一次预授权回退；回退失败冻结该 host/action 并推送 |
| 断线 | 结果未知则 `unknown`；只重传结果，不自动重跑写操作 |

远端 journal 以 `execution_id + step_id` 去重。
远端锁保存 fencing generation，拒绝旧 generation。
同一执行票据重放只返回已存结果。
超时先终止登记进程组，再查真实状态。
SSH 断开不等于远端已经停止。
租约丢失后不再开启新步骤，不能据此立即派另一执行器。
现有 10 分钟 unknown grace 仅用于状态归档。
安全停止不能等待这 10 分钟。

幂等性必须逐动作证明。
只有确认“副作用尚未开始”才能按退避重试。
失联后仍在运行、写后读回失败，均不得自动重试。
`unknown` 只锁该主机及签名登记中的依赖，不冻结无关主机。
依赖闭包必须包括会受本动作影响的共享存储、网络路径/设备、平台修复账本及发布依赖，不能只列服务名。
只作为正常传输或只读检查使用的公共设施不因此被锁成全局依赖；确实承载受影响账本则停全部新写。
执行前将这个闭包固定进 plan；隔离锁继承整个闭包，既有共享资源锁不能随全局槽释放。
若依赖证据不完整，就不准入该动作；事故后无法确定隔离范围时保持原槽并升级给 Owner。
登记该主机及依赖的隔离锁后释放全局调度槽；无关请求可继续。
该锁隔离的是调度范围，不声称旧进程已经停止。
`host_execution_resolve` 收集 journal、进程、前后态和 fencing 证据。
它在原执行记录的锁内对账，不新领目标写锁，也不执行主机副作用。
Owner 签 resolve plan 后才能关闭 unknown；普通 admin resolve 不足够。
证明完成或未开始后才释放资源锁；结果仍不明就继续锁定。
若无法证明旧进程已停，须先完成逐次批准的隔离，不能强制解锁重跑。
resolve 只改执行状态；补救或重做是新 action、新授权。
结果晚到可按原 lease 接收一次。
本地 journal 重启后继续补传；平台确认仅允许按 §5.2 回收输出，不清除防重放墓碑和高水位。

### 4.4 目标主机在操作中失效

故障样例采用 2026-10-25 的 NVMe 掉盘：主机挂起、ping 仍通、SSH 重置。
这是需求提供的情景，未查询现场，不推断具体节点或当前修复状态。
ping 仅证明一部分网络栈可回应，不能证明 SSH、helper、磁盘、账本或服务健康。

| 失效点 | 判定、停止与恢复边界 |
|---|---|
| 副作用前不能持久化 intent/nonce/步骤记录 | 不发起该副作用；若其他端已有开始记录或无法证明未开始，保持 unknown |
| 命令已发出后 SSH reset、超时、挂起或写后读回失败 | 标 unknown，撤销后续步骤许可；不重跑、不靠重连或 lease 到期推断命令已停止 |
| 目标 watchdog、回退或终止进程组也无法运行 | 在存活端记录回退未证实、保留隔离锁并报警；不承诺物理掉盘可以自动回退 |
| 故障目标承载平台 API 或修复 statefile | `.50` 不能获得新许可就停止新写；仅已授权且仍可运行的安全停止/固定本地回退继续 |
| 只有 PG/Redis 展示或通知投影失效 | 独立 statefile、API、锁和通知健康证明仍满足全部条件才可继续；不以 ping 或缓存票据替代验证 |
| `.50` 自身丢盘或停机 | 停全部新 host 写；`.52`/平台独立报警，`.52` 无钥匙且不自动接管；恢复见 §5.2 |

存活端保留最后确认的步骤、时间、plan/制品摘要、lease/fencing、持久化回执和缺失的证据。
故障通知附受影响主机、依赖隔离范围、unknown 和回退未证实状态，走 S2 独立故障路径。
本地回退也只在目标还能执行、已固定的范围/期限内尝试一次；不能隐含重启或断电自救。
硬件检查、更换磁盘和物理电源处置交 Owner；不得把另一次高风险修复算作原 M 的重试。
SSH 恢复后只做受限诊断及结果对账；旧票据、旧许可和自动启动恢复逻辑都不能开启下一步。
重装后 host key 或安全状态变化须隔离重建信任，不能自动接受新身份或从空账本继续。
Owner 签 resolve 之前须证明旧进程已停或已可靠隔离，并核对实际后态；证据不足继续 unknown。
如需另一次修复，按既有 H/Owner 独立入口给出新 plan、新授权；不增加离线自主授权。

S2/S3 必须在可丢弃测试环境注入“写后断线但进程仍活”“ping 活而 SSH reset”、
journal fsync 失败及目标不可执行 watchdog；禁止为验收在生产拔盘。
S3/S4 再验 A 主机 unknown 后 B 无关主机可继续，C 共享存储/网络/发布依赖被挡，
A 恢复后旧许可仍不能启动下一步；按实际执行范围在 S5/S6 复验网络及 UGOS 适配。
每项都须保存通知、隔离锁、无重复副作用及恢复对账证据，缺证据不得开放对应动作。

## 5. 审计、线程回传与通知

每一步先写意图，再写开始和结果。
审计写不进去，下一步不执行。
平台丢 PG/Redis 不影响 host 修复账本。
statefile 损坏或磁盘满时停止新写。

| 记录块 | 必须保存 |
|---|---|
| 请求 | `request_id`、`execution_id`、认证主体、线程、`work_id`、环境 |
| 授权 | 层级、策略 ID/版本/哈希、条款、签名指纹、freeze epoch；或 approval ID |
| 目标 | host ID/指纹、资源 ID/UID、生命周期、配置前态、`params_hash`、`plan_hash` |
| 执行 | helper/bundle digest、步骤、executor 主体、lease、fencing generation、起止时间 |
| 结果 | exit code、耗时、后态、回退结果、错误分类、脱敏输出摘要及哈希 |
| 投递 | 线程事件 ID、周报周期、提醒种类、目标、accepted/failed/skipped |

拒绝也落审计：过期、冻结、未知 helper、未覆盖、签名和摘要不符。
记录稳定 reason code、认证主体、请求哈希及可安全保存的目标。
不保存恶意请求的原始敏感参数；审计不可写时仍拒绝并报存储故障。
H 授权记录另存 Owner 签名及签名端指纹，不能只存 approval ID。
登记、manifest、前态快照、签发票据和生效版本的摘要全部关联。

沿用 W-50：平台保存不超过 2 KiB 的脱敏尾部。
全文先脱敏后保存，留 `.50` 30 天，设容量上限。
隐藏字符或无法安全脱敏的段落整段抑制。
输出哈希针对实际保存的脱敏字节。
凭证值、环境、敏感备份内容不采集。
受限只读输出也执行同样处理。

新增持久审计归档保留至少 180 天。
不能只依赖现有 500 条闭单与 50 条尾部。
归档前不得清掉未汇总事件；清理不得删开放或 unknown 记录。
事件通过 outbox 回到原线程和工作项。
只读阶段完成证据由事件驱动，不要求 Owner 回复“好了”。
线程离线时保留待投递事件，恢复后按游标读取。
审计以序号及前项哈希串联，周报引用截止序号和链头。
每小时及每次生成摘要时，将链头 fsync 到 `.50` 本地存储。
同时把链头交平台和 `.52` 留存，检测截断及不一致。
`.50` 本地副本防平台记录丢失，不宣称能抵抗三处同时被改。
这是周期归档检查点；每次副作用前的安全状态持久化按 §5.2 执行，不能等一小时。

每周一 09:00 Chicago 生成一份 Console 周报。
含成功次数、主机、条款、回退、失败、unknown 和减少的逐次审批数。
还显示操作耗时、Owner 决定数及最常见拒绝原因。
成功不单独推手机；周报可查，不额外发送成功推送。
网络、join、fixed-IP、agentd 更新成功立即有 Console 记录。
这些成功还进入每日摘要，不能等一周才看见变更。
`host_git_endpoint_set` 逐次列入每日、每周摘要，不仅给聚合次数。
失败、unknown、回退失败才立即推；同事件去重。
存活失效、反复成功熔断及摘要失约同属故障通知。
审批需求、冻结和续签提醒是治理通知，照常发送。
推送失败持久重试，不能把 accepted 写成手机已收到。
S2 必须提供不经过 `.50` 的故障投递路径，不等待其他项目。

### 5.1 独立存活与死人开关

| 检测方 | 信号及初始阈值 | 故障路径 |
|---|---|---|
| platform | executor 每 20 秒心跳；TTL 60 秒；含进度及最后 journal 序号 | 直接投 `.52` 独立 relay；不能经 `.50` 转发 |
| platform | 最老可执行请求等待超过 5 分钟；审批等待另计 | Console 标积压，并经 `.52` 推送 |
| `.52` watchdog | 直探 `.50` executor 和平台心跳；连续 60 秒缺失 | 本机持久 outbox 直接投现有通知提供方 |
| `.52` watchdog | 每周一 09:15 仍未收到当前周期摘要及截止游标 | 推 `digest_missing`；零执行周也必须有空摘要 |
| platform | `.52` relay/watchdog 60 秒失联，或投递持续失败 5 分钟 | 直投通知提供方，报警独立路径损坏 |

`.52` 的 watchdog、relay 无节点钥匙，不具备执行能力。
它们不依赖 `.50` 的进程、存储、代理或通知凭证。
平台直投所需的通知身份也独立安装，不能经 `.50` 获取。
复用现有通知提供方，不新增外部服务。
失联消息从检测到提交提供方不超过 3 分钟。
通知链路健康证明过期时停止签发新的 M 票据，原定回退可完成。
不能把可发送等同于手机已阅读；投递状态明确区分。
S2 做 `.50` 断电、平台断开、relay 停机和摘要漏发的故障注入。
须看到独立通道送达证据，再允许生产策略签名。
平台及两台 mini 同时断网仍可能无法送达，记录为剩余故障域。

### 5.2 安全状态的权限、持久化与恢复

下表为实施必须采用的专用路径和写入主体，不表示这些目录已创建。
Linux 根为 `/var/lib/bifrost-host-ops`；macOS 根为 `/Library/Application Support/Bifrost/HostOps`。
根及所有父目录归 root、Agent 不可写；子目录不放在仓库、Agent home 或共享临时目录。
平台使用该 Linux 根的独立持久卷，挂载及权限由 Owner 操作包安装，不依赖 PG。

| 位置 / 子目录 | 必须持久保存 | 属主、读写主体 |
|---|---|---|
| 平台 `platform/` | 完整策略/收紧链/墓碑、版本与 freeze epoch、授权/nonce 绑定、额度预占、lease/fencing、资源及 unknown 锁、审计/outbox | 专用平台修复链服务 UID，目录 0700、文件 0600；只该服务和 root 可读写 |
| `.50` `executor/` | 本地 stop、策略/epoch/fencing 高水位、nonce 消费、quota、执行/步骤 journal、前态/回执、审计链及补传 outbox | `bifrost-host-exec`，0700/0600；只执行器和 root 可读写；本地 stop 由 root 受限停写入口更新 |
| 目标 `helper/` | 目标身份 generation、策略/epoch/fencing 高水位、nonce/execution 绑定、步骤去重、锁、生命周期、前态、回退和结果 | root，0700/0600；只固定提权 helper 和 Owner 维护入口可读写，SSH 受限账户不能直接读写 |
| `.52` `watchdog/` | 独立心跳观察、审计链头/高水位见证、告警去重及 outbox；无执行票据或节点私钥 | 独立 `bifrost-host-watch` UID，0700/0600；只 watchdog/relay 和 root 可读写，不与 Agent 共用 UID |
| 各端 `trust/` | 签名基线、登记、manifest、公钥及安装版本锚 | root 安装且父目录不可写；只获准服务可读、不可自更新，写入只走 Owner 安装器 |

状态写者必须由固定程序实现；Agent 不能以同 UID、组权限、ACL、调试/备份接口读写原始记录。
平台仅经鉴权接口返回脱敏投影；有申请和冻结权限不等于可直接改 statefile。
文件创建/打开禁止链接替换和路径穿越；校验父目录、属主、权限及文件身份，原子替换后复核。
安装器还须拒绝硬链接/共享可写文件，备份和恢复副本沿用同样私有权限。
审计归档、journal、nonce 与 outbox 都在这些私有目录；输出脱敏不等于可以公开原始账本。

副作用前：平台原子持久化授权/额度/锁；`.50` 原子持久化 nonce 绑定及执行意图后才能签票；
目标 helper 原子持久化相同 nonce/execution 绑定、步骤 intent、fencing 与锁后才能运行命令。
每次事务都须完成 WAL/文件 fsync，替换文件时还须 fsync 父目录；收到成功回执才进入下一步。
任何一端写失败、回执丢失或状态有歧义，就拒绝后续副作用；已可能执行的步骤留 unknown。
nonce 一次性绑定整份 plan/execution；同 plan 的后续步骤仍要顺序、去重及新鲜许可，
重复请求只能查原执行状态，不能因 nonce 已绑定而再次启动第一步。
每个结果/锁变化及审计事件也同步持久化；不能以平台收到结果代替目标端落盘。

回收区分输出与授权状态：确认接收后，输出按 30 天容量策略、审计按至少 180 天归档策略回收。
H 消费墓碑至少保留到批准有效期结束加允许时钟容差（当前 5 秒），且执行/回退/unknown 已全部结清，
相关票据已过期、结果与审计已持久归档；条件不齐就继续保留，不能受 500 条闭单上限驱逐。
开放/unknown journal 不回收；终态 journal 可压缩为 execution/plan/nonce/步骤结果摘要的去重墓碑。
旧请求在墓碑回收后仍须被期限和 generation 检查拒绝，绝不能作为新授权执行。
策略限制墓碑、最大版本/epoch/fencing/身份 generation 及额度历史不因输出清理或换版本而重置。
限制墓碑只有 Owner 明确新签替换后才能归档；仍有效的拒绝语义必须留在完整策略集中。

启动或恢复备份先保持冻结，核对本地链与其他存活端保存的链头、generation 和高水位。
发现截断、旧副本、缺失账本或无法独立证明状态新鲜，就进入隔离恢复，禁止空账本开放写入。
周期链头无法证明其后所有消费记录未丢；存在这类缺口的执行一律按 unknown 保留隔离。
恢复必须由 Owner 独立维护入口核对未结操作、隔离旧进程，并签更高恢复 generation/最小策略版本，
拒绝旧 generation 的计划、票据和许可；身份/钥匙受损时同时重建信任，再单独签解冻。
不能以签恢复记录清除未知副作用；没有隔离证据仍不释放相关资源。
三端同时回滚且无可信新鲜见证时不声称自动检测成功，只能停写并由 Owner 重建。

S1 定义事务/保留及恢复协议；S2 验平台、`.52` 与审计/outbox；S3 验 `.50` 和目标权限、重启恢复。
各端用 Agent 身份实测读取、覆盖、删除、链接替换 journal/nonce/高水位/审计均被拒绝。
故障测试覆盖：已开始无结果、确认后清理、进程崩溃重启、持久化各边界掉电及恢复旧状态副本。
重放只能返回既有结果/unknown 或因过期拒绝；无条件都不得重复副作用，缺状态必须冻结。
上述安全状态证据缺一项，S4 不得签首版生产 M 策略。

## 6. 切片、估算与 Owner 的动作

估算为实施、自检、独立复核和返工的合计人日。
不含等待签名、硬件窗口和观察期的日历时间。
每片预算两轮复核；签名协议和首次 M 预算三轮。
复核仍有阻断项就不准入；超预算重新估算，不能压缩验收。

| 切片 | 交付与验收门槛 | 实施/自检 + 复核/返工 = 人日 | Owner 必须做 |
|---|---|---|---|
| S1 信任制品与规则 | 登记和 bundle 的签名流；字段方向/property tests；版本、冻结、never-M、H plan 协议；三轮复核 | 3–3.5 + 1–1.5 = 4–5 | 审阅候选范围；此时不签生产策略 |
| S2 调度、审计与告警 | 身份/环境隔离、host-only claim、拒绝 shell、statefile/outbox；失败/unknown 推送、周报骨架、独立心跳与 dead-man；两轮复核 | 3.5–5 + 1.5–2 = 5–7 | 安装独立通知身份；批准所需部署；验独立路径 |
| S3 执行器与 R | `.50` 无 Agent；Linux/macOS helper、launchctl、签名票据、Owner H 签名端；前态快照；unknown resolve；七个 R；两轮复核 | 3.5–5 + 1.5–2 = 5–7 | H 引导钥匙/sudoers/helper/锚；提供可丢弃 Linux 测试机与 macOS 测试账户；约 2–3 小时 |
| S4 首批 M 闭环 | 下列七动作；拆二进制更新；单步撤销、回退、次数/熔断；Console scope diff；三轮复核 | 3.5–5 + 1.5–2 = 5–7 | 签登记及 manifest，签首版策略；约 30–60 分钟；先验 S1–S3 |
| S7 首轮观察 | 首批范围合盖一夜；七天观察；审计完整、零手贴命令、故障可见；两次证据复核 | 0.5–1 + 0.5–1 = 1–2，另 7 天观察 | 看周报；不逐项签成功 |
| S5 后续网络与接入 | netplan、join 原子生命周期、fixed-IP/VIP/DHCP 恢复；测试机拔网故障；三轮复核 | 4–6 + 2–3 = 6–9 | 登记新机、join credential；批测试准备；单独签扩展范围 |
| S6a 后续 H 与展示 | 其余 host H 模板、逐动作恢复演练、完整日报/周报与审批下钻；两轮复核 | 2–3.5 + 1–1.5 = 3–5 | 签测试环境高风险 plan；独立维护执行器 |
| S6b 后续适配与动作 | UGOS helper、NAS 离线镜像；工具链、验证、清理、生命周期、Git 端点、监控演练；两轮复核 | 3.5–5.5 + 1.5–2.5 = 5–8 | NAS 准入、签包与策略扩展；无准入不自动 |

执行顺序为 S1→S2→S3→S4→S7，再做 S5、S6a、S6b。
S5 明确拆为后续切片，不拖入首轮承诺。
S1–S4 合计 19–26 人日；含 S7 为 20–28 人日。
全部上述切片合计 34–50 人日，另加七天观察及硬件等待。
原 13–19 人日撤回；不能再用零点几天估算完整动作适配。

首轮七个 M 为 service_restart、service_state、container_restart、compose_reconcile。
另含 monitoring_install、monitoring_remove、agentd_update，均为 `host_` 动作。
只在登记准入的 Linux/macOS 目标开放；compose 仅限无状态项目。
macOS 没有经过准入的容器运行时，就不开放容器动作。
首轮不开放网络、join、fixed-IP、清理、工具链或 UGOS 写动作。
未实现模板返回 unsupported，不借用自由 shell 填空。
S3 的 H 只做信任引导和 resolve；其他破坏性 helper 暂不安装。
S6a 才扩展 H 模板；Owner plan 验签机制已在 S1–S3 完成。
S2 用测试信任锚和合成事件验收，不签生产 M 策略。
S4 签发门槛包含 S2 故障投递证据及 S3 真实断线测试。
scope diff 页、摘要骨架和每日关键变更记录不能后移到 S6。
把握中等偏低；签名端、macOS/UGOS 限权和故障恢复风险最大。
七动作以外仍可能需要人工；全局每周少于 40 次只是观察指标。
只有完整范围实测达到该指标，才能宣布 WORK 4.7 全部完成。
所有运行时发布继续遵守原发布规则。
新接口、策略状态和票据协议随各片独立复核。
本次只交设计，不启任何切片。

首次凭证引导不能自动完成。
Owner 配置节点钥匙、sudoers、执行器身份和公钥锚。
初装 helper/登记由 Owner 独立入口完成，不借尚未可信的执行器自举。
Owner 私钥、管理员 kubeconfig 不迁入执行器。
已有 host credential 的受限使用不等于 Secret 变更。
后续新增主机权限、轮换凭证、续签或扩权仍需 Owner。
把这些合并成准备完整的操作包，避免来回追问参数。

### 6.0 S1 超预算重估（2026-10-26 · Work 601）

S1 原三轮预算已在 Work 598 用尽，B2 需要范围 schema 决策，不能把本次修复算作原预算内完成。
协调已选择方案 A，本次只继续 S1：额外实施/自检 1.5–2.5 人日，独立复核/返工 1–1.5 人日，
合计追加 2.5–4 人日；S1 规划累计由 4–5 调整为 **6.5–9 人日**。
S1–S4 调整为 21.5–30 人日，含 S7 为 22.5–32，全部切片为 36.5–54 人日，
仍另计七天观察和等待。这是剩余范围的规划重估，不是本轮实耗统计。
本修订后安排一次独立复核并预留一次返工复核；若仍有 B 项，保持未准入并再次重估，
不得删验收或自动推进 S2。Work 601 的代码、自检与报告交付不代替独立签收。

#### Work 606 · Review 604 后再估算

Review 604 仍发现 B1，S1 保持未准入。本次限定于制品选择绑定及回归，
追加实施/自检 0.5–1 人日、独立复核/返工 0.5–1 人日，合计 **1–2 人日**。
S1 累计规划调整为 **7.5–11 人日**；S1–S4 为 22.5–32，含 S7 为 23.5–34，
全部切片为 37.5–56 人日，仍另计七天观察和等待。这是规划重估，不是实际耗时。
本次自检完成仅可送独立复核；若再有 B，继续保持未准入并重估，不自动启动 S2。
Review 604 没有新增独立 C 代码缺陷；§6.1 的时钟/私有账本、CAS/断电恢复、权限拒绝、
签名端隔离及生产拒装测试锚等运行时门槛原样保留，不以本轮测试代替。

### 6.1 复核 573 的切片准入补充

下列是各片完成的必要条件，不能以本设计修订、单元测试模型或旧操作单替代运行时证据。
估算仍是 §6 的规划区间；实施者必须把这些验收纳入预算，超出则重估，不删门槛。

| 切片 | 必须交付的证据 |
|---|---|
| S1 | §3.1/3.3 完整策略参考模型、两层交集、拒绝墓碑和三端共用测试向量；同历史下授权子集；§5.2 状态协议；下表 D10 全矩阵的契约测试 |
| S2 | §5.2 平台/`.52` 私有状态、原子落盘、恢复旧副本拒绝和 Agent 权限拒绝；§4.4 故障事件/依赖锁/独立通知；unknown 释放槽不释放依赖锁 |
| S3 | §4.2.1 签名端防借签和 A/B 替换；§5.2 执行器/helper 断电、墓碑回收和恢复测试；§6.2 新操作包；真实 SSH 断线及模拟磁盘不可写；D10 在 helper 再拒绝 |
| S4 | 首批七动作端到端复验 D10、签名/权限/重放；A unknown、B 无关继续、C 共享依赖被挡；旧许可不能恢复；S1–S3 证据齐全后才签策略 |
| S5/S6 | 新增网络、UGOS、H 或 bundle 适配逐个复用上述拒绝及故障矩阵；尚未测试的动作不准入 |

D10 检查在策略匹配和 H 验签**之外**强制执行：平台 gate、执行器和 helper 各自拒绝，
同时核对请求及实际安装/回退的最终效果；有效 Owner H 签名也不能解锁。
服务身份和别名复用 [AGENT_FACTS §8a](../../AGENT_FACTS.md) 与其所指运行时映射，
包括 `daemon`、`bifrost-engine(.service)`、`trading_engine`；不另造仅按 action 名判断的清单。
通用 platform 入口沿用原 D10 闸门，host 路由不能接手它们来绕过。

| 入口/载体 | D10 BLOCKED 时必须拒绝的样例 |
|---|---|
| service restart/state，规范名及别名 | 启动或重启成实盘执行模式；不能借别名变成普通服务 |
| container/compose，配置或副本数 | 拉起交易执行容器、增加 daemon 执行副本、将 observe 配置改为实盘发单 |
| monitoring/agentd/toolchain/validation 安装 bundle | 借包内 unit、启动项、脚本或镜像启用上述执行，或移除冻结护栏 |
| rollback/旧 bundle/恢复前态 | 回退到含实盘启用、执行扩容或护栏删除的旧制品；“恢复”不是豁免 |
| H access/manifest/runbook 与有效 H 签名 | 改冻结 overlay、执行配置或接线以启用真实发单；签名不能覆盖 X |

测试还包括允许的已登记只读状态/日志及纯观测制品作阳性对照，防止错误封禁全部观测。
无法解析目标身份或包的作用范围就拒绝准入；无执行效果证明的包不能因名字像监控而通过。
以上是运行时应实现的检查，不是本次修改 guard 或放开交易的授权。

### 6.2 S3 必须交付的 Owner 引导与更新操作包

§6 当前列的是责任和顺序，不是已可照抄执行的操作单。S3 必须新增本执行器专用操作包，
在独立复核及可丢弃主机演练通过前不安装生产钥匙、不签生产策略。
O2/O9/O13 仅为输入资料，不能代替该操作包；本轮不虚构未实现的安装命令。

操作包分 Owner 本机/可信签名设备、`.50`、`.52` 和每个 Linux/macOS 目标四部分，必须包含：

1. 固定版本、制品 SHA-256、Owner 签名、公钥指纹和离线验签命令；明确输入值、执行用户及主机，不能用 latest 或仓库工作树脚本。
2. 安装前检查 `.50` 整机无 Agent、身份/host key、私有目录及所有父目录权限、磁盘和时钟；给出通过输出与失败即停条件。
3. 逐条可执行的账户、forced-command、来源限制、sudoers、SSH host key 校验、服务配置及 §5.2 文件目的地/权限安装命令；附非特权和 Agent 身份拒绝测试。
4. 签名端安装和独立更新入口，以及防借签验收；初始登记/manifest/策略签发、H plan 展示验签和无效签名拒绝的完整步骤与预期输出。
5. 本地 stop-writes、冻结/解冻、unknown 对账、坏盘/旧副本隔离恢复、升级失败恢复和卸载步骤；每步说明保留哪些日志、墓碑、锁、凭证撤销证据。
6. 失败前后均核对文件摘要和服务状态；失败保持停写，不自动恢复旧安全状态。卸载先停派/排空或隔离 unknown，撤销身份，保留安全记录后才清除程序。

`.50` 自维护入口必须是 Owner 在可信本地控制台调用的受保护独立安装器，不经过 host executor 自更新。
安装器及其更新入口、依赖归 root 且 Agent/平台普通部署不可写；每次安装/升级都验证
Owner 对目标主机、版本、制品摘要、前态及恢复范围的本次授权，并记录安装回执和单调版本。
保护范围包括执行器二进制、启动配置、运行库、helper/票据信任配置及安装器自身；
普通平台发布、M bundle 或执行器运行账户都不能覆盖，不能靠同时构建就获得安装权限。
失败回退只能用本次授权且仍满足安全版本下限的制品，不回滚 nonce/epoch/fencing/锁。
权限和恢复验收需实测普通平台发布及 M 更新不能写这些文件，Owner 独立入口可完成经签版本更新。
平台全停时该入口仍只由 Owner 维护，不增加 `.50` 的离线自动授权或 `.52` 自动接管。

### 6.3 待 Owner 定

本轮没有需要改变 §4.1 九项已定选择的修复，九行选择保持原文。
签名端隔离、持久化和独立安装器是既定方案的准入条件，本设计不以它们为由重开选型。
未来若实现发现必须改变九项中的任一项，先在此列 2–3 个选项及推荐，Owner 定前保持该片未准入。

### 6.4 S1 复核 590 修订（2026-10-26 · Work 592）

本补充落实 B1–B4、C1/C2，不改变 §4.1 九项选择，不授权生产安装或签发。
S1 候选接口增加必填熔断账本和本地时钟观测；尚无运行时消费者。

- 普通解冻复用准入的状态完整性校验，仅不检查 stop 标志；版本高水位为零、
  epoch 不一致、恢复 generation 与签名不符、熔断账本缺失均拒绝，不能以解冻补状态。
- §3.3/§5.2 的熔断按 **environment/host/action** 持久锁存，记录单调 trip、
  证据摘要及已签解除的 execution ID 墓碑。成功结果与锁存、审计、通知 outbox 同事务
  CAS/fsync；冻结期间仍记录。策略变更同事务核对受影响目标历史，改名、版本、
  阈值放宽、窗口流逝、输出清理及重启都不清锁存。所有未解除成功的历史窗口仍参与检测。
- 专用签名域 `bifrost-host-ops-circuit-release` 覆盖完整解除对象字节，绑定环境、
  host/action、当前 circuit 摘要（含 trip）、完整历史摘要、epoch、恢复 generation、
  当前策略 head/version、原因及有效期。拒绝目标 reserved/running/unknown 或时钟异常。
  在同一状态/历史 CAS 下关闭该 trip，并保留已明确签认的成功 execution ID；不按时间
  截断，迟到且未签认的成功仍计数。重放不能解除新 trip；普通解冻、续签及恢复不代替解除。
  额度、未知副作用锁和历史均不清零；S2/S3 必须证明目标静止、事务故障及旧副本恢复安全。
- 策略 `Load` 必须先对调用者提交的原始正文验签，再做解析/独立内存快照；拒绝无效 UTF-8。
- R 日志 `lines` 仅允许十进制字符串 1–200（无符号、前导零或选项）；`since` 仅允许
  带时区、整秒且不晚于校验时刻的 RFC3339 时间，不支持相对表达式。service 必须是
  已签对象规范名或登记别名；请求及全部实际 read 效果解析到同一规范身份，并绑定登记配置摘要。
  参数控制字符拒绝；helper 的固定 argv、实际来源复验、输出限制和脱敏仍为 S3 门槛。
- 共用本地时钟校验不可跳过：M、H `VerifyApproval`、普通解冻、熔断解除及逐步
  `Permit.Check` 都要求成功同步 ≤5 分钟、绝对偏差 ≤5 秒、无回拨/未来同步时间。
  有效 Owner 签名不豁免。S2/S3 各端独立观测，未知/过旧/超限/回拨均拒绝新写并报警。
- C2 门槛继续保留：实际文件/父目录/ACL/inode、OCI digest、正向及回退效果重建、
  三端私有账本恢复、Agent 权限拒绝、签名端防借签和 A/B 替换、测试身份不得安装到生产
  信任目录。S1 模型/三端标签不是这些证据；未实现模板 unsupported，S4 前逐项验收。

## 7. 风险与必须守住的边界

| 风险 | 防线与验收 |
|---|---|
| 名称合法但参数越权 | 未知字段、路径穿越、shell 字符、重绑定目标全部拒绝 |
| 目录检查后被替换 | root 专用父目录、无链接、文件描述符及摘要复核 |
| 整个安装脚本夹带扩权 | 拆开 prepare；隔离、sudoers、Secret 变化走 H |
| 网络操作切断自身 | 先装本地回退；拔链路后证明恢复；无证据不纳入 M |
| UniFi 写成功但回包丢失 | unknown、读回核对、禁止重写；测试 DHCP 恢复 |
| 同机重复或跨 mini 重复写 | 远端锁、fencing、去重 journal；启动第二 runner 不能双写 |
| 冻结、过期与排队竞态 | 在入队、claim、每次写前重查；原回退可完成 |
| 账本丢失或满盘 | 注入写失败；不能派新写；结果只补传、不重执行 |
| 缓存清理误删成果 | 活跃引用、归属、快照、可重建证明；脏 worktree 留存 |
| 普通日志泄漏凭证 | 合成密钥与隐藏字符测试；整段抑制；哈希与保存内容一致 |
| 持钥 executor 被攻破 | 每主机权限隔离；不能访问任意 shell；单机吊销演练 |
| admin 令牌泄漏伪造 H 批准 | 无 Owner plan 签名不签票、不执行；测试伪造批准记录与跨环境 claim |
| main/CI 产物夹带 root 代码 | Owner manifest、实际字节双验；修改任一文件或镜像 digest 必须拒绝 |
| 未签登记扩大 R/M 范围 | 本地 root-owned 签名制品；测试改 service、root、endpoint 与 stateful 标记 |
| `.50` 停机导致静默 | 平台 TTL、队龄、`.52` dead-man 和直投路径；切断 `.50` 后验证告警 |
| mini/平台/PG/NAS 故障 | 分别断开；验证承诺范围；未实现离线调度必须明确显示 |

永久逐次审批：分区、格式化、数据及备份删除。
还包括 firewall/VLAN、集群节点重启、凭证和 PROD DDL。
信任锚、执行器提权与安全护栏放宽也不能自动批准。
集群内 netplan、有状态项目换镜像/重建和 never-M 服务同样逐次批。
helper 升级、生命周期重设及 unknown 人工裁决也不能经 M 放行。
签名协议不能防御目标主机 root 被攻破；该主机须隔离并重建信任。
H 签名阻止泄漏 admin 凭证独自授权，但不能恢复已损坏的数据。
已有例行临时缓存保留策略不构成业务数据删除授权。
D10 始终 BLOCKED；一张审批单也不能解锁。
两台 TWS 主机的自动维护不在本设计范围。

验收必须证明两件事。
第一，Owner 合盖一晚，例行操作仍自动完成并回到线程。
第二，越界、冻结、过期和未知结果都不会变成自动重试。
一周后按实际决定数验 4.7，不按“少复制了几条命令”验收。

## 8. 复核 1 的处理

A/B 全部采纳；没有以接受风险替代修复。
本表是设计处理记录，运行时验收仍须在对应切片执行。

| 项 | 落点与验收 | 切片 |
|---|---|---|
| A1 | §4.2：Owner SSHSIG 绑定 plan；票据钥匙只在执行器；M 独立复核；伪造 admin 批准不能执行 | S1–S3 |
| A2 | §3.2：Owner manifest 与文件/镜像字节双验；main 和 CI 不能自授权 | S1/S3/S4 |
| A3 | §2.0：本地签名登记、R allowlist、helper 脱敏；登记篡改和日志秘密测试 | S1/S3 |
| A4 | §2.2–2.3：集群 netplan、有状态重建、never-M 归 H；join 前原子转 joining | S1/S4/S5 |
| A5 | §5–6：S2 失败/unknown 推送、周报骨架和存活验收；生产策略签名前强制检查 | S2/S4 |
| A6 | §5.1：平台 TTL/队龄、`.52` 周报 dead-man、独立 relay；断 `.50` 仍报 | S2 |
| B1 | §3.1：逐字段方向与 property tests；删条件、缩短 timeout、换 rollback 不误判收紧 | S1 |
| B2 | §3.3：解冻绑定 min_rule_version；执行器/helper 高水位；旧规则重放拒绝 | S1/S3 |
| B3 | §3.3：本地 stop-writes、已发票据撤销、逐步许可；冻结竞态测试 | S2–S4 |
| B4 | §4.2：token 绑定 executor/host/env；host 路由排除 RoleAdmin；跨环境结果拒绝 | S2 |
| B5 | §2.3、§4.2：只领 host_*；PROD 拒绝自由 shell host runner，含旧排队单 | S2 |
| B6 | §3.3：条款日/周限额和反复成功熔断；并发、重启、重命名不重置 | S1/S2/S4 |
| B7 | §5：关键成功立即入 Console、每日摘要；不增加成功手机推送 | S2/S4/S5 |
| B8 | §5：过期、冻结、helper 未知、未覆盖等拒绝留痕；审计失败仍拒绝 | S2 |
| B9 | §2.2：清理 plan 仅提示；helper 重算候选；活跃引用和路径替换拒绝 | S6b |
| B10 | §2.2：ErrClientNotFound 不写；登记静态/VIP 保留地址；含 `.100` 冲突测试 | S5 |
| B11 | §2.3、§4.2：helper 安装/升级为 H；handler_digest 不符拒绝 | S3/S4 |
| B12 | §4.1：`.50` 整机无 LLM/Agent；安装钥匙前验收；不以账户分开替代 | S3 |
| B13 | §6 显式列登记/manifest、macOS/UGOS、快照、二进制拆分、离线镜像、测试机、resolve 和 scope diff | S1–S6 |

C1–C6 也全部并入：安装归属见 §2.0/2.2；Git 摘要见 §5。
时钟检查见 §4.2.3；摘要链落盘见 §5。
disable 回退测试见 §4.2.3；unknown 局部锁见 §4.3。
对应验收分别归 S4、S6b、S3、S2、S4、S3。

## 9. 复核 573 的处理

本轮 B1 已修改授权语义，C1–C5 均写入实现与准入条件；没有将它们标成运行时已通过。

| 项 | 设计落点 | 实施/验收归属 |
|---|---|---|
| B1 | §3.1/3.3 固定基线适用域、两层交集、删除留拒绝墓碑、完整策略子集判据与反例 | S1；S3 三端一致、S4 全链复验 |
| C1 | §4.2.1 同对象展示/计算/签名，签名端及更新隔离，防借签与 A/B 替换 | S3，阻断 S4 签发 |
| C2 | §5.2 四端私有路径/写者、每步 fsync、墓碑回收、旧副本隔离恢复 | S1–S3，S4 重放复验 |
| C3 | §6.1 通用动作、别名、bundle/回退及有效 H 签名的 D10 拒绝矩阵 | S1/S3/S4；新适配 S5/S6 |
| C4 | §4.1、§6.2 新操作包和独立安装器，普通发布不能更新执行器 | S3；尚未交付可执行操作单 |
| C5 | §4.3 调度槽不承诺物理并发，§4.4 A/B/C 依赖隔离和恢复测试 | S2–S4 |
| N1/N2 | 保留上一轮落点；§4.2/6.1/6.2 与下述参数测试；设计回应不替代上线验收 | 对应各片 |
| N3/N4 | §4.4 掉盘分支、§5.2 恢复；九项选择未变，本轮只做文档验证 | S2–S4 故障测试仍待实施 |

S1/S3 参数准入还须覆盖前导选项、NUL/换行、重复 JSON 键、非预期环境、工作树文件/父目录替换；
“Owner 已批”的理由文字不能提供授权，不以固定 argv 一项代替全部参数安全证明。
