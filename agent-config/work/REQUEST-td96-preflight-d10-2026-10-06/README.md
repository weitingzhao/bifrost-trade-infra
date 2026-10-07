# TD-96：preflight D10 闸门补洞（待 Owner 审阅后应用）

2026-10-06。`preflight.js` 是 guard 文件，按规矩由 Owner 改，这里只放修改稿。

## 问题（第 2 轮扫描实测）

D10 的三条规则只认得特定写法，下面三种都会被放行：

| 规则 | 现在只认 | 漏掉的写法（实测 ALLOW） |
|---|---|---|
| 2. Monitor `…/control/*` 写操作 | `curl -X POST` / `curl -d` | `requests.post` / `httpx.put` / `requests.delete` / `httpx.delete`、`wget --post-data` / `--method=POST`、`http POST`（httpie） |
| 3. daemon 扩容 | `kubectl scale --replicas=N` | `kubectl patch` / `edit` / `apply` 把 daemon 副本写成大于 0 |
| 4. 改动 guard 文件 | `rm` / `mv` / `truncate` / `kubectl delete` | `sed -i`、`tee`、`cp`、`>`、`kubectl patch` / `edit` / `apply` 指向 scale-zero / observe-safe patch |

## 改了什么（`preflight.diff`，只动 `d10Rules` 的规则 2–4）

- **规则 2**：除了 curl，还认 wget 的 `--post-data / --post-file / --body-data / --method=POST`、httpie / xh 的 `http POST`、
  代码里任意对象上的 `.post( / .put( / .delete( / .patch(`、`.request('POST'`、`fetch(…, {method: 'POST'})`、
  urllib 带 `data=` 或 `method='POST'`、PowerShell `Invoke-WebRequest -Method Post`。
  仍要求同一条命令里出现 `/control/` 或 `/account-sync/control/` 路径，所以只读 GET 和对其他路径的 POST 不受影响。
- **规则 3**：`kubectl patch / set / apply / replace / edit` 指向 daemon、并把副本数写成大于 0（`--replicas=N` 或 JSON/YAML 里的 `"replicas": N`），同样拦截。
  缩到 0 和 `kubectl get` 照常放行。
- **规则 4**：guard 文件名出现时，`sed -i`、`perl -i`、`>` / `>>` 重定向、`cp / ln / tee / install / rsync / dd`、
  `kubectl patch / edit / apply / replace`、`git rm / mv / checkout / restore`、`unlink / shred`、代码里 `open(…, 'w')` / `write_text` / `writeFileSync` 都拦。
  只读（`cat`、`grep`、`sed -n`、`git log`、`git diff`、`kubectl get`）放行。按「D10 宁可误报不可漏报」：拿 guard 文件当 `cp` 的源也会拦。

## 测试

`test.proposed.js` 是现在的 `test.js` 加 32 条新用例：24 条应拦（requests/httpx 的 post/put/delete、wget、httpie、sed -i、tee、cp、重定向、kubectl patch/edit/apply 各一条），8 条同类只读写法不得误拦。

```
node test.proposed.js      # ✓ 74 通过 / 0 失败（原 42 + 新 32）
```

原文件对原测试：42 / 42 通过。草案相对 2026-10-06 稿补上了 `requests.delete`、`httpx.delete`、`tee`，以及 `kubectl patch|edit|apply` 直接改 scale-zero / observe-safe patch。`preflight.js` 本体未改。

## 怎么应用（Owner）

在 `bifrost-trade-infra` 的干净 checkout 里：

```bash
cp ../REQUEST-td96-preflight-d10-2026-10-06/preflight.proposed.js agent-config/scripts/agent-guard/preflight.js
cp ../REQUEST-td96-preflight-d10-2026-10-06/test.final.js agent-config/scripts/agent-guard/test.js
node agent-config/scripts/agent-guard/test.js
```

`test.final.js` 与 `test.proposed.js` 只差一行（指向 `preflight.js`）。基线是 infra origin/main 上 `753753e`（2026-10-02）的 `preflight.js`。
应用后告诉我，我把 TD-96 从 `TECH_DEBT.md` 删掉，并在 `RATCHETS.md` 的 preflight 一行写明新增覆盖。

## 改完仍然挡不住的（写清楚，免得高估）

preflight 按命令文本匹配，是纵深防御的一层，不是唯一的闸门：

- **两步走**：先用 Write 写一个脚本文件，再 `python3 /tmp/x.py` 执行。执行那条命令里没有 `/control/` 字样，文本规则看不见。
- **拼接或编码的路径**：例如 `'/con' + 'trol/arm'`、base64。
- **直接打开 socket**：`nc`、`telnet`、`openssl s_client`。

真正挡住实盘的是另外两层：monitor 写接口要求 Operator 登录（TD-23，10-02 上线），以及 STG / PROD 的 daemon 副本被 overlay 钉在 0 / 只观察（spine D10）。
