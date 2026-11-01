# 切法：过渡期后的模块进运行时（计划根 R5，W-31，2026-10-31）

本文件只放第 5 轮的台账段落，供 `agentrt-plan-import generate -round 5` 读；格式同 `WORK.md` 第 3、4 轮（`CUT-plan-import-2026-10-19.md` §2）。导入运行时之后以运行时为准，这里是导入时的快照。

### W-31

  - **第 5 轮（过渡期后的模块；统筹 2026-10-31 按 DESIGN-module-progress-2026-10-31 D7 起草）**：一个模块一项，做透再开下一个；步骤由运行时按证据推进（D1 A、D3 三个原子、D5 交付带步骤号），Owner 只批卡和签收
    - **第 5 轮逐项（核对于 2026-10-31 23:30）**。过渡期（R4）之后按模块登记；每一步的任务经独立复核才算验收（D2），所以不单列复核步。导入运行时之后以运行时为准，这里是导入时的快照。
      - 5.1 Console 模块进展视图（W-31；DESIGN-module-progress-2026-10-31 D1–D7）
        - [x] agentrt 步骤证据原子：step_tasks（只认已验收）、step_landed、step_stg_settled，standing 认它们作第一条规则｜10-31；platform `6ff7b6fe`；复核 630；#241
        - [x] Console 模块行：分段进度条、「N steps to go」、每格链到记录｜10-31；platform `100fc5c6`；#240
        - [~] 交付带步骤号：handin.sh `--plan-node`｜10-31 起；infra `cc3891f`（分支 modview/handin-plan-node），随 S5 的 infra 推送由你推上 main
        - [x] （你）批 PROD 发布单｜10-31 23:12 PROD 发布 `6ff7b6fe`；#242
        - [ ] ★ PROD 上步骤按证据自己往前走：R5 至少一步由 step_* 规则变成做完
        - [ ] 退役统筹的 Claude 进度页
      - 5.2 发布线：每个应用自己一条，同应用串行、不同应用互不阻塞（W-31；接手 R4:4.3 的按应用分线；DESIGN-release-lanes-2026-10-24 第 3 稿 §4；核对于 2026-10-31 23:15）
        - [x] （你）定 4.3 设计 12 点：按应用分线、共用资源读写锁、窄 Argo 执行器代替 Git 写入器｜10-26 infra `77676b0`（第 3 稿；第 3 稿之后的独立复核没找到记录）
        - [ ] Console 发布线视图：每个仓库一行，在途落地、STG 与 PROD 当前提交、线的持有者与到期、今日落地额度｜属于 5.2；先读现有窗口、落地和发布记录，车道上线后改读车道；v3.6 只有全局的 Release lane（`design/ops/LaneDetail.dc.html`）；数据按设计 §2.12，样子跟 Design 专轮
        - [ ] 发布操作和车道对象，先影子：登记表、渲染闭包、锁、拒绝审计｜4.3 S1
        - [ ] 兼容能力先装，再停发排空，把全局窗口换成车道权威｜4.3 S2a、S2b
        - [ ] （你）签应用登记表：哪些仓库归哪条线、共用资源、迁移归属｜4.3 §2.2，按应用子集签
        - [ ] 各发布入口逐族接进车道，旧窗口判定退役｜4.3 S3a–S3c、S3e；流水线、Argo 同步、apply、迁移 Job、重启、Owner 脚本、Finance
        - [ ] 落地和 push-main 只等同一条线，不再等任何窗口｜4.3 S3d；现在 `agentrt/landingci/window.go:29` 读全局窗口，`agentrt/landing/drill.go:139` 有窗口就 park
        - [ ] （你）按应用打开并行：platform、trade 各签一次｜4.3 S4
        - [ ] ★ 实测：platform 和 trade 同一时间各发一版不等待，同仓库仍串行
      - 5.3 PROD 自动发布：platform 的 PROD 发布按签名规则放行，你只收事后通知（W-56；接手 R4:4.3 剩下的 W-56 门槛；PLAN-w56-unattended-prod-2026-10-10；核对于 2026-10-31 23:15）
        - [x] 发布流水线自查 CI 绿、STG 同一提交，按确切提交发布｜10-12；infra `667b758`、`79c8088`，platform `2726c47`；你 21:13 应用，#12 第一次把关；TD-295 你 10-12 签收（infra `8bea0cc`）
        - [x] 发布后按摘要核对 Pod（STG 与 PROD）｜10-13；infra `d1495c7`、`f5ab877`、`b9ec378`；#16 核对通过
        - [x] PROD 不再重建：部署 STG 核过的那对摘要，Argo 应用按摘要钉住｜10-22；infra `b63fa49`、`a4431f1`、`e318a80`，platform `6ff3801b`；#85；TD-335 待你签收；10-31 只读：PROD 三个 Deployment 都按 @sha256 部署
        - [x] 每条有副作用的流水线先过故障即拒的冻结检查｜10-11 12:39 你应用（infra `d5f4cc1`）；10-31 只读：15 条发布、构建、apply 流水线的根任务都是 freeze-check
        - [x] 平台账号收窄：cicd 只写自己的 ConfigMap，Deployment 只许重启和缩放｜10-24 你应用（TD-432 批 A，infra `b8e313b`、`e889aa6`）；10-31 线上两条准入与主线文件逐条相同；TD-314、TD-293、TD-434 台账没跟上
        - [x] （你）生成发布签名密钥，指纹编进平台｜10-15 platform `28e63c1`（O18）；集群里签过的发版策略到期 2027-01-26，allow 不含 PROD 流水线
        - [x] （你）定冻结协议四项：只增的冻结记录，你删记录解冻｜10-11 18:20 你定 D1、D2、D4、D6；设计过复核 93、95
        - [x] 冻结判定第一片进主线（没接线）｜platform `3620e177`、infra `0aa585d`（10-12）；10-31 只读：集群没有 freezes CRD，平台没有别的包引用 releasefreeze
        - [ ] 冻结改读只增记录：设计收尾、接线、旧冻结写成墓碑｜4.3 S3a、§2.8；修订稿复核 121「先修」未收；10-15 锚编入后主线上旧的签名解冻已可用，复核 79、86 的绕法没处理
        - [ ] （你）装冻结记录的 CRD、准入和权限
        - [ ] （你）冻结演练：各入口被拒之后由你删记录解冻
        - [ ] 量出谁能改 platform PROD：录制包签名、重放先验签｜W-56 第 1 步 A 片，决定记录之五的方向，没出设计
        - [ ] （你）用你的身份跑一次带模拟身份的采集
        - [ ] 封住旁路：tekton-trigger 进准入，PROD 的 run 必须是登记的名字，applier 改不了 platform PROD 的工作负载｜W-56 第 1 步 D、F 片，TD-272
        - [ ] 窄 Argo 执行器：只同步到完整提交、只写登记的那对摘要｜4.3 定 11 A，W-56 第 1 步 E 片
        - [ ] （你）关掉 platform PROD 的自动同步，收回 tekton-deliver 对 Application 的写｜TD-330；10-31 只读：`bifrost-platform-prod` 仍跟 main、automated prune + selfHeal
        - [ ] 可信发布记录：两个摘要、ui 提交、构建输入、run UID，四方比对，只增不改｜4.3 S5a，W-56 第 2 步；10-31 只读：最新 PROD 记录（v3）只有 platform 提交
        - [ ] （你）签构建输入清单
        - [ ] 发布闸门进策略引擎，先影子，和独立核对脚本逐次比对｜4.3 S5b，W-56 第 3 步
        - [ ] 晋升动作和有界恢复：失败或超时回到发布前那对摘要，冻结下照样恢复｜4.3 S5c，W-56 第 4、5 步
        - [ ] （你）批新路径的人工试发，每次一张，直到监督器上线｜4.3 S5c
        - [ ] 带外监督器：保存意图、接管、恢复、失联呼你｜4.3 S5d，W-56 第 6 步；放 .50 独立账户
        - [ ] （你）批监督器的身份和权限
        - [ ] 影子满五次、近三次无差异后切强制；重跑矩阵、冻结、恢复用例，量各段超时｜4.3 S5e
        - [ ] （你）签 platform PROD 的自动发布规则：观察时长、中断上限、恢复条款，有效 90 天｜W-56 第 7 步
        - [ ] ★ 一次小改动按规则无人点击上了 platform PROD，失败自动回到上一对摘要，你只收到事后通知
        - [ ] 签规则后 30 天：要你点的 platform PROD 发布单为零，转人工的例外另列｜W-56 退出口径
      - 5.4 S5 内容检查器启用（W-31；DESIGN-S5-v3.1、TD-471、TD-472；首批 4 个 Console TS 路径）
        - [~] 构建入口接线：平台能起 bifrost-build-s5-checker｜platform `8850296311a1`，TD-467 平台侧核心单 #230 已备
        - [~] 修法 A：检查器镜像带齐依赖声明（TD-471）｜草稿 infra `ad96574`、platform `7ec82e27`、`2295a740`，本机 324/324 相等；核心落地单批了即选 A
        - [ ] 准入策略的 S5 段在 K8s 1.35 上编译通过（TD-472）
        - [ ] 重新登记基线：main 已漂移（10 处 S5_DATA_PROVENANCE、1 处 module-edge）
        - [ ] 构建检查器镜像，回填摘要与 materials，改出厂 UNBUILT 的测试
        - [ ] （你）批 S5 集群对象：服务账号、网络策略、准入策略、两个 Task、pipeline-ci-s5
        - [ ] （你）签 STG 的 S5 规则
        - [ ] STG 演练 P1：一件首批路径的落地检查 passed、findings 为空
        - [ ] （你）批 PROD 发布单（带回填后的信任根）
        - [ ] （你）签 PROD 的 S5 规则
        - [ ] ★ PROD 上一件首批路径的落地带 S5 证据自己合进 main

## 导入后

- 运行时是 R5 唯一的事实来源：`GET /api/v1/agentrt/plan?root=R5`（MCP `get_plan`），Console Work → Plan。
- 改步骤一律走计划变更（`propose_plan_change`）；交付带 `handin.sh propose --plan-node R5:<步>`。
