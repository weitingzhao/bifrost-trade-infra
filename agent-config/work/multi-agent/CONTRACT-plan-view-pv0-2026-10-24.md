# PV0 契约与映射（Work 564，2026-10-24）

## 1. 决定与交付边界

Work 564 `BRIEF.md` 明确：4.1 的 13 点按推荐；D-PV1 A、D-PV2 A、D-PV3 A 已定。
这些选择不再待问。`CUT-plan-view-2026-10-24.md` 原文从本地 `plan-view-cut`
提交 `eb58dc9` 原样带入，保留它写作时的“待选择”历史措辞；当前决定以本段为准。
基线为 infra `881253d`。本次没有查运行时、发布、读 Secret 或建立审批单。

交付是 `PLAN-VIEW-R4-v1.json`，`kind=agentrt.plan_view/v1`、`v=1`，计划版本 1，
产物类型对应现有 `other`。这是待采用的图（`adoption=proposed`），不是已写入运行时的状态。
采用图仍是切法 §10 的独立步骤；不得把这份文件的提交伪装成 `note.plan_view` 事件。

## 2. 字段与不变量

`agent-config/scripts/validate_plan_view.py` 是本片可执行的封闭字段契约。
根字段：协议、租户 `dev`、根 `R4`、版本、采用标记、基线、决定、来源、节点。
节点沿用切法 §3.2 的分类、主线序号、锚点、职责、验收、估算、绑定，并补齐
`milestones` 和带来源的 `evidence`。只读运行状态 `execution`、`delivery`、
`waiting_on` 不写进此文件，添加这些字段会被拒绝。

| 字段 | 本片口径 |
|---|---|
| `plan_node_id` | `4.1` 等为导入源逻辑键，**不是已查得的数据库主键**。PV1 在锁内按 root 映射真实节点，拒绝缺失或歧义 |
| `parent` / `ordinal` | 保留第 4 轮结构；PV1 采用时核对树版本；父节点不能成环 |
| `lane_kind` / `mainline_order` | `mainline`、`branch`、`support`；主线路径显式排序，序号唯一连续 |
| `anchor_node_id` | 支线、配套指向主线节点；展示位置，不是阻塞边 |
| `depends_on` | 明确 root/node、前置 `milestone`、本节点 `required_for`、`relation`、理由与来源 |
| `required_for` | 阻塞只作用于该里程碑，不能把实施门槛倒灌给设计。父项依赖也不能自动施加给提前片 |
| `relation` | `blocks` 才阻塞，必须无环；`related` 只关联，允许反向关联，拒绝自关联 |
| `next_responsible` | 默认责任；不是“现在等谁”的断言。真实派工覆盖默认；provider 未查到则为 null |
| `acceptance` | 每条含中文标准、里程碑、规则引用、证据要求、环境与来源 |
| `rule_ref` | 语义引用，不是已部署的 `done_rule_json`。`external_verified` 等原子需 PV1–PV2 接线后才能参与计算 |
| `estimate` | 区间或 null、复核轮数、来源、理由、low/medium。未测不编天数；PV 整片沿用 9–11 人日，包含复核，不含等待 |
| `bindings` | 本片均为空；不编造 mission/task/run/approval ID。PV1 必须核对租户、节点与版本 |
| `evidence` | 有来源的离线观察，不是另一套可手改的完成状态；区分 repository、legacy、Owner statement，`live_verified=false` |

所有对象拒绝未知字段和版本；JSON 重复键拒绝。最多 500 节点，拒绝缺来源、
重复节点、自依赖、悬空节点/锚点/父节点/里程碑、重复主线顺序与阻塞环。
PV0 没有跨轮绑定，遇到跨根边直接拒绝；PV1 扩展前须实现切法要求的多根有序锁与租户验证。
本校验器只约束本片文件，不能代替 Go 事务校验器、数据库 CHECK 或权限检查。

## 3. 采用的映射

| 项 | 类别 | 路径 / 锚点 | 真阻塞与当前证据 |
|---|---|---|---|
| 4.1 | mainline | 1 | 当前首段；第 3 稿与 13 点决定已具备，S0 仓库准备；P0 线上未验 |
| 4.2 | mainline | 2 | 实施等 4.1 PROD；Finance 签名与第二仓接入各有验收；台账不是实时状态 |
| 4.3 | support | 4.1 | 设计先行，实施等 4.1 PROD；复核 535 结论为“先改” |
| 4.4 | mainline | 3 | 设计和记忆先行，实施等 4.1 PROD，**不等 4.2 完成**；复核 536 为“先改” |
| 4.5 | support | 4.1 | 完整现场流实施等 4.1 PROD；全计划视图提前片独立，不继承此门槛 |
| 4.6 | support | 4.1 | 第一波并行；已有盘点，清理与连续七天观察分开 |
| 4.7 | support | 4.10 | 实施等第二仓接入；一周决定数未采集 |
| 4.8 | support | 4.2 | 第二波实施等 4.1 PROD；题集签名单列 |
| 4.9 | branch | 4.4 | B4 ①先行，其余实施等第二仓；硬件窗口单列，不阻塞 4.1 |
| 4.10 | mainline | 4 | 汇合 4.1、4.2、4.4、4.6、4.7 的独立证据；五个验收格，不能一键完成 |
| 4.5.pv | support | 4.1 | 与 4.1 并行；PV0 本片，PV1–PV5 未实施 |
| 4.7.host-policy | support | 4.10 | 九点架构已定；视图可用后再实施，晚间顺序覆盖旧台账“第一件” |

主线 4.1 → 4.2 → 4.4 → 4.10 是叙事路径；每个箭头不自动成为 `blocks`。
五格分别保存：自主合入比例、每周决定数、合盖一夜、双产品并行、一周免清理。
任一格缺证据，4.10 不完成。accepted 不能证明 landed；run 绿不能证明实际部署和健康。
旧 Work 尾注与手工勾选只作候选证据，撤销、陈旧、采集失败由 PV2 投影明确呈现。

## 4. 验收与交接

```bash
python3 agent-config/scripts/validate_plan_view.py
python3 -m unittest discover -s agent-config/scripts -p test_validate_plan_view.py
```

第一条输出 `PASS: 12 nodes; references and blocking graph valid; not adopted`。
第二条正反测试覆盖环、悬空、未知协议、重复键、错误顺序及并行设计不误串行。
PV1 继续实现版本 CAS、真实节点映射、跨租户拒绝、事件词表与完成原子；PV2–PV5 按切法推进。
本片没有新 RPC、DDL、运行时写入或 UI 改动。
