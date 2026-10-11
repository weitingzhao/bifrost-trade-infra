# Codex 复核 79 — TD-310：把 Owner 的发布密钥编成信任锚（platform `17136ba..a55b2cc`，infra `allowed_signers`）

2026-10-11 15:14 CDT · 只读

统筹方处理：先改，信任锚不单独上线。指纹、签名人文件、两个命名空间都核对无误；但有了锚之后，冻结和解冻这一对里有两处变得够得着：同一秒内的两次冻结 `frozen_at` 相同，旧的解冻签名可以重放；解冻在核对和写入之间没有条件，可能把一次更新的冻结盖成「未冻结」。这两处在锚为空时走不到（冻结本身被拒）。任务书 `TASK-2.md`：解冻签名绑定到那一次冻结的标识，写入以核对时的对象为条件；另把锚的测试改成和签名人文件对指纹。停线条件：再发现一种不经 Owner 新签名就能解冻的办法，修一轮；第二次就停，锚不上线，冻结和解冻的协议先出设计。

---

VERDICT: fix first

P2 — `api/internal/releasepolicy/write.go:83`：启用锚后，同秒冻结可重放旧解冻签名。静态复现：固定 `Now=T`，Freeze A → Owner 签名解冻 A → Freeze B → 重交 A 的签名；两次 `frozen_at` 相同，校验通过，历史记忆也不拒绝相等值。最小修复：原子分配严格递增的冻结标识，并让解冻签名绑定该标识；补同秒重放测试。

P2 — `api/internal/releasepolicy/write.go:108`、`api/internal/delivery/release_policy_facts.go:60`：解冻校验与写入之间存在竞态。静态复现：Unfreeze 读取 A 并验签 → Freeze 写入较新的 B → Unfreeze 的 writer 重新 GET B，却用 A 的解冻数据覆盖它。平台历史可能仍阻止发布，但 Tekton 只读对象，会接受这个 `false` 对象。最小修复：写入必须以验签时对象的 resourceVersion 为条件，冲突即拒绝并重新校验。

P3 — `api/internal/releasepolicy/anchor_test.go:12`：测试检查前缀、base64 和 32 字节长度，却不能发现格式正确的错误指纹或清空常量。复现：替换成另一合法 SHA256 指纹，测试仍通过。建议在 sibling infra 存在时用 `SignerKeys` 解析公钥并比较指纹；CI 的 `k8s/cicd/tekton/pipeline-ci-platform.yaml:83` 同时等待 `clone-infra`，避免检查被跳过。

核对结果：
- 实算公钥指纹为 `SHA256:pzjcenBSbCbgIoqamoQLsvlxELfp4ikcLbvp164Eel8`，与常量和 brief 完全一致。`allowed_signers:4` 是合法 Ed25519 行，符合 `SignerKeys` 的解析路径。
- 两个 namespace 恰为 `bifrost-release-policy`、`bifrost-release-unfreeze`，与脚本签名及平台验签一致；平台不需要部署第二份公钥文件，直接从签名取公钥并核对编译指纹。
- 新增能力是 operator 可冻结、提交 Owner 已签的解冻或策略，以及有效策略下的 C 级自动审批。按 brief 所述当前未安装策略，单凭锚不能自动批准发布；其他密钥签名仍被拒绝。
- 策略拒绝过期和早于当前策略的签名，允许同一策略重装；并非所有旧签名都禁止重交。解冻通常绑定当前 `frozen_at`，但上述同秒与竞态问题破坏了这项保证。
- 正常解冻链路完整；最新冻结记忆不可读或比当前记录更新，仍会阻止解冻后的放行。Tekton 当前只校验对象形状，不独立验签。
- 私钥丢失或非空指纹错误时仍然可冻结，却无法正常签名解冻。`docs/RELEASE.md:156` 的 Owner break-glass 三对象步骤仍适用；先恢复冻结对象并清除 PROD/STG 历史，再修锚发版。仅回滚为空会拒绝新冻结，不能解除已有冻结。

仅进行了只读代码审查和内存指纹计算；未运行 Go 测试、脚本或任何 HTTP／平台／集群调用。
END OF REPORT