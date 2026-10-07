# LANE-B2 报告

## 改动

- bifrost-platform · `cursor/b2-platform` · `ccdf2005727a7990d1b2fbc57533e64badd7cb3a`
- bifrost-trade-infra · `cursor/b2-infra` · `b7d29bc8e8bf95c1d795a20ff3524cb19139c04b`

两条分支都已推到 origin。没有推 main，没有发版，没有 kubectl，没有写库。

Console 页 `#approvals` 放在 Mission Control（导航最上面一组）的第一项，Ops 透镜也能看到。第 3 阶段再定最终位置。批准 / 拒绝只带浏览器里另存的审批令牌（`localStorage` 键 `bifrost-ops-approval-token`），请求体 `channel: "console"`。列表和详情仍走现有的 `operatorToken()`。界面文案是英文 “Set approval token”（工作区规则：UI 不用中文）；任务里的「设置审批令牌」指的就是这个输入框。

## B1 接线（一行）

B1 的创建路径在 origin/main 上还不存在，本道没有建、也没有改那些文件。合并时在 `POST /api/v1/approvals` 的处理函数里，申请单落库、`id` 已经有了、写 201 之前加：

```go
_ = approvalnotify.NotifyCreated(r.Context(), approvalnotify.Created{
    ID:        id,
    Action:    body.Action,
    Tier:      tier,
    Requester: r.Header.Get("X-Bifrost-Session"),
})
```

导入 `github.com/weitingzhao/bifrost-platform/api/internal/approvalnotify`。错误可以丢掉：`NotifyCreated` 自己记日志。中转挂了不能让创建失败。批准、拒绝、过期不要调它。`click_url` 由这个函数拼成 `http://ops.bifrost.lan/#approvals?id=<id>`。`APPROVAL_NOTIFY_URL` 或 `APPROVAL_NOTIFY_TOKEN` 缺一个就只记日志、不发 HTTP。说明写在 `api/internal/approvalnotify/notify.go` 的包注释里。

列表客户端同时接受 `{ "items": [ ... ] }` 和裸数组。字段按接口约定：`id, action, tier, params, reason, rollback, requester, status, expires_at, result/error`。

## 防线

- `bifrost-platform/console/src/pages/__tests__/ApprovalsPage.test.tsx`
  - `renders a pending request and disables decisions without a token`（待批渲染：session、动作、级别、参数、理由、回滚、剩余时间；无令牌时 Approve / Reject 置灰并说明）
  - `opens the request named by #approvals?id=`（直达一条，手机点通知用的 hash）
  - `keeps the last 50 closed requests`
- `bifrost-platform/api/internal/alertrelay/relay_test.go`
  - `TestNotifyRejectsABadToken`（令牌错或空 → 401）
  - `TestNotifyNtfyFailureIs502`（ntfy 失败 → 502）
  - `TestNotifySetsTheClickHeader`（`Click` 头等于 `click_url`）
- `bifrost-platform/api/internal/approvalnotify/notify_test.go`
  - `TestNotifyCreatedSkipsWhenUnset`
  - `TestNotifyCreatedPostsClickAndBearer`（令牌不进消息正文）
  - `TestNotifyCreatedRelayFailure`

页面是单列、控件全宽（`flex-col`、`w-full`），手机宽度下不依赖横表。

## 门禁

在 `/tmp/cursor-b2-platform` 上，退出码分开看：

- console `npx tsc -b` → 0
- console `npm run lint` → 0（19 条既有 warning，0 error；没有本道新增的 error）
- console `npx vitest run` → 0，119 files，804 passed
- console `npm run build` → 0
- api `go build ./...` → 0
- api `go vet ./...` → 0
- api `go test ./...` → 0（含 `alertrelay`、`approvalnotify`）

## 验收

```bash
cd bifrost-platform/console && npx vitest run src/pages/__tests__/ApprovalsPage.test.tsx
cd bifrost-platform/api && go test ./internal/alertrelay/ -count=1 -run 'TestNotify'
```

