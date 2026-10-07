# LANE-P — bifrost-platform 鉴权与控制面（4 项）

先读 `cursor-tasks/README.md`。报告写到 `cursor-tasks/reports/LANE-P.md`。

- **起点**：`origin/td-l6`（不是 main：td-l6 带着还没进 main 的 TD-224/228/249，避免冲突）。
- **分支**：`cursor/td-platform`，只推分支。跨仓库的部分（infra / research / plugin）各开同名分支，同样只推分支。

| 项 | 一句话 | 注意 |
|---|---|---|
| TD-220 | 没有测试逐条枚举 platform-api 路由的鉴权；`POST /cluster/sync-kubeconfig` 与 plane 的 `POST /hermes/run-first-task` 无鉴权；LoadAuth 失败不记日志 | 防线就是那个「逐条枚举路由」的 Go 测试：新路由不登记鉴权就红 |
| TD-225 | 只读 MCP bridge 失败即放开：拼错的 `MCP_BRIDGE_FOCUS` 注册全部 74 个工具；env 里的 `PLATFORM_OPERATOR_TOKEN` 盖过 viewer 令牌 | `.mcp.json` 是治理层文件（`bifrost-trade-infra/agent-config/`，根目录是符号链接）：改动放 infra 分支，**不要碰任何真实令牌值** |
| TD-229 | trust overrides 在集群里落到 `$HOME`、读写错误被吞 | 按 `internal/releases` / `internal/threadtitles` 的 ConfigMap 模式；不新增外部依赖。若需要新 RBAC（k8s 清单）→ infra 分支 + 写进「要 Owner 批」 |
| TD-231 | IB feed 判定挂在一个写死的 NVDA 样本上；Trade namespace / DB 名是 53 处 Go 字面量 | 只做「样本从配置读」+「名单进 environments.yaml」+ 一条防字面量增长的测试；更大的插件健康契约不在本道 |

做完后不要起 deliver；platform 发版由 Owner 批。
