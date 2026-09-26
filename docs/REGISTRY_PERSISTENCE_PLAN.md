# 方案 · 给 registry 补持久卷（只保留被引用的 + 各 repo 最近 3 个）

> **问题**：`cicd/registry` 的 Deployment **没有任何 volume**，19 个 repo 的镜像全在 pod 的
> 写入层里（containerd snapshotter，节点 `ubt-k3s-01`），pod 自 2026-06-17 起未重启。
> **那个 pod 一旦重建，全部 tag 消失。** 清单 `k8s/cicd/registry/deployment.yaml` 本身就没写 volume
> ——注释是「Session S3 smoke」，一个冒烟测试用的 registry 变成了生产依赖，不是配置漂移。
>
> ⚠️ **风险已升高**：2026-09-26 我把五个节点的 containerd 镜像缓存 prune 到各约 43 个，
> 所以旧 tag 在节点上**不再有副本**。registry 丢内容就只能重建镜像。

## 决定（Owner，2026-09-26）

**只复制被引用的 + 各 repo 最近 3 个 + 移动 tag（`prod`/`stg`/`dev`/`latest`），旧版本回滚目标不保留。**

实测规模（2026-09-26 16:1x UTC，`scratchpad/keepset.py`）：

| | |
|---|---|
| 现状 | `/var/lib/registry` **112.9 GB**，398 个 tag |
| 保留 | **49 个 tag** |
| 丢弃 | **349 个 tag** |
| **复制体积** | **387 个唯一 blob = 5.30 GB**（层已去重，不是各镜像大小相加） |

**21 倍的缩减。** 复制是分钟级，不是小时级。

（2026-09-26 清理了 97 个陈旧的已完成 Job 之后重算：保留集从 55 / 5.99 GB 降到 49 / 5.30 GB。
详见下方「Job 清理」一节 —— 我先前估的「降到约 32」是错的，理由在那里。）

## 前置条件（都要满足才动手）

1. **没有构建在跑。** 这是最要紧的一条 —— 复制完成到切换之间任何一次 push 都会落到**旧** registry，
   切过去就消失。查：
   ```bash
   kubectl -n cicd get pipelinerun --sort-by=.metadata.creationTimestamp -o wide | tail -5
   ```
   2026-09-26 实测这天 `bifrost-build-market-data` 一小时内跑了两次、且 20 分钟内出了新 tag
   （0.41.4 → 0.41.5），**所以那天不能做**。需要一个协调过的安静窗口。
2. **避开这些时刻**：21:05–23:15 UTC（EOD 采集，发版会滚 pod 而排程走的就是它）、
   00:45 UTC（`market_self_heal`）、02:15 UTC（plugin trim）、02:30 UTC（Research 闸门）。
3. `ubt-k3s-01` 至少剩 20 GB（实测剩 259 GB，宽裕）。
4. 保留清单是**当时**重新生成的，不是复用这份文档里的 —— 见步骤 1。

## 为什么不用别的做法

| 做法 | 为什么不行 |
|---|---|
| 直接给 Deployment 加 volume | ❌ **会重建 pod，写入层当场消失** |
| `kubectl exec` 加 volume / ephemeral container | ❌ ephemeral container 不能挂新卷 |
| 拷 containerd 的 overlay upperdir | ❌ 要动运行中容器的写入层，且要摸 containerd 内部布局，太脆 |
| 设 `REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED` 防 push | ❌ 改 env 同样重建 pod |
| `kubectl cp` 113 GB | ❌ 全部流过 API server |
| **新起带 PVC 的 registry + crane 复制 + 切 Service selector** | ✅ 全程旧 registry 继续服务，每一步可回退 |

**切换靠改 Service 的 selector，不是改 Deployment** —— 一条 patch 生效、一条 patch 回退，NodePort 30500 不变，
所以 `192.168.10.73:30500` 这个地址和各节点的 insecure-registry 配置都不用动。

---

## 步骤

### 1 · 重新生成保留清单（不要复用文档里的）

```bash
cd <scratchpad>          # keepset.py 在这里
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
python3 keepset.py       # 打印规模，写出 keepset.json
```

脚本的判据：**被活跃工作负载引用的**（扫全集群 deploy/sts/ds/cronjob/job）
∪ **各 repo 最近 3 个语义版本** ∪ **移动 tag**（`prod`/`stg`/`dev`/`latest`/`main`）。

