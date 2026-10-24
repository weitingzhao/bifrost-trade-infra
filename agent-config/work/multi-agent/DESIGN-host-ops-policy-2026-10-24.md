# 主机操作策略与带外执行器

2026-10-24 · Work 560 · W-31 第 4 轮 4.7 / W-50。
状态：设计提案，未签名，未实施。

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
| `host_service_restart(host, service)` | 登记服务的 `systemctl restart` 或 `launchctl kickstart` | 重启不恢复内存；健康失败停自动循环 | O2/O13 |
| `host_service_state(host, service, state)` | 固定 unit 的 start/stop/disable；含旧 Mac agentd 退役 | 恢复原启用及运行状态；agentd 先停派并排空 | O2/O8 |
| `host_container_restart(host, project, service)` | 固定容器 `docker restart`；不变镜像、挂载、权限 | 健康失败恢复旧配置；内存不可恢复 | O13/B |
| `host_compose_reconcile(host, project, bundle)` | 固定 compose 的 `pull`、`up -d`；同配置可 force-recreate | 保留旧 digest/config；用旧版重建；不执行 `down -v` | O13/B |
| `host_image_stage(host, artifact)` | 校验归档后 `docker load`；只导入已登记镜像 | 删除本次未引用镜像；不改运行容器 | O13 |
| `host_monitoring_install(host, bundle)` | mini 安装 LaunchAgent；06 安装 exporter；NAS 固定 compose | 恢复旧文件与服务；首次安装可撤登记对象 | O13 |
| `host_monitoring_remove(host, install_id)` | 停用本次安装的 exporter，移除确定的文件清单 | 重装原 bundle；先协调平台告警配置 | O13 |
| `host_monitoring_drill(host, exporter, duration_s)` | 停一个 exporter，记录告警，再恢复；最长 10 分钟 | 主机本地定时恢复；一次只演一台 | O13 |
| `host_agentd_update(host, bundle, environment)` | 停派、排空、安装固定二进制与等权 unit、启动、核对 | 回到上一 digest；隔离、凭证、出站规则变化转 H | O2/O8 |
| `host_toolchain_install(host, bundle)` | 已登记目录内安装固定 Go/Node/CLI/测试 DB 工具 | 切回旧版本；不运行可变远程安装脚本 | O2/O3 |
| `host_validation_run(host, profile, bundle)` | 固定 sandbox、隔离、bench、exam、Git 保护探针 | 停指定进程组；只清合成测试资源；不放宽保护 | O2/O8 |
| `host_temp_cleanup(host, plan)` | 重建缓存、node_modules、登记临时日志；先移入隔离区 | 7 天内恢复；到期只清可重建对象 | W1/O2 |
| `host_lifecycle_collect(host, plan)` | 调现有生命周期检查；按任务归属归档已结束 worktree | 恢复 bundle；脏目录、无归属目录只报 | W1 |
| `host_netplan_apply(host, plan)` | 固定接口及已审阅配置；备份、generate、apply、双路探测 | 先装本地超时回退；不改 VLAN、网关、防火墙 | B |
| `host_new_node_join(host, runbook, cluster_id)` | 新空白 worker；固定 K3s 版本、标签和初始 taint | 无负载时撤本次安装；已有工作负载转 H | B/W2 |
| `host_new_node_fixed_ip(host, plan)` | 平台调用现有 UniFi 实现；只写目标 MAC 的三字段 | 恢复 before；原为 DHCP 时需新增受限恢复动作 | B/N |
| `host_git_endpoint_set(host, repo_set, mapping)` | 固定 origin/insteadOf；只允许登记的 Gitea 地址 | 恢复原配置；不接触 credential helper | O8 |

M 不是“任何可撤回命令”。
重启有短时中断，先检查依赖和维护锁。
MinIO、Gitea、registry 有共享依赖，必须逐项目登记。
NAS 旧 MinIO 路径安全性未核实前，不纳入自动重建。
目录位于可写父目录时直接拒绝，不自动 chown 修补。

`prepare-agent-06.sh` 同时改防火墙、AppArmor 和凭证。
现有 `update-agentd` 会调用它，不能整体列入 M。
必须拆出仅换二进制的更新动作。
安装监控不自动授予新 sudo、特权挂载或端口权限。
这些能力先经 H 安装，后续复用才按 M。

