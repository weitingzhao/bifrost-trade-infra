# Codex 复核 75 — W-56 清点程序第 7 轮：请求记录的封闭形状、每个应有的请求恰好一组（`e88fd5a..7ffafa5`）

2026-10-11 14:03 CDT · 只读

统筹方处理：**停线**。复核 71 的那一处关了，但又找到一种「采集器不会发的请求被接受并忽略」：JSON 里同一个键写两遍，解析时前一遍被悄悄丢掉。停线条件是这一轮之前写下的（`TASK-7.md`），复核明确回答「成立」，照办：分支 `w31/w56-matrix` `7ffafa5` 不合并，不再补。这是这条线第三次停。新方向见 `PLAN-w56-unattended-prod-2026-10-10.md` 的决定记录 5：不再靠穷举检查一份不可信的录制包，改成采集时由 Owner 的发布密钥签名、重放先验签。

---

VERDICT: fix first
STOP CONDITION: met

范围：`e88fd5a..7ffafa5`；以下路径相对 `scripts/release/prod_matrix/`。未发现 P1，一项 P2 阻挡离线合并。

P2 — `schema.py:539`：JSON 重复键被静默覆盖，仍能接受并忽略采集器不会发送的请求。
最小复现：复制样例 GET `/api`，编号改为 320，添加 `request.body={}` 并重新封存为 A；将原始包文本 S 改为 `'{"attempts":[' + json.dumps(A) + '],' + S[1:]`。
通过实际 `read_declared` 解析后重放，退出 3，输出逐字不变；前一个 `attempts` 中的非法请求完全消失。
同一尝试中先放非法 `request`、再放原始同名 `request`，也退出 3且输出不变。
最小输入防线：所有 JSON 入口使用拒绝重复键的 `object_pairs_hook`，重复字段退出 2，并覆盖嵌套对象。
按预先写定的停止条件，本 lane 应停止补丁，先评审新的分组设计；不能将此项记作合并后跟进。

P3 — `test_round7.py:48`、`test_round7.py:63`：变异计数不能证明全部一致封存或唯一组防线得到覆盖。
复核 1276 个 extra-key：688 个封印一致；588 个把 SAR 正文替换成 `{}`／`null`，封存异常被吞掉，随后由 schema 拒绝。
319 个 twin 全部封印一致，但 SAR 改 user、自检增加正文键都改变 POST 身份，GET 增加正文直接违反形状。
最小修复：区分无法封存与有效封存的变异，并断言拒绝原因；另保留直接验证相同身份两组的测试。本项单独可作为跟进。

Review 71 的 P2：closed；`attempts.py:203`、`identities.py:120`。两个原复现均退出 2，原因是 `unexpected key body`。
六类请求均实测：request／params 额外键、大小写及 Unicode 仿冒 body、params 缺失／null、attempt／result 额外键均退出 2。
相同身份独立重复、成功与失败各一份、重试链加独立副本均退出 2；重复尝试编号也退出 2。
POST 正文额外键被拒绝；spec 额外键、extra、uid、groups 换序产生不同身份，但追加组均被拒绝，没有静默计入或忽略。
读取处未发现未受保护的“取第一组”或覆盖；`chains` 取末次结果是明确的重试链规则。
README `:23`、`:33` 两项声明均存在，符合 collector 和离线前导记录约定；封闭形状声明仍受上述解析漏洞限制。
独立重跑 Round 7 五项测试通过；新增变异为 extra-key 1276/1276、twin 319/319 退出 2。
差异仅涉及指定目录六个文件，工作树干净；禁止 socket 和子进程的审计钩子下 replay 正常退出 3。
全程只读，未调用 HTTP、平台或集群接口，未读取凭据。
END OF REPORT