预期：3 个页面测试通过；`TestNotifyRejectsABadToken`、`TestNotifyNtfyFailureIs502`、`TestNotifySetsTheClickHeader` 通过。

发版并在 .50 重新部署 operator-plane 之后：

```bash
curl -sf http://192.168.10.50:8783/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://192.168.10.50:8783/api/v1/alerts/notify \
  -H 'Content-Type: application/json' \
  -d '{"title":"t","message":"m","click_url":"http://ops.bifrost.lan/#approvals?id=probe","priority":4}'
```

预期：health 里 `alert_relay` 为 true；无令牌的 notify 返回 401。然后打开 `http://ops.bifrost.lan/#approvals` 与 `#approvals?id=<id>`（手机宽度能打开那一条）。

## 要 Owner 批

本机 `bifrost-platform/.env` 里 `ALERT_RELAY_TOKEN` 有值（只确认了键在，没有打印）。先建 Secret，再合 infra（Argo 会改 PROD Deployment），再发 platform，最后在 .50 重部署 operator-plane。

1. 建 Secret（不要 `echo` 令牌）：

```bash
token=$(grep -E '^ALERT_RELAY_TOKEN=' /Users/vision-mac-trader/Desktop/stocks/bifrost-platform/.env | head -1 | cut -d= -f2-)
token=${token#\"}; token=${token%\"}
token=${token#\'}; token=${token%\'}
test -n "$token" || { echo "ALERT_RELAY_TOKEN is missing"; exit 1; }
kubectl --kubeconfig "$HOME/.kube/bifrost-k3s.yaml" -n bifrost-platform-prod create secret generic bifrost-platform-approval-notify \
  --from-literal=APPROVAL_NOTIFY_TOKEN="$token" \
  --dry-run=client -o yaml | kubectl --kubeconfig "$HOME/.kube/bifrost-k3s.yaml" apply -f -
unset token
```

Secret 名 `bifrost-platform-approval-notify`，键 `APPROVAL_NOTIFY_TOKEN`。overlay 里 `optional: true`，没建 Secret pod 也能起，只是不推送。

2. 合并 `cursor/b2-infra` 进 main。Argo 会给 PROD `platform-api` 和 `platform-workers` 加上 `APPROVAL_NOTIFY_URL=http://192.168.10.50:8783/api/v1/alerts/notify` 和上面的 Secret。`kustomization.yaml` 多了一行 patch，可能和 B4 的 UniFi patch 撞同一处。

3. Platform 发版（合并 `cursor/b2-platform` 进 main 之后）。窗口在另一个会话里一直占着：

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra
scripts/release/release.sh hold --what bifrost-platform,bifrost-ui
```

另一个会话：

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra
REVISION=<merged platform SHA> make k3s-deliver-platform
scripts/release/platform-prod-pinned-from-stg.sh bifrost-deliver-platform-<unix> -o /tmp/platform-prod-b2.json
kubectl --kubeconfig "$HOME/.kube/bifrost-k3s.yaml" create -f /tmp/platform-prod-b2.json
```

4. 在 .50 重新部署 operator-plane。脚本从**当前 checkout** 编译，所以先切到含 notify 的提交。不要加 `--disable-alert-relay`。显式 `ALERT_RELAY=on` 会保留呼人（origin/main 的 `deploy_mac_mini.sh` 在部署者没设、或设成 off 时也会留下远端的 `on`，除非显式 `--disable-alert-relay`）：

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-platform
git checkout <merged platform SHA>
ALERT_RELAY=on ./scripts/agent/deploy_mac_mini.sh vision@192.168.10.50
```

## 后续

- 在 B1 加上面那一行之前，创建申请不会推手机。Console 页要等 B1 的 API 和这次 platform 发版之后才有真数据。
- 接口没有 `created_at`。已结历史按 `expires_at` 新到旧取 50 条。
- `kustomization.yaml` 与 B4（`cursor/b4-infra`）都要改 PROD overlay 的 patch 列表，合并时只该多一行 `platform-approval-notify.patch.yaml`。
- 无其他新债。没有改 B1 / B3 / B4 的文件，没有改共享 checkout。
