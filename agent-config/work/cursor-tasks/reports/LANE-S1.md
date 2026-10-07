# LANE-S1 报告

起点：platform `origin/main` `2727eb0294c62f697a00bd51ffc455a924027171`。只推了分支 `cursor/s1-platform`，没有推 main，没有 deliver / PipelineRun / kubectl apply / 写库 / 改 `TECH_DEBT.md` 或 `RATCHETS.md`。没有改共享 checkout，没有改 `scripts/agent-guard/preflight.js`。D10 仍是 BLOCKED：没有下单路径、没有扩容 daemon、没有写 `ib:operator:cmd`、没有 `POST /control/*`。

分支尖端：`3621f41e803a6331739d9d3d484147d20ed022b8`。

## TD-206
- Claim：成立。改前 `agent/git-bridge/src/server.ts:308` 是 `git(dir, ['add', '-A'])`，`:346` 是 `git(dir, ['push', 'origin', branch])`，`:372` 是 `app.listen(PORT, '0.0.0.0')`。非 GET 没有 bearer。`/health` 保持开放，给 bdev watchdog 用。
- 改动：bifrost-platform · `cursor/s1-platform` · `cec8b01cf240f47add978babb9b7f0645c94d187`（桥本身），外加 `897eeca2f880a5567050fe4d7094daaa4e87865c` 与 `3621f41e803a6331739d9d3d484147d20ed022b8`（platform-api 的 status 探测带头）。有令牌时，除 `GET`/`HEAD /health` 外的路由都要 operator 或 admin bearer（名字来自 `config/platform-auth.yaml` 的 `token_env`，值只从进程环境和 `bifrost-platform/.env` 读，不写进仓库）。没有令牌就只绑 `127.0.0.1`。`/commit` 拒绝空的 `paths`，只执行 `git add -- <paths>`。`/push` 只送 `HEAD:refs/heads/<当前分支>`。git 仍是异步 `execFile`，没有回到 `execSync`。探测依次读 `PLATFORM_OPERATOR_TOKEN`、`PLATFORM_ADMIN_TOKEN`、`PLATFORM_PROD_OPERATOR_TOKEN`、`PLATFORM_PROD_ADMIN_TOKEN`。
- 防线：`agent/git-bridge/src/server.test.ts`（11 个：匿名 `POST /commit` 与 `GET /status` 为 401，`GET /health` 为 200，空 paths 为 400，add 参数正好是 `['add','--','a.txt']`，push 参数是 `['push','origin','HEAD:refs/heads/topic']`，源码不含 `'add', '-A'` / `'add', '.'` / `'commit', '-a'` / `execSync(`）。`api/internal/agentbridge/handler_test.go` · `TestProbeGitBridgeSendsOperatorToken`、`TestProbeGitBridgeUsesProdOperatorToken`。没有改 infra 的 `scan.sh`：这条防线在 platform 单测里，argv 扫描要动 infra，本道不推 infra。
- 门禁：在 worktree 的 `agent/git-bridge`：`npm test` → exit 0，11 passed；`npx tsc --noEmit` → exit 0。`api/`：`go test ./internal/agentbridge/ -count=1 -run TestProbeGitBridge` → exit 0。
- 验收：`cd bifrost-platform && git fetch -q origin && git checkout 3621f41e803a6331739d9d3d484147d20ed022b8 -- agent/git-bridge && cd agent/git-bridge && npm test`。预期 11 passed、exit 0。`git grep -n "\['add', '-A'\]" 3621f41e803a6331739d9d3d484147d20ed022b8 -- agent/git-bridge` 无输出。线上 `curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.74:8785/status` 要等 Owner 重启 git-bridge 之后才是 401（有令牌、绑在 LAN）或连接被拒（没有令牌、只听 127.0.0.1）。现在的进程还是旧代码，匿名 GET 仍是 200。
- 要 Owner 批：合并并在 Mac Pro 检出之后，`bdev restart git-bridge`，再 `bdev restart platform-api`。git-bridge 不需要新的环境变量名，它读 `platform-auth.yaml` 里已有的 `PLATFORM_OPERATOR_TOKEN` / `PLATFORM_ADMIN_TOKEN`（值在 `bifrost-platform/.env`）。本道没有重启。集群里的 platform-api 要能通过，它发出的 bearer 必须等于桥从那份 `.env` 装进来的 operator 或 admin 值。STG pod 的变量名是 `PLATFORM_OPERATOR_TOKEN`（Secret `bifrost-platform-role-tokens`，由 `scripts/k3s/apply-platform-role-tokens.sh` 从 infra `.env` 的 `PLATFORM_STG_OPERATOR_TOKEN` 写入）。PROD pod 的变量名是 `PLATFORM_PROD_OPERATOR_TOKEN`。名字不同、值也通常不同。对不齐时，集群上的 `GET /status` 会 401；本机 bdev 的 platform-api 和桥读同一份 `.env`，对得齐。
- 后续：`HEAD` 若已在 `main`，这条 ref-only push 仍会推 `main`。台账里「非 release.sh window 就拒绝 main」没有做。`GET /status` 在有令牌时也要 bearer，比 Fix 正文里的「只锁非 GET」更严，为的是对上「匿名 GET /status 为 401」这条验收。

