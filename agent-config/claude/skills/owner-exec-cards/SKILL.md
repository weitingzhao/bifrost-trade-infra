---
name: owner-exec-cards
description: >-
  怎么用平台的卡让 Owner 在手机上批、由集群里的执行口去跑：apply_manifest 的卡、owner_run_command 的执行卡、
  node-run.sh 渲染的节点卡。Use when a step needs a write you cannot do with a tier-B platform action,
  when about to call request_action, when a card failed or went stale, or when you are tempted to ask the
  Owner in a thread to run, click or "亲口放行" something.
---

# 平台的卡：什么时候建、怎么建、批了之后

出处：2026-11-19：要 Owner 跑的脚本应走执行卡，不该让他去终端执行。那两天平台上有 43 张卡，驳回 0 张，多数是手续；还有几条线在线程里请他放行、到终端执行。
机制本身（执行口在哪里跑、手里有什么、哪些命令会被拒、结果怎么读）只写在 `agent-config/OWNER_EXEC.md`。这一页讲的是判断和做法，两边对不上时以那一页为准。

## 先判断：要不要卡

按顺序问，前一步能办就停在那一步：

1. **平台有现成的 B 级动作吗？**（`CLAUDE.md` §3 的对照表：`plan_manifest`、`rollout_restart_deployment`、`start_pipeline_run`、`delete_pod`、`run_probe_pod`……）有就直接调，不建卡。
2. **apply 一份清单？** 先 `plan_manifest`，**等 plan 跑完**（`wait_for_pipeline_run`，看 `results.objects`），再 `request_action apply_manifest`。签名规则覆盖时它会直接执行，回给你 `apply_run`，不出卡。没覆盖才出卡。
3. **平台动作做不了、又确实需要管理员级写入？** 才建 `owner_run_command`。它是后路，不是常用的路。
4. **要进某台节点？** 用 `scripts/owner-exec/node-run.sh render` 生成命令全文（见 OWNER_EXEC.md「要进某台集群节点」），能用设备档就不用主机档。

建卡之前过一遍 `owner-decision-check`：是你自己能定的术和器，就自己定，不建卡；是规则逼的手续，卡里写明是哪条规则逼的。

**不要做的事**：
- 不在线程里请 Owner「亲口放行」「到终端跑一下」「去 Console 点一下」。他要动手的事都是一张卡，他在手机上批。auto mode 或 preflight 拦下的才例外（那是 harness 的规矩，见 `CLAUDE.md` §5），而且照规矩停下来报告。
- 不替他批，不调审批接口，不用浏览器去点审批页（preflight 会拦）。
- 不建了卡就停下来等：建完接着做不依赖它的事，批了再接。
- 他说了「去睡了」就不建卡（推到他手机上），把卡备好，醒了再建。

## 建卡：一张卡要过的检查

| 检查 | 为什么 | 出过的事 |
|---|---|---|
| plan 跑完再建 apply 卡 | 没跑完的 plan 卡面是「0 objects」，规则不放行，就成了一张白等的卡 | #634（11-19） |
| 对比集群现状和 main 上**整份**文件，逐段看 | 整份 apply 会把别人改了没 apply 的东西一起带上去 | 记忆 `lesson_full_apply_carries_unapplied_changes` |
| 一批一张：同一件事的几个文件放进一次 plan（同一目录）或一张卡 | 一张卡就要他看一次 | #636 / #637 本可合成一张 |
| 不建重复卡；卡失败了先读日志 | 重复卡他要批两次，失败的卡再批也是失败 | #638 批了仍失败：批之前 main 又动过这个文件，平台按「渲染结果不同」拒绝了。要按 main 头重新 plan、建新卡（#639），不在失败的卡上反复批 |
| 卡里钉的镜像，渲染时核对 registry 里还在 | 卡等批的时候镜像可能已被清掉，批了也跑不起来 | node-run 渲染时会做这个检查（`NODE_RUN_SKIP_IMAGE_CHECK` 只给 selftest 用）；记忆 `lesson_deferred_cards_pin_must_be_checked` |
| `owner_run_command` 的 `params` 里要有 `reason`（一句英文） | 没有它建卡会被 400 拒 | 11-19 #640 第一次建卡 |
| 执行口写得了这个对象：集群级对象它只许写 PriorityClass 和 Node（准入策略 `bifrost-owner-exec-no-trade`），ClusterRole、ClusterRoleBinding 之类会被拒；能用命名空间里的 Role 就用 Role | 批了也执行失败，白等一轮 | #640（11-19）改 ClusterRole 被拒，改成 cicd 里的 Role |
| 命令自带内容（heredoc），不引用仓库里的文件 | 执行口手里没有任何检出 | OWNER_EXEC.md「命令在哪里跑」 |
| 命令能重跑，结论放在最后几行 | 卡只存输出最后 2048 字节；执行口中途没了会再跑 | 同上 |

## 卡面怎么写

`reason`（卡的理由）用白话，三段，第一段最重要：

```
改了什么：<会改哪个对象的哪几处，改完是什么样；和 main 的哪个提交一致>
批了以后谁因此能做什么新事：<多数是「没有人获得新能力」，再写省了什么、快了什么>
为什么要你：<哪条规则逼的手续（例：platform-rbac 不在 Argo 下，applier 不写 RBAC），或它属于法、六类里的哪一条>
没做的检查：<照实写；没有就写「无」>
```

「为什么要你」写**保护的是什么、这次会不会造成那种坏事**，不写「规则不让」（`CLAUDE.md` §5）。
`rollback` 写一条能照着执行的回退；撤不了就写撤不了。`work_id`、`requester_thread` 都填上。

## 批了之后

- **谁来跑**：`apply_manifest` 由平台的 apply 流水线跑；`owner_run_command` 由集群里的执行口 `owner-exec` 跑，他输了 6 位码才跑。不用你做任何事。
- **怎么知道批了**：卡批了不会叫醒你的会话。等的时候起一个后台检查，盯它要改的那个对象（例如 `kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml get ...` 看对象有没有出现、字段变没变），或在下一次干活时用 `get_request` 读卡。不要在前台空等。
- **读结果**：`get_request` 看 `status` 和 `execution`（`exit_code`、`output_tail`）。`apply_manifest` 的卡失败时，读 `error` 里那次 apply run 的日志（`get_delivery_run_logs`）。
- **自己核对生效**：`executed` 只说明退出码是 0。要自己读集群：对象在不在、字段对不对、Pod 起没起来。
- **记账**：每张规则逼出来的卡，在自己线的笔记里记一行：卡号、哪条规则、等了多久。这是给 Owner 判断「哪些卡可以换成记录」的依据。

## 常见情况怎么走

| 情况 | 走法 |
|---|---|
| cicd 里改 Pipeline、Task、TriggerTemplate、TriggerBinding、EventListener | plan → 等 plan 跑完 → apply。applier 应用过的对象直接执行，不出卡 |
| cicd 里第一次创建上面这几种对象 | plan → apply，会出卡（签名规则要求「applier 应用过」） |
| cicd 里改 CronJob、Deployment、PVC | `owner_run_command`，命令用 `kubectl get -o json | python3` 只改那一处，找不到要改的那一处就退出（#631 的写法） |
| 改 RBAC（`k8s/platform-rbac/`） | `owner_run_command`，只 apply 改到的那个对象，先对比现状（#640 的写法） |
| 节点上读 SMART、量目录大小 | `node-run.sh render --tier device ...`；做不了才用主机档 |
| 卡等很久没人批 | 不催，不在线程里问，接着做别的。要改什么就撤卡重建，不要再建一张一样的 |
