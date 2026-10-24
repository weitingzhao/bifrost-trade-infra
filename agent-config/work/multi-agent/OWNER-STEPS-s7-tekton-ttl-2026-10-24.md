# 你要做的：Tekton 清理任务的新规则（W-31 4.6 S7 第一步，TD-299，约 3 分钟）

改动在 infra main `29dd7f4`：`k8s/cicd/tekton/pipelinerun-ttl.yaml` 的 CronJob 加第三遍，删一周前结束的单独 TaskRun（webhook 起的 github-sync、mirror-sync，平台的 Dockerfile 刷新），每个任务留最新 5 个；失败 run 的 Pod 从 2 天改为留 7 天。权限（ServiceAccount、Role、RoleBinding）没变。

**为什么要你来**：清单应用流水线在 `cicd` 只许写 Tekton 定义，不许写 CronJob（这个任务的身份能删 run）。所以这一份和以前一样由你用管理员 kubeconfig 应用；`plan_manifest` 在第一步就拒了（`kind ServiceAccount … is not allowed in that namespace`），这是对的。

**先看会删什么**：我用只读身份对线上空跑过（读真集群、删除只记录不发）：PipelineRun 0、Pod 0、单独 TaskRun 108 条，全是 `bifrost-gitea-mirror-sync`，结束于 2026-06-19 到 09-27。清单在我本机 `~/agent-work/tdb/s7-would-delete-20261024T0936Z.txt`。

## 1　只检查、不生效

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git pull --ff-only && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/pipelinerun-ttl.yaml --dry-run=server
```

做完会看到四行，结尾 `(server dry run)`：ServiceAccount、Role、RoleBinding 为 `unchanged`，CronJob 为 `configured`。有 `error` 就停下，回线程说一声。

## 2　应用

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/pipelinerun-ttl.yaml
```

做完会看到 `cronjob.batch/tekton-pipelinerun-ttl configured`，其余 `unchanged`。它每小时第 20 分跑；下一次跑完我读日志核对三行 `… done deleted=… kept=…`，第三行应接近 108。回线程说「S7 应用了」即可。

**回退**：在上一个提交上重新 apply 这个文件：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git show 95a95ec24b1563994b42298e589cd643a8a8bca5:k8s/cicd/tekton/pipelinerun-ttl.yaml | kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f -
```

删掉的 TaskRun 回不来，但它们的日志在 Loki 留 30 天，发布证据在发布记录 ConfigMap 里，不在这些 run 上。