临时清理只涵盖可重建且无活跃引用的对象。
身份由受保护登记表决定，不靠目录名猜测。
删除唯一代码、证据、备份或业务数据，永远归 H。
已清缓存只能重建，不能宣称原字节可恢复。

netplan 自动范围只含单机地址、DNS 等登记变更。
集群成员须有第二管理路径和集群健康前置检查。
涉及路由拓扑、共享 VIP 或无法证明回退，转 H。
新节点加入前须证明不在集群、无业务卷。
加入时保持 `NoSchedule`；放开调度另走平台动作。
已有 join credential 仅由 helper 消费，不交给 Agent。
创建、轮换或扩权该 credential 仍逐次批准。

UniFi 自动入口只适用于登记为 `new` 的机器。
MAC、IP、hostname 必须与资产记录完全匹配。
现有 `unifi_client_fixed_ip` 保留 D 级入口。
新入口复用其校验，额外检查生命周期与期望前态。
补齐 DHCP 恢复、跨进程互斥后才能签入策略。

### 2.3 H：逐动作批准；X：禁止

每行是一类具名模板，不是一张包办全部动作的审批单。
参数、目标 UID、制品摘要和回退范围全部入审批哈希。

| 具名动作与参数 | 可触碰范围、实际执行 | 回退及限制 | 来源 |
|---|---|---|---|
| `host_disk_provision(host, disk_id, layout)` | 指定序列号的分区、格式化、存储池 | 无原地回退；需已验备份；装 SSD 由人做 | B/W2 |
| `host_data_delete(host, object_ids, plan)` | 精确数据、卷、备份或唯一文件；包括解密副本清理 | 从备份恢复；不能当临时缓存处理 | O2/O7/W1 |
| `host_network_security_change(host, plan)` | firewall、VLAN、nftables、路由拓扑 | 独立管理路径回退；不经 M netplan 绕行 | O2/B |
| `host_node_power(host, operation, plan)` | 已入集群节点 reboot/poweroff；NAS 停机也纳入 | 开机与恢复负载；不可恢复内存 | O2/W2/B |
| `host_node_retire(host, step, plan)` | cordon、卷备份/删除、drain、K3s uninstall、删除 Node | 每个高风险步骤单独批准；按 UID 复核 | O2 |
| `host_access_change(host, account, plan)` | 新账户、sudoers、authorized_keys、AppArmor、NAS 家目录修复 | 吊销/禁用账户；不能回退为已知不安全权限 | O2/O3/O13 |
| `credential_install(target, credential_ref, operation)` | 生成、复制、轮换、撤销 Secret/令牌；CLI 登录、钥匙串、pgpass | 重新签发；不输出值；Owner 完成设备登录 | O2/O3/O4/O5/O8/O12 |
| `host_backup_verify(host, backup_id, plan)` | 指定加密备份、私钥引用、隔离解密目录 | 清理副本另有明确授权；不读回明文 | O7 |
| `rule_publish(rule_id, version, digest)` | 规则签发、续签、信任锚、公钥更换 | 新签版本；不得回退到更宽旧规则 | O2/O9 |
| `platform_manifest_apply(plan_id)` | 现有 `plan_manifest/apply_manifest`；固定对象与提交 | 旧清单；删除对象或回退安全护栏仍逐次批 | O1/O6/O7/O10–O13 |
| `platform_access_change(plan_id)` | RBAC、准入策略、NetworkPolicy、仓库权限 | 精确旧策略；扩大权限必须新批准 | O4/O5/O6/O8/O12 |
| `platform_database_migrate(database, migration_id)` | 角色、建库、schema、授权；PROD DDL | 按迁移回退；破坏性 DDL 不自动 | O5 |
| `platform_retention_apply(plan_id)` | Tekton TTL CronJob 与不可恢复的运行记录删除 | 旧规则只影响以后；已删记录不回来 | O11 |
| `gitea_repository_admin(repo, operation, plan)` | 转普通仓库、复制分支、归档、删仓库/组织、注册开关 | 按动作恢复；删除可能需整库恢复 | O7/O8 |
| `platform_release_request(release_id)` | 现有发布动作；仍按专门发布策略判断 | 依原发布回退约定；主机策略不扩大授权 | O1/O4/O6/O8/O12 |
| `platform_backup_start(backup_id)` | 现有具名备份/Job 动作；保留原级别 | 无需撤回成功备份；清理失败产物另判 | O5/O7 |
| `owner_run_command(command, reason, runner)`（现有） | 未覆盖操作的逐次 D 级兜底；默认 Owner 运行 | 不进 M；受限 host executor 不能运行任意 shell | ADR/W-50 |
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
收紧只允许集合缩小、限额下降、期限缩短。
无法证明是收紧，就按放宽处理。
规则没有任意表达式，也没有命令正则授权。