## TD-207
- Claim：成立。改前 `agent/remediation/src/server.ts:184` 的 `POST /run`、`:211` 的 `POST /run/:id/respond` 没有鉴权。`scripts/agent/deploy_mac_mini.sh:169` 写 `REMEDIATION_RUNNER_BIND=0.0.0.0`。Hermes 改前 `agent/hermes-gateway/src/server.ts:94` 的 `POST /skills/:id/trigger` 和 `:106` 的 `POST /reload` 没有鉴权；`agent/deploy/com.bifrost.hermes-gateway.plist:27` 是 `HERMES_GATEWAY_BIND=0.0.0.0`。
- 改动：同一分支 · `61871c67f8e930b46462f726002acee5236bdebf`。环境变量名只有 `REMEDIATION_RUNNER_TOKEN`（必须和 `PLATFORM_OPERATOR_TOKEN` 不是同一个值）和审批用的 `PLATFORM_OPERATOR_TOKEN`。仓库里只有键名和生成命令的注释，没有值。两个进程在绑定不是 loopback（`127.0.0.1` / `localhost` / `::1`）且 runner 令牌为空时拒绝启动。令牌已设置时：runner 除 `GET`/`HEAD /health` 外都要 runner bearer（所以匿名 `GET /run` 是 401）；`POST /run/:id/respond` 只收 operator 令牌，拿 runner 令牌来批会 401。Hermes 只锁非 GET，`GET /health`、`/skills`、`/executions` 仍开放，platform-api 的只读代理不用带这个令牌。两个令牌都空时（本机 loopback）路由保持开放。platform-api 的 remediation client 在除 `/respond` 以外的调用上带 runner bearer，`/respond` 带 operator bearer；`/health` 不带。agentbridge 的 smoke / nightly 探测和 agentreport 的 nightly POST/GET 同样带 runner bearer。`deploy_mac_mini.sh` 在本机 `bifrost-platform/.env` 缺少非空 `REMEDIATION_RUNNER_TOKEN` 时 exit 1，并把已有的这一行拷到 Mini，不发明值。`deploy_hermes_gateway.sh` 在目标机 `~/bifrost-agent/config/.env` 缺少这一行时 exit 1，不打印那一行。
- 防线：`agent/remediation/src/server.test.ts`（`bindRefusal`、匿名 `GET /health` 200、匿名 `GET /run` 401、带 runner 令牌的 `GET /run` 200、匿名 `POST /run` 401、runner 令牌打 `respond` 为 401、operator 令牌打 `respond` 不是 401、路由栈）。`agent/hermes-gateway/src/server.test.ts`（匿名 `POST /reload` 与 `POST /skills/missing/trigger` 为 401，带令牌的 `POST /reload` 不是 401，路由栈）。`api/internal/remediation/client_test.go` · `TestRunnerClientSendsRunnerAndOperatorTokens`（夹具 `fixture-runner-token` / `fixture-operator-token`，失败信息不打印头的值）。
- 门禁：`agent/remediation` 的 `npm test` → exit 0，7 passed（5 个鉴权 + 2 个 TD-221，脚本在 TD-221 那次提交里才把第二个文件加进 `npm test`）；`npx tsc --noEmit` → exit 0。`agent/hermes-gateway` 的 `npm test` → exit 0，7 passed；`npx tsc --noEmit` → exit 0。`api/`：`go build ./...` → exit 0；`go vet ./...` → exit 0；`go test ./...` → exit 1。失败的两处都不在本分支的 diff 里，origin/main 上已如此：`internal/safego` `TestNoUnguardedGoroutines`（`checklist/prober.go:83`）、`internal/tradevocab` `TestTradeVocabularyOnlyShrinks`（`probe/probe.go` 预算 0）。`internal/remediation`、`internal/agentbridge`、`internal/agentreport` 为 ok。
- 验收：检出 `3621f41e803a6331739d9d3d484147d20ed022b8` 后，`cd agent/remediation && npm test` 与 `cd agent/hermes-gateway && npm test` 都 exit 0；`cd api && go test ./internal/remediation/ -run TestRunnerClientSendsRunnerAndOperatorTokens -count=1` 为 PASS。线上要等 Owner 部署之后：`for h in 192.168.10.50 192.168.10.52; do curl -s -o /dev/null -w "$h %{http_code}\n" http://$h:8781/run; done` 预期 401。`GET /health` 仍是 200。现在的 Mini 进程还是旧代码。
- 要 Owner 批：先在部署机的 `bifrost-platform/.env` 增加键 `REMEDIATION_RUNNER_TOKEN`（新值，和 `PLATFORM_OPERATOR_TOKEN` 不同；本机生成，不提交）。`PLATFORM_OPERATOR_TOKEN` 已经会被拷到 Mini，`POST /run/:id/respond` 认的是它。然后从含本分支代码的 `bifrost-platform` 跑（本道没有跑）：
  - `./scripts/agent/deploy_mac_mini.sh vision@192.168.10.50`
  - `AGENT_ROLE=standby PEER_SSH=vision@192.168.10.50 PEER_URL=http://192.168.10.50:8781 ./scripts/agent/deploy_mac_mini.sh vision@192.168.10.52`
  - `./scripts/agent/deploy_hermes_gateway.sh vision@192.168.10.52`
  Hermes 在 .52。缺键时前两个脚本在拷贝前退出，第三个在目标机 `.env` 没有该键时退出。本机 platform-api 从 `.env` 里 `REMEDIATION_` 前缀带上这个键，加完后 `bdev restart platform-api`。集群里的 platform-api 现在没有 `REMEDIATION_RUNNER_TOKEN`。STG/PROD 的 Secret 机制是 `bifrost-platform-role-tokens`（`k8s/overlays/platform-stg/platform-api-role-tokens.patch.yaml`、`k8s/overlays/platform-prod/platform-api-role-tokens.patch.yaml`，`scripts/k3s/apply-platform-role-tokens.sh`）。要在 Mini 开始拒绝匿名调用之前，把同名环境变量加进这两个 Deployment 和对应 Secret。PROD 的登录令牌环境名是 `PLATFORM_PROD_OPERATOR_TOKEN`，不是 `PLATFORM_OPERATOR_TOKEN`；`/respond` 客户端只读后者。集群 PROD 要能审批，pod 里还得有和 Mini 上 `PLATFORM_OPERATOR_TOKEN` 相同的值，变量名用 `PLATFORM_OPERATOR_TOKEN`。本道没有改 infra，没有 kubectl apply。
