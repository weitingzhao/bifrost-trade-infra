# Codex 复核 112 — 冻结协议第一片：复核 109 之后的收尾（platform `3620e17..3466ff9`，infra `77e6b39`）

2026-10-12 00:45 CDT · 只读 · Cursor 实现、统筹方验收 · 结论：可以合并。没有找到会答错的应答；只缺测试的规则 1 条（第三个数据块的长度行没有逐字节的掩码——`chunk*` 的后续重复）。

VERDICT: safe to merge
A RESPONSE THAT IS ANSWERED WRONGLY: not found
RULES THAT ONLY LACK A TEST: 1
固定复核 platform 3466ff9、infra 77e6b39；只写本目录副本，未新写 socket/TLS 服务器或流量整形代码。
109 第二块缺口：closed；scripts/release/freeze_http_vectors.py:455–463，d 为两块、last=0000、一条 trailer，位置和掩码沿用同一生成规则。
重新生成与两份文件逐字节一致；SHA-256 b9873fa5a8611716d576a1b3c8cbf4a6588ee8b6651545d4200367d5d1b77374，两处摘要常量匹配。
api/internal/releasefreeze/http_vectors_test.go:90、scripts/release/test_freeze_http.py:62：基线通过；646 个替换/插入位置、165,376 次字节试验；d 为 92/93 个位置。
独立重植109原错误：两侧点名测试均失败，明确报 d replace 67 0x21；second_go.log、second_python.log，阴性对照通过。
ALPN 硬化：closed；api/internal/releasefreeze/read.go:199 调 closeConn，:174 直接关闭 TLS 的 NetConn；拒绝仍返回原错误。未实测 defaultDial 的 ALPN 分支延迟。
范围：相对 platform 3620e17，read.go 仅上述一行改变，httplang.go、lang.go 不变；相对 infra 合并提交 0aa585d，freeze_gate.py 逐字节不变；H、L、限额和 verdict 无改动。
180,843 份旧语料重跑：Go/Python clear 各 4,623，逐行判定零差异；Python BufferedReader、_Reader、识别器零差异；12,342 组缓冲分割比较通过（go_baseline.log、python_audit.log）。
P2-test：scripts/release/freeze_http_vectors.py:457，四个基础应答仍没有第三个数据块的长度首字节位置条目；这是 chunk* 后续实例的覆盖缺口，当前生产循环正确。
独立植错：httplang.go:283 的 parseChunkSize 前加 `if len(body)==2 && len(line)==2 && line[0]=='!' {line[0]='7'}`；freeze_gate.py:712 对应改写，仅在已收两字节正文时把 ! 当7。
最小应答：M 分成 1、1、7c 三块，第三块长度改成 !c，last=0000、一条 trailer；首字节偏移59，third_chunk_witness.hex；原版两侧拒绝，植错两侧 clear，识别器拒绝。
覆盖证据：植错 Go 现有内存断言通过（8.911 s），Python HTTP/L 九项通过（7.648 s），未植错对应测试亦通过；third_go_memory.log、third_python_memory_final.log、control_*。新增 witness 只记录判定，未计入杀错证据。
建议后续补第三块近失或对重复分块生成性质测试并登记植错；这不是现版答错的应答，不阻止本次两项修复合并。
边界：未宣称完整默认套件通过；一次扩大 Go 选择范围误含 TestFaultInjectionSeams，因 TCP bind 受限失败，随后仅重跑内存子集通过。
END OF REPORT