请求结构为 `action + params + host + work_id + requester_thread`。
调用身份由认证层取得，不信自报 requester。
执行器身份也由凭证绑定，不能只信 `executor_id`。
接线需补此校验，现有 claim 只限制 runner 角色。

新 M 动作默认按需审批处理，不能简单设成 TierB。
专用 gate 命中后原子写入系统授权的执行记录。
记录标明 `authorization=host_policy`，不伪造 Owner 点击。
沿用审批租约协议，但不沿用“call directly”的自动批准分支。
所有入口共用校验；内部 executor 标记也不能跳过冻结复查。

匹配顺序固定：

1. 严格解析请求；未知参数直接拒绝，不沿用静默丢弃。
2. 查动作硬边界；X 拒绝，H 建逐次审批。
3. R 走只读目录；不依赖 M 策略有效期。
4. M 校验签名、版本、环境、有效期、冻结与信任锚。
5. 核对资产指纹、生命周期、参数集合、helper 与配置摘要。
6. 生成确定性 plan，绑定前态、检查、回退和锁范围。
7. 原子登记授权结果、`params_hash`、`plan_hash`、幂等键。
8. 领单及每个副作用前重查策略、冻结、前态与租约。

多条规则匹配时取约束交集；冲突即拒绝。
策略失效、读取错误、时钟异常、资产未知均不自动执行。
回退缺失、审计落盘失败、无法取得锁同样拒绝。
“不匹配”返回具体原因，并保留申请入口。
签名损坏或冻结不自动转成人工绕过路径。
未知请求不降格为自由 shell。

冻结单独存为 `host_ops_freeze`，含单调 `epoch`。
任何已认证 operator 可冻结；冻结立即持久化。
解冻必须由 Owner 签 `bifrost-host-ops-unfreeze`。
签名绑定环境、当前 epoch 和原因。
删除冻结文件、回放旧解冻或回拨 epoch，均视为冻结。
缺少冻结记录也视为冻结。

冻结停止排队、新领单及未开始的副作用步骤。
已开始的命令进入动作定义的安全停止点。
不承诺瞬间撤销已经发生的网络或容器变更。
已登记的本地安全回退仍允许完成。
回退范围和期限在原 plan 中固定，不能扩大。
策略到期同样停止新步骤，不自动续期。
到期前 14/3/1 天提醒；过期有等待任务时再提醒一次。
续签入口显示范围差异、期限与执行统计。

## 4. 执行器与主机边界

### 4.1 架构选项

已定的 `.50` 放置不重新请求决定。
其余推荐均是实现依据候选，本次不部署。

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
账户 `bifrost-host-exec` 与 operator-plane、Agent 账户分开。
operator-plane 只转交元数据，不直接加载私钥。
实现可随同一平台制品发布，运行权限仍隔离。
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
票据由平台签发，短期有效，绑定 plan、目标及执行器。
M 票据还携带 Owner 签名策略及其收紧链。
helper 独立验证范围和期限，不能只相信平台给的层级。
H 票据绑定单次审批及本机预装能力，不能扩展 helper 权限。
远端只持验签公钥，不持 Owner 的签名私钥。
这把执行票据钥匙须独立安装并逐次批准轮换。

传输只发送严格 JSON 和制品字节，不拼接命令字符串。
helper 使用固定 argv、干净环境和固定 PATH。
不继承请求者的环境、SSH 配置或 Git 配置。
源码、unit、compose、回退文件及所有父目录不可由 Agent 修改。
路径逐层验证且禁止符号链接穿越。
写前重新核对 inode、属主与摘要，避免检查后被替换。
制品来自已审阅 manifest，不能只接受调用方给的哈希。

