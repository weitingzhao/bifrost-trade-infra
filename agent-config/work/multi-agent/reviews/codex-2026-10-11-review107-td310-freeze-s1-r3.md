# Codex 复核 107 — 冻结协议第一片第 3 轮：应答头部和分帧写成语言 H（分支 `w31/td-310-s1`，platform `5fbeb3d..04a4530`，infra `7f4e2d4`、`c912ec6`）

2026-10-11 22:03 CDT · 只读两个工作树，在自己的目录里跑副本 · 这一轮的作者是统筹方（Claude），所以由 Codex 复核 · 结论：先修；停线条件成立。P1 一处：Python 一侧的总期限只在每次高层读之前换算成相对超时，缓冲读一次会做多次底层读取，「头立即到、正文第一个字节第 6 秒到、其余第 12 秒到」时 Python 在 12 秒答 `clear`，Go 在 10 秒拒绝。字节层面两份读法 180,843 份自造应答 0 分歧，测试用的识别器与设计一致。P2 三处：Go 的种错运行器没有复制 `testdata`，新加的 16 条种错其实是因为缺文件而失败的；另植的「值里多放行 0x81」没有测试拦住；生产代码里带着被禁止的行为（重定向、第五个成员等），应搬进种错的 `new` 文本。

VERDICT: fix first
A RESPONSE THAT BREAKS THE STOP CONDITION, OR A PLANTED VIOLATION NO TEST CATCHES: found
自造静态原始应答 180,843 份，两读取器均逐份内存运行；二进制差异 0，测试识别器差异 0，接受 4,623 份。另对同一应答运行两种滴流安排，两种安排均发生 Go/Python 差异。
语料含各位置全部 256 种字节替换与插入、删字节与重复行、共享向量随机组合变异（种子 107310）、两种分帧混用、全部界限两侧、截断、尾随响应、排列和空白；生成与结果见 review_cases.py、own_cases.txt、*_verdicts.txt。
停止条件的答案：找到；下述合法 H/L 应答在正文读完前超过总期限，Python 仍答 clear，Go 拒绝，违反 U。
P1 — scripts/release/freeze_gate.py:727、:610、:536、:558：相对 socket 超时没有约束 BufferedReader 内部的多次底层读取，完成后也没有检查总期限。
最小复现字节：b'HTTP/1.1 200\r\nContent-Length: 104\r\n\r\n{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1"},"items":[]}'。
传输安排：头立即送达；正文第一字节在第 6 秒送达，其余 103 字节在第 12 秒送达；一次 GET、TLS 等其余条件可全部成立。每次 recv 等待 6 秒，都短于进入 fp.read(104) 前设置的约 10 秒相对超时。
实测纯内存 RawIOBase + BufferedReader：Python 3.12.7 在 12.008 秒返回 clear；Go 同样安排在 10.000 秒返回超时。缩放到 200ms / 两次 120ms，Python 248.790ms clear、Go 200.875ms 拒绝；这是全部发现的传输判定差异，字节相同。
证据：deadline_probe.py、deadline_results.txt、copies/bifrost-platform/api/internal/releasefreeze/zz_audit_test.go、go_deadline_results.txt；模拟底层读取遵守 socket 的每操作超时，没有联网。
最小修复：在每次底层 recv/readinto 前按剩余总期限设置超时，并在读取结束及返回 clear 前检查期限；只在高层 fp.read/readline 前调用 _arm 不够。补正文末段、最后 trailer 空行滴流测试，不能只慢送状态行。
P2 — api/internal/releasefreeze/mutants_test.go:181、:132：copyPackage 跳过目录，未复制 testdata；新 H 种错的 TestHTTPVectors 在 :73 读文件失败，却被运行器算成捕获。
最小复现：完全不改生产代码，按 copyPackage 的方式只复制 .go 文件（排除 mutants_test.go），运行 go test -run '^TestHTTPVectors$'；具名测试因缺 freeze_http_vectors.json 失败。go_harness_control.txt 保存阴性对照。
最小修复：复制 testdata；每个副本先运行未种错的同一测试并要求通过，再种错；除具名失败外，还核对失败来自预期反例，拒绝缺夹具和测试准备失败。
抽查两侧新增条目的前十项：line-1025、fields-65、interim-9、length-5-digits、hex-5-digits、bare-lf、reason-without-sp、field-text-wide、token-wide、chunked-with-length；均实际削弱 H。
Python 十项均使 test_http_vectors 因预期应答误放行而失败；Go 十项原运行器均先缺文件，补齐夹具后十项均使 TestHTTPVectors 因相应规则失败。见 python_mutant_samples.json、go_mutant_samples.txt；没有把编译失败当捕获。
P2 — api/internal/releasefreeze/httplang.go:63、scripts/release/freeze_gate.py:601：另植“ftext 额外允许 0x81”，在原 return 前增加早返回，保持种错清单的 old 字符串不变；所有所运行的离线默认测试仍绿，两侧都误放行。
复现字节：b'HTTP/1.1 200\r\nX: \x81\r\nContent-Length: 104\r\n\r\n{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1"},"items":[]}'；识别器拒绝，种错两侧 clear。补每个语法字节位置的完整字节类别覆盖；证据 own_mutants/、own_mutant_*_confirm.txt、mutant_go_verdict.txt。
上述自植种错仅证明离线测试盲点，未宣称完整默认套件无测试捕获；本次停线依据是已实测的 P1 原代码反例。
逐条核对 H（Go 路径前缀 api/internal/releasefreeze/；Python 路径前缀 scripts/release/；下表均为原文件行号）：
| 产生式 / 限制 | Go 执行点 | Python 执行点 | 结论 |
| --- | --- | --- | --- |
| line、CRLF、含 CRLF 的 1024 | httplang.go:79 | freeze_gate.py:609 | 字节边界一致，裸 LF / 无 LF 拒绝 |
| status(c)、三 DIGIT、SP、ftext | httplang.go:102 | freeze_gate.py:620 | 与两支产生式一致 |
| field、tchar+、冒号、ftext* | httplang.go:128 | freeze_gate.py:639 | 无 obs-fold、非 ASCII 值拒绝 |
| 名字仅 A–Z 折叠、值仅裁 SP/HTAB | httplang.go:67、:142 | freeze_gate.py:605、:649 | 一致，无 Unicode 折叠 |
| head、0–64 field、任何 head 禁 CE | httplang.go:153；read.go:245 | freeze_gate.py:657、:544 | 临时头也检查 CE |
| response、100/102/103 至多 8、最终 200 | read.go:238；decision.go:44 | freeze_gate.py:539、:324 | 最终非 200 不放行；无其他 1xx |
| body(a)、唯一 CL、无 TE、1–4 DIGIT、≤4096、完整 n 字节 | httplang.go:192、:232 | freeze_gate.py:674、:707 | 字节判定一致；期限另见 P1 |
| body(b)、唯一 chunked、无 CL、1–4 HEX、非零块、data CRLF、≤4096 | httplang.go:209、:273 | freeze_gate.py:689、:747 | 拒扩展；零值等价于 1–4 个 0 |
| last、trailer 0–64 field、禁 CE/CL/TE、最后空行 | httplang.go:308 | freeze_gate.py:761 | 截断不放行；最后空行仍受 P1 影响 |
识别器核对：freeze_http_vectors.py:106–109 用 \A/\Z；:121 限 1024，:138 限 64，:156 限 8 并检查每个 head 的 CE；lower()/strip(b" \t") 仅作用于正则验证过的 ASCII，int() 仅作用于已匹配的数字/HEX；body_of、clear、in_l 与 H/L 未发现偏差。
生产 H 路径无 lenient 数字/空白/大小写解析；Go strconv.Itoa 只用于拒绝显示，TrimSpace 仅令牌或休眠重定向路径；Python latin-1 解码不会抛 UnicodeDecodeError，readline 有 1025 上限。显示 JSON 不参与 clear 判定。
H 的适用性：普通 Kubernetes 应答形状测试通过；互斥 CL/TE、唯一分帧、数据 CRLF 和完整 trailer 阻断所查走私近失。响应后的字节按设计忽略，连接随读结束关闭；未发现 H 与接收正文切分不一致或字节截断被原代码放行。
全性与界限：最多 9 个 head、各 64 field、64 trailer、每行 1024、正文 4096；一字节块至多 4096 个，所有正常读取推进或失败。没有发现字节输入导致无界分配或逃出恢复边界；Python 缓冲滴流破坏时间界限。
模型：963 状态、129,206 转移、两个阴性对照通过；2000 随机序列的内存阶段通过，未找到模型内 S/L/U 反例。模型的抽象传输故障没有揭示 P1 的真实读取时序。
验证限制：Go 所选纯离线默认测试通过（1.178s，含 678 L 向量及共享文件核对），Python HTTP/L 默认测试 6 项通过；完整套件含本地监听，随机测试的监听被沙箱拒绝，因此未完成整包 <40s 独立验收。VERIFY.md 的 1.968s 仅是作者声明；Python 3.11 本机未找到，未执行该版本。
范围与纯度：核对指定提交，平台改动均在 releasefreeze，infra 两次改动均在 freeze 文件；cmd/ 无新包引用，生产 encoding/json 仅 display.go；共享向量逐字节相同。原工作树保持干净，所有改动只在本审查目录。
第 7 项评级 P2：read.go:272 / freeze_gate.py:561 的重定向、lang.go:80 / :141 的第五项和重复 R、freeze_gate.py:431 的 _per_operation_deadline 等禁止行为不宜放进生产包；迁到种错 new 文本。应答、环境变量、零值及 Gate 测试接缝不能打开常量开关；Python _META_EXTRAS 可被执行中的代码修改，但没有外部输入入口，这不等于字节可达漏洞。
设计必须增加：缓冲读取每次底层 I/O 都遵守同一个绝对期限、完成后再检查期限，以及“头快、正文/最终空行慢”的跨读取器时序反例和未种错副本必须先通过的种错阴性对照；保留现有 H/L，不放宽期限。
END OF REPORT
