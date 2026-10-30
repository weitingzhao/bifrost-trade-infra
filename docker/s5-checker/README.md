# W-31 S5 trusted CI contract

设计依据：S5 v3.1 §3.1、§5.1、§6.2。此目录与 `k8s/cicd/tekton/*s5*` 属于受保护构建材料，候选 R 不提供检查器、命令、profile 或可信测试。

`IMAGE_DIGEST` 初始为全零，表示尚未构建。平台嵌入的 `landingci/s5trusted/contract.json` 同步保留占位；运行入口拒绝占位，不能据此启动可采信的 CI。

## 构建与固定

`bifrost-build-s5-checker` 只接受完整、非零的 `infraRevision` 和 `checkerRevision`。后者是单独复核的可信检查器提交 T，不是待验证 R。构建上下文包含两个固定 checkout；Go 按 go.sum 校验模块，Node/Go/TypeScript 归档按 `TOOLS.lock.json` 中的摘要校验。TypeScript 为 5.9.3，不运行 npm lifecycle。运行镜像移除 Go 编译器，包含检查器二进制、hard 子树的 TS/profile/suite 和只读工具。

来源：[Node 官方校验和](https://nodejs.org/download/release/v22.14.0/SHASUMS256.txt)、[Go 官方发布清单](https://go.dev/dl/?mode=json&include=all)；TypeScript SRI 与设计基线 platform/console/package-lock.json 一致。Python base 和 apt 版本沿用已存在的 ci-infra 锁。

构建、推镜像及安装仍是另行批准的核心发布动作。本次只交付文件。构建完成后，复核镜像产物，将 digest 同时填入 IMAGE_DIGEST、两个 Task 的 image，生成并复核平台嵌入合同：

```sh
python scripts/s5/pins.py --ready --output ../platform/api/internal/agentrt/landingci/s5trusted/contract.json
python scripts/s5/pins.py --ready --check-platform ../platform/api/internal/agentrt/landingci/s5trusted/contract.json
```

两个仓库必须作为同一次核心变更发布。不得从候选树、可写 ConfigMap、labels 或创建请求注入 trust root。必须先在真实 Tekton 上确认已解析 spec 的默认字段与嵌入合同一致；未知默认值保持拒绝，不能为通过而通配忽略字段。

## 线 A 提供的内部 CLI

此线不修改 A 的 `rules/s5check` 或 `cmd/s5check`。构建和运行依赖以下最小适配入口；缺入口即失败，没有假成功实现：

* `s5check --ci-materials /opt/s5/s5check /opt/s5/TOOLS.lock.json`：输出 canonical JSON，包含 `profileDigest, toolchainDigest, callersDigest, typesDigest, testsDigest, uiSHA`。所有摘要为 64 位小写 hex，UI 为完整 SHA。`toolchainDigest` 是 TOOLS.lock.json canonical JSON 的 SHA256；其余来自镜像内冻结材料。
* `s5check --ci-request-stdin`：stdin 为 `{schema:2,key:S5CIKey,ciUID,platformGitDir,uiGitDir,policyRoot}`。两个 Git 目录是只读 bare object stores，固定 refs 为 `refs/s5/{base,a,m0,revision}` 和 UI 的 `refs/s5/ui`。不得 checkout symlink 后读取宿主、不得执行候选构建脚本。
* 调用设计 §3.1 的 `CheckS5Candidate(ctx, trustedTreeReader, trustedPolicy, CandidateKey)`，扫描完整 M0/R 及关系，并执行镜像内可信 suite。行为代码必须放到独立子进程，可信 checker 父进程记录受保护断言完成情况；不能把候选 stdout、exit 0、passed.json 当作测试完成。
* stdout 只返回完整 schema-2 `ContentEvidence` 的 canonical JSON；诊断到 stderr，失败退出非零。成功必须 `passed:true, findings:[]`，`files` 为数组（caller-only 可以为空），每项含 `path,beforeBlob,afterBlob`。身份字段严格遵循设计；不添加候选自报字段。成功 evidence 最大 3000 字节，为 Tekton 默认结果限额留空间；超限关闭。

runner 在 Linux/amd64 的独立低权限子进程中执行可信 checker：固定 CPU/文件大小/文件描述符/墙钟上限、seccomp 拒绝网络和命名空间/挂载逃逸、禁止创建新进程组；子进程与其 suite 继承限制。只在父进程验证 JSON、所有 key 绑定、实读树/文件 blob 后写 Tekton results。`/tekton/results` 仅父 uid 可写。候选代码绝不能在该父进程中执行。

树 fetch 与 check 是不同 Task/Pod；fetch 匿名访问固定 Gitea 地址，无凭据回退。check 树 workspace 内核只读，根文件系统只读，没有 kubeconfig、Secret、宿主卷和 push 凭据。ServiceAccount 禁止自动 token，NetworkPolicy 拒绝 check 的 ingress/egress；seccomp 的网络限制不依赖网络策略收敛。

## 线 B 读取接口

平台 `landingci.Client` 新增：

```go
EnsureS5(ctx context.Context, key S5CIKey) (S5RunIdentity, error)
ReadS5(ctx context.Context, key S5CIKey, saved S5RunIdentity) (S5Evidence, error)
```

`S5CIKey` 是设计完整 25 字段（schema=2，generation/ruleVersion 为 uint64；task/attempt/op 为 string）。`Base` 保留原任务 base，传给 Tekton 的 `base` 则明确为 `M0`。canonical key JSON、完整 keyDigest、M0、R、固定 UI、十进制 generation 一起进入参数；run 名为设计规定的摘要前 40 位及 base36 generation。

线 B 必须在锁内先持久化 key/generation/needsS5Evidence，随后调用 EnsureS5，再单独持久化返回的 `{run,uid,keyDigest,generation}`。重启可幂等 Ensure，但 Read 不会自己补造丢失的 UID。任一材料变化或重试必须由线 B 开新 generation；不能修改已有 run。

Read 成功仅返回 `Status == "Succeeded"` 且 `Reason == ""`；Content 为 canonical ContentEvidence、Digest 为其 SHA256。非成功不得转成 VerifiedS5；仍须由线 B 在最终锁内验证当前 ReviewBinding/PatchEvidence/rule/live/quota 等。此接口不做主线授权，也不代替既有 lint/build/test CI。

采信验证使用 Tekton [PipelineRun 已解析 pipelineSpec](https://tekton.dev/docs/pipelines/pipelineruns/) 和 [TaskRun taskSpec](https://tekton.dev/docs/pipelines/taskruns/)，并读取 TaskRun/Pod 的 owner UID、完成状态、实际 imageID、环境、只读 mount 和凭据/host 卷。多页读取不按 labels 或 pipelineRef 过滤；同代任何额外 run 均关闭，新代出现拒绝旧代；失败不会回退旧成功。依赖现有 observer 的 PipelineRun/TaskRun/Pod 读取权限，不新增 RBAC 授权。

`40-admission.yaml` 仅为完整固定 S5 template 增加精确例外；原其他流水线的 pod/SA/参数限制保持原表达式。实际安装前仍须做 server-side admission dry-run。S5 JSON 参数只传环境，从不插入 shell。

## 离线验证与未验证项

```sh
python -m pytest -q scripts/s5
python -m ruff check docker/s5-checker scripts/s5
python scripts/check_admission_guards.py
python scripts/s5/pins.py --check-platform ../platform/api/internal/agentrt/landingci/s5trusted/contract.json
# 初始占位应 exit 1：
python scripts/s5/pins.py --ready
```

Python supervisor 成功对照使用临时 Git 真对象和测试专用假 checker；它证明输送/绑定，不是 P1–P4 检查器验收。macOS 不支持 Linux seccomp/setuid/只读挂载，相关内核测试明确 skip。真实镜像构建、可信 suite、Tekton、admission dry-run、匿名 Gitea 连通性、网络隔离和发布均未在本次实施中执行。