Agent 仅持请求/只读身份，不持 executor 身份。
mini 私钥目录 0700、文件 0600，不挂进 Agent 环境。
执行器不提供读文件、读环境或任意 SSH 工具。
agent-06 的现有出站规则继续拒绝 SSH、NAS 和 UniFi。
本机进程隔离与网络限制必须实测，不能仅靠提示词。
STG 只接测试主机身份，不能领 PROD 的真实节点单。

### 4.3 执行、超时与并发

全局同时一个写动作，每台主机也只有一个。
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
`unknown` 占住冲突资源，直至确认完成或由 Owner 处置。
结果晚到可按原 lease 接收一次。
本地 journal 保留至平台确认接收，重启后继续补传。

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

每周一 09:00 Chicago 生成一份 Console 周报。
含成功次数、主机、条款、回退、失败、unknown 和减少的逐次审批数。
还显示操作耗时、Owner 决定数及最常见拒绝原因。
成功不单独推手机；周报可查，不额外发送成功推送。
失败、unknown、回退失败才立即推；同事件去重。
审批需求、冻结和续签提醒是治理通知，照常发送。
推送失败持久重试，不能把 accepted 写成手机已收到。
复用现有通知中转；B3 完成前保留 `.50` 中转单点的限制。

## 6. 切片、估算与 Owner 的动作

估算为单条实施线的人日，不含等待及硬件窗口。
先交可核对的制品，再让 Owner 安装或签名。

| 切片 | 交付与验收门槛 | 估算 | Owner 必须做 |
|---|---|---|---|
| S1 目录与规则 | 闭合 schema、签名/收紧/冻结；拒绝矩阵全过 | 2–3 天 | 最终签规则前审阅范围 |
| S2 领单与审计 | 新动作 gate、认证绑定、statefile、outbox、线程回传 | 2–3 天 | 涉信任边界的发布批准 |
| S3 执行器与 R | `.50` 独立服务、主机 helper、身份及限权阳性/阴性测试 | 2–3 天 | 安装账户、逐主机钥匙、sudoers、host key；约 60–90 分钟 |
| S4 首批 M | exporter、服务/compose、二进制更新、缓存隔离；故障回退演练 | 2–3 天 | 签第一版 90 天策略；约 15–20 分钟 |
| S5 网络与接入 | netplan watchdog、新节点 taint、UniFi 前态恢复；断线测试 | 3–4 天 | 新机资产登记、join credential 配置；硬件安装 |
| S6 H 与可见性 | Console 逐动作审批、完整影响展示、周报、失败推送 | 1–2 天 | 批测试环境的高风险演练单 |
| S7 一周观察 | 合盖运行、零手贴例行命令、审计齐全、每周决定少于 40 次 | 1 天工作 + 7 天观察 | 看周报；无逐项成功签收 |

合计约 13–19 人日，另加一周观察。
这是首批闭环估算，不是整个目录的全部实现工期。
工具链、Git 配置、镜像离线搬运随后按需各补 0.5–1 天。
其余 H 模板先复用现有动作或 Owner 兜底。
把握中低；NAS SSH 限权和断线恢复风险最大。
所有运行时发布继续遵守原发布规则。
新接口、策略状态和票据协议随各片独立复核。
本次只交设计，不启任何切片。

首次凭证引导不能自动完成。
Owner 配置节点钥匙、sudoers、执行器身份和公钥锚。
Owner 私钥、管理员 kubeconfig 不迁入执行器。
已有 host credential 的受限使用不等于 Secret 变更。
后续新增主机权限、轮换凭证、续签或扩权仍需 Owner。
把这些合并成准备完整的操作包，避免来回追问参数。

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
| mini/平台/PG/NAS 故障 | 分别断开；验证承诺范围；未实现离线调度必须明确显示 |

永久逐次审批：分区、格式化、数据及备份删除。
还包括 firewall/VLAN、集群节点重启、凭证和 PROD DDL。
信任锚、执行器提权与安全护栏放宽也不能自动批准。
已有例行临时缓存保留策略不构成业务数据删除授权。
D10 始终 BLOCKED；一张审批单也不能解锁。
两台 TWS 主机的自动维护不在本设计范围。

验收必须证明两件事。
第一，Owner 合盖一晚，例行操作仍自动完成并回到线程。
第二，越界、冻结、过期和未知结果都不会变成自动重试。
一周后按实际决定数验 4.7，不按“少复制了几条命令”验收。