- 后续：Hermes 的 `GET /executions` 仍匿名（Fix 范围是非 GET，验收也不覆盖它）。`scan.sh` 的 argv 棘轮没有加，理由同 TD-206。

## TD-221
- Claim：成立。改前 `agent/remediation/src/tools/platformTools.ts:269` 的 `ib_gateway_control` 描述含 mode，`:278` 的 action 枚举是 `reconnect | mode | maintenance`，`:280` 有 `mode` 属性，`:292` 把 `body.mode` 发给插件。同一文件里 ledger refresh 的 `mode: full`（约 `:74`）是另一个工具，没有动。目录文案是 TD-241，本项没改 `FORBIDDEN_ACTIONS` / `AGENT_FACTS` / `CLAUDE.md`。
- 改动：同一分支 · `2bfd46534a5acf2d36b2f5cead2d5a1a492b8821`。该工具只接受 `reconnect` 或 `maintenance`。请求体是 `{}`，没有切换 live/mock 的字段。工具块里不再出现 mode 这个子串。
- 防线：`agent/remediation/src/tools/ibGatewayControl.test.ts`（`mode` 和空动作抛错；从 `platformTools.ts` 切出 `ib_gateway_control` 到 `start_agent_host_deploy` 的那一段，断言不含 `mode`）。
- 门禁：含在 TD-207 那次 `agent/remediation` 的 `npm test`（7 passed，exit 0）和 `tsc --noEmit`（exit 0）里。
- 验收：检出该提交后 `cd agent/remediation && node --import tsx --test src/tools/ibGatewayControl.test.ts`。预期 2 passed。`platformTools.ts` 里 ledger 工具仍有 mode 字样；断言只覆盖 `ib_gateway_control` 那一段。随 TD-207 的 Mini 部署一起生效。没有单独的发版。
- 要 Owner 批：没有（代码随 runner 部署走；部署命令在 TD-207）。
- 后续：无后续（本项）。