### 2 · 建 PVC（40 Gi，钉在 ubt-k3s-01）

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: registry-data, namespace: cicd }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources: { requests: { storage: 40Gi } }
```

`local-path` 是 `WaitForFirstConsumer`，所以在有 pod 挂它之前不会 provision ——
下一步的新 Deployment 带 `nodeSelector` 决定它落在哪个节点。

⚠️ **40Gi 只是意图，`local-path` 不强制限额**（见 `docs/STORAGE_CEILINGS.md`）。真实上限仍是节点根分区。
写 40 而不是 6，是给累积留空间；但**累积本身要靠步骤 8 的保留期治，不是靠这个数字**。

### 3 · 起新 registry（标签与旧的不同，先不接 Service）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: registry-v2, namespace: cicd, labels: { app: registry-v2 } }
spec:
  replicas: 1
  strategy: { type: Recreate }          # RWO 单副本，RollingUpdate 会自锁
  selector: { matchLabels: { app: registry-v2 } }
  template:
    metadata: { labels: { app: registry-v2 } }
    spec:
      nodeSelector: { kubernetes.io/hostname: ubt-k3s-01 }
      containers:
        - name: registry
          image: registry:2
          ports: [{ containerPort: 5000 }]
          env:
            - { name: REGISTRY_STORAGE_DELETE_ENABLED, value: "true" }
          volumeMounts: [{ name: data, mountPath: /var/lib/registry }]
          readinessProbe: { httpGet: { path: /, port: 5000 }, initialDelaySeconds: 3, periodSeconds: 10 }
      volumes:
        - { name: data, persistentVolumeClaim: { claimName: registry-data } }
---
apiVersion: v1
kind: Service
metadata: { name: registry-v2, namespace: cicd }
spec:
  selector: { app: registry-v2 }
  ports: [{ name: http, port: 5000, targetPort: 5000 }]      # ClusterIP，仅供复制用
```

验：`kubectl -n cicd get pod -l app=registry-v2 -o wide` 在 ubt-k3s-01 上 Running，
且 `kubectl -n cicd exec deploy/registry-v2 -- wget -qO- localhost:5000/v2/_catalog` 返回空 catalog。

### 4 · 复制（crane，只复制清单里的）

```bash
kubectl -n cicd run crane --rm -i --restart=Never \
  --image=gcr.io/go-containerregistry/crane:latest \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"ubt-k3s-01"}}}' \
  --command -- sh -c '
  for X in $(cat /tmp/pairs); do
    R=${X%%:*}; T=${X##*:}
    crane copy --insecure registry.cicd.svc.cluster.local:5000/$R:$T \
                          registry-v2.cicd.svc.cluster.local:5000/$R:$T || echo "FAIL $R:$T"
  done'
```

`pairs` 由 `keepset.json` 生成（`repo:tag` 每行一个）。实操上把它做成 ConfigMap 挂进去，
或直接把列表内联到脚本里 —— 55 行而已。
**crane copy 是幂等的**，所以重跑只补差异，这点在步骤 5 要用到。

验：`for R in $(repos); do curl -s .../v2/$R/tags/list; done` 与 `keepset.json` 逐个对上。
**任何 `FAIL` 都要查清再往下**，不要带着缺口切换。

### 5 · 切换前补差异（把丢失窗口压到秒级）

```bash
python3 keepset.py            # 重新生成：期间可能有新 tag 进来
# 用新的 keepset.json 重跑步骤 4 的 crane（幂等，只补新的）
```

### 6 · 切 Service selector（**这一步是唯一有影响的动作**）

```bash
kubectl -n cicd patch svc registry -p '{"spec":{"selector":{"app":"registry-v2"}}}'
```

立刻验：

```bash
curl -s http://192.168.10.73:30500/v2/_catalog
curl -s http://192.168.10.73:30500/v2/bifrost-market-data/tags/list
kubectl get pods -A | grep -ci "ImagePull\|ErrImage"        # 必须是 0
```

**回退**：`kubectl -n cicd patch svc registry -p '{"spec":{"selector":{"app":"registry"}}}'` ——
一条命令，秒级。**旧 Deployment 全程不动、不缩容、不删除**，这就是回退的底气。

### 7 · 观察一整个发版周期后才退役旧的

至少跨一次真实构建 + 一次 `kubectl apply -k` 部署，确认推拉都正常。**然后**才：

```bash
kubectl -n cicd delete deploy registry          # 释放 .01 上那 112.9 GB
```

⚠️ **删掉之后那 342 个旧 tag 就永久没有了**（节点缓存已 prune，registry 是唯一副本）。
这是 Owner 已经接受的取舍。

### 8 · 把清单改回仓库，并加保留期

