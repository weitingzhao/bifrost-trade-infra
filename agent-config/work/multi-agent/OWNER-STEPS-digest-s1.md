# 护栏 ⑤ 第 1 片（⑤-11）：把两个构建任务的新定义应用到集群（要你动手的一条命令）

写给 Owner。一条命令，做完不用回话：统筹方用只读身份自己看结果，再发一次测试环境来验证。

2026-10-13 凌晨写成。命令由统筹方逐项核对，并交 Codex 只读核对（结论见文末）。

## 这一步是什么

平台发测试环境和正式环境时，共用两个构建任务（`bifrost-kaniko-platform-api-stg`、`bifrost-kaniko-platform-console-stg`）。这一步让它们在构建完之后多记一样东西：推上去的那份镜像的摘要。每个任务多一个结果、多一个参数，别的都不变——镜像推到哪、怎么部署、两条流水线本身都和今天一样。

它是「正式环境直接用测试环境验过的镜像」的第一块：先让系统记得每次构建出来的到底是哪一份。

## 做之前（统筹方核对后在线程里说「可以做 ⑤-11」）

- 没有平台的发布在跑，没有未结的正式环境发布单。
- 线上这两个任务的定义等于主线上改之前的版本（2026-10-12 23:20 量过一次，做之前再量一次）。

## 命令

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; a=k8s/cicd/tekton/task-kaniko-platform-api-stg.yaml; c=k8s/cicd/tekton/task-kaniko-platform-console-stg.yaml; git show d1495c7:$a | kubectl apply --dry-run=server -f - && git show d1495c7:$c | kubectl apply --dry-run=server -f - && git show d1495c7:$a | kubectl apply -f - && git show d1495c7:$c | kubectl apply -f - )
```

- 它在一个括号里临时用你的管理员身份（你的终端默认连的是本机 Docker Desktop，不是集群；括号结束后终端不受影响）。
- 两个文件直接取自主线上固定的那个提交 `d1495c7`，不依赖你本地检出目录的状态。
- 先对两个文件各做一次服务端试算，两次都过了才真正应用。任何一步失败，后面的都不执行。
- 应当看到四行：两行 `task.tekton.dev/… configured (server dry run)`，两行 `task.tekton.dev/… configured`。

## 做完之后会怎样

- 集群里只变两个对象：`cicd` 里的这两个 Task。两条流水线、别的任务都不变。
- 下一次平台构建（测试环境或正式环境）会多记一个结果。写不出这个结果时，构建那一步会失败——所以统筹方在你应用之后**立刻发一次测试环境**来验证，量三样是否相等：构建记下的摘要、镜像仓库回的摘要、测试环境的 Pod 实际在跑的摘要。
- **这次验证通过之前，统筹方不建任何正式环境的平台发布单。**

## 撤回

把两个任务恢复成改之前的定义（取自改之前的主线提交 `d5154ea`）：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; a=k8s/cicd/tekton/task-kaniko-platform-api-stg.yaml; c=k8s/cicd/tekton/task-kaniko-platform-console-stg.yaml; git show d5154ea:$a | kubectl apply -f - && git show d5154ea:$c | kubectl apply -f - )
```

撤回之后构建不再记摘要，其余和今天完全一样。已经发出去的镜像和正在跑的东西不受影响。

## 统筹方已核对的

- `d1495c7` 里这两个文件各自只比 `d5154ea` 多 4 行：一个结果声明（3 行）和一个参数（1 行）。实现者 Cursor，独立复核 144（Codex）：可以合并，没有必须改的；六处种错都被测试拦住。
- 这个集群上已有两次成功的构建用同一个 kaniko 版本、同一个参数记下了摘要（`bifrost-build-ib-gateway`，10-07 和 10-10），值是 `sha256:` 加 64 位十六进制，没有换行。
- 2026-10-13 00:13 只读量到：没有未完成的流水线运行；最近一次测试环境的平台发布（21:46）成功。

## Codex 的只读核对

（待填：核对结论和要求改的地方。）