## TD-96
- Claim：成立。现行 `scripts/agent-guard/preflight.js` 与草案目录里的 `preflight.current.js` 字节相同（`diff -q` exit 0）。`/control/` 规则只匹配 curl 形态（`preflight.current.js:107` 一带）。`requests` / `httpx` / `wget` / httpie，以及 `sed -i` / `tee` / `cp` / 重定向 / `kubectl patch|edit|apply` 改 scale-zero 与 observe-safe patch，现行文件拦不住。
- 改动：没有提交。只改了 `/Users/vision-mac-trader/Desktop/stocks/REQUEST-td96-preflight-d10-2026-10-06/` 下的 `preflight.proposed.js`、`test.proposed.js`、`test.final.js`、`preflight.diff`、`README.md`。没有改 `scripts/agent-guard/preflight.js`。规则 4 在 guard 文件名出现时增加 `kubectl patch|edit|apply|replace`。测试在原有草案上补了 6 条 DENY：`tee`、`requests.delete`、`httpx.delete`、`kubectl apply` / `patch` / `edit` 指向那两个 patch。`test.final.js` 与 `test.proposed.js` 只差 guard 路径（`preflight.js` 对 `preflight.proposed.js`）。
- 防线：草案 `test.proposed.js` / `test.final.js`。Owner 把 `test.final.js` 拷成 `agent-config/scripts/agent-guard/test.js` 之后，现有的 agent-guard 测试就是棘轮。本道没有起 ci-infra，也没有改流水线（起 PipelineRun 不在本道权限里）。
- 门禁：`node REQUEST-td96-preflight-d10-2026-10-06/test.proposed.js` → exit 0，74 passed / 0 failed（原 42 + 新 32：24 DENY + 8 ALLOW）。
- 验收：同上，再跑一次 `node …/test.proposed.js`，预期 74 passed。确认现行文件未改：`diff -q scripts/agent-guard/preflight.js REQUEST-td96-preflight-d10-2026-10-06/preflight.current.js` 无输出。
- 要 Owner 批：把草案套上现行 guard（本道按指令不做这一步）。在 `bifrost-trade-infra` 里：
  - `cp ../REQUEST-td96-preflight-d10-2026-10-06/preflight.proposed.js agent-config/scripts/agent-guard/preflight.js`
  - `cp ../REQUEST-td96-preflight-d10-2026-10-06/test.final.js agent-config/scripts/agent-guard/test.js`
  - `node agent-config/scripts/agent-guard/test.js`
  工作区根的 `scripts/agent-guard/` 是 infra 里这份的符号链接，拷到 `agent-config/scripts/agent-guard/` 即生效。
- 后续：无后续（草案侧）。套上之后若要 CI 每次跑 `test.js`，那是 infra 流水线的事，本道没有改。

## 其它

- 并行车道的 worktree / 分支没有动。S1 worktree 里没有撞上别的车道正在改的文件。LANE-S2 声明不碰 `api/internal/remediation`，remediation client 只在本分支。
- `go test ./...` 的两处既有失败见 TD-207。没有修（不在本道范围）。
- 工作树 `/tmp/cursor-s1-bifrost-platform` 在推送后已删除。