- `bifrost-trade-infra/k8s/cicd/registry/deployment.yaml`：加 PVC + `nodeSelector` + `strategy: Recreate`，
  并把「Session S3 smoke」那句注释改掉 —— 它不再是冒烟测试件。
- **根因是没有保留期**（397 个 tag 无限堆积）。`keepset.py` 已经是一个可用的裁决器：
  把它包成 CronJob，每周算出保留集、`DELETE /v2/<repo>/manifests/<digest>` 掉其余，
  再跑一次 `registry garbage-collect` 回收 blob（`REGISTRY_STORAGE_DELETE_ENABLED` 已是 true）。
  **不加这一条，一年后又是 113 GB。**

---

## 保留清单（2026-09-26 16:5x UTC，Job 清理后重算；执行时仍要重算）

| repo | 保留 | tag |
|---|---|---|
| `bifrost-analytics` | 1 | `0.1.0` |
| `bifrost-api-account` | 2 | `prod` `stg` |
| `bifrost-api-docs` | 2 | `prod` `stg` |
| `bifrost-api-market` | 2 | `prod` `stg` |
| `bifrost-api-monitor` | 2 | `prod` `stg` |
| `bifrost-api-ops` | 2 | `prod` `stg` |
| `bifrost-api-portfolio` | 2 | `prod` `stg` |
| `bifrost-api-research` | 3 | `0.1.4` `prod` `stg` |
| `bifrost-api-strategy` | 2 | `prod` `stg` |
| `bifrost-api-trading` | 2 | `prod` `stg` |
| `bifrost-flex-query` | 4 | `0.6.0` `0.6.1` `0.6.2` `latest` |
| `bifrost-frontend` | 2 | `prod` `stg` |
| `bifrost-market-data` | 4 | `0.41.4` `0.41.5` `0.41.6` `latest` |
| `bifrost-platform-api` | 2 | `prod` `stg` |
| `bifrost-platform-console` | 2 | `prod` `stg` |
| `bifrost-research` | 11 | `0.105.4` `0.106.0` `0.113.0` `0.121.0` `0.121.0-dagster` `0.123.0` `0.124.0` `0.125.0` `0.56.2` `0.97.0` `latest` |
| `bifrost-socket` | 2 | `prod` `stg` |
| `bifrost-worker` | 2 | `prod` `stg` |
## Job 清理（2026-09-26 已做）

我先前说那些上古 tag 是「陈旧 CronJob 钉着的」——**那是错的，没有这种 CronJob**。
真相：它们被**已完成的 Job 对象**钉着，而且 `successfulJobsHistoryLimit: 3` **本来就设了**
（14 + 25 个 CronJob × 3 ≈ 104，数字正好对上）。机制是：**那些 CronJob 已经停跑**
（插件 14 个自 2026-08-29 全部 `suspend: true`，Research 的 30 个也全部 suspended，两边都被 Dagster 接管），
所以「保留最近 3 个」的历史被**永久冻住**，把当年那些 tag 无限期钉着。缺的是 `ttlSecondsAfterFinished`。

做了：

- 删 `plugin-market-data` 44 个冻结 Job（Job 与 Completed pod 清零）；
  14 个 CronJob 全部加 `ttlSecondsAfterFinished: 604800`（7 天），已提交并 apply。
- 删 `research` 53 个（succeeded 且 ≥7 天且非 active），60 → 7。
  **`research` 的 25 个 CronJob 同样没有 TTL，但那是它们的 repo 且在 ArgoCD 自动同步下，没碰。**

**保留集只从 55 降到 49，不是我估的约 32。** 原因值得记下来 ——
剩下的 6 个旧 research tag 全被**该保留的** Job 钉着：

| tag | 引用者 |
|---|---|
| `0.56.2` | `research-harness-29804490`（failed, 25 天） |
| `0.97.0` | `research-harness-29816010` / `29817450`（failed, 17/16 天） |
| `0.105.4` / `0.106.0` / `0.113.0` | `research-harness-*`（成功，**3 / 2 / 1 天**） |
| `0.121.0` | **`research-iv-history-repair`（当天）** |
| `0.121.0-dagster` | 两个活着的 Dagster Deployment |

`research-harness` 每天在跑，**每次钉一个不同的历史版本** —— 那是 Research 会话正在做的历史修复。
所以这些「旧」tag 是**现在正在用的**。如果按我那个估算去砍，会砍掉别人在用的镜像。
**「被引用」这个保守判据救了这一次，别把它换成「只留最近 N 个」。**
2. `registry:2` 没有认证、没有 TLS（各节点按 insecure-registry 配置信任它）。
   这次不改，但值得知道：**任何能到 30500 的东西都能推镜像**。
