# Codex 复核 109 — 冻结协议第一片第 5 轮：复核 108 留下的三处（分支 `w31/td-310-s1`，platform `9cb55cf..45fe03b`，infra `2c807e1`）

2026-10-12 00:03 CDT · 只读两个工作树，在自己的目录里跑副本 · 这一轮由 Cursor 实现、统筹方验收 · 结论：可以合并。没有找到会答错的应答；只缺测试的规则 1 条（第二块和多个零的收尾块没有逐字节的掩码）；另一处该改的（ALPN 不符时的关闭仍会等 close_notify，判定没有错）。180,843 份应答和 148 种送达安排，两份读法 0 分歧。

VERDICT: safe to merge
A RESPONSE THAT IS ANSWERED WRONGLY: not found
RULES THAT ONLY LACK A TEST: 1
108 字节首位：closed；api/internal/releasefreeze/http_vectors_test.go:97、scripts/release/test_freeze_http.py:62，生成位置包含 0。
108 期限第二次核对：closed；http_vectors_test.go:149、test_freeze_http.py:89，全部字节即时可用，120 ms 延迟越过 100 ms；单独删第二次核对，两侧点名测试失败。
108 clear 后迟返：closed；api/internal/releasefreeze/read.go:148、:172，成功拨号后的每个退出均关闭；TLS 直接关闭 NetConn，非 TLS 调 Close。
停止条件的答案：没有找到当前两份实现答错的应答，也没有找到模型中破坏 S、L 或 U 的序列。
审查固定提交：platform 45fe03b、infra 2c807e1；仅本目录副本可写，原工作树和 108 只读；未访问网络、集群或凭据。
证据：108 的 180,843 份应答重新运行；Go/Python clear 各 4,623，逐行 verdict 完全一致；Python BufferedReader 与 _Reader 及识别器亦零差异。
证据：108 的 148 组时序两侧零错误、零二进制差异；12,342 组 Python 缓冲分割比较零差异；穷尽模型及随机内存序列通过。
P2-test：scripts/release/freeze_http_vectors.py:452，三基础应答没有第二块或多零 last 的逐字节掩码；当前实现正确，但位置规则只穷尽基础应答。第二字段行和临时头自己的 CRLF 均有掩码。
最小植错与复现：第二块两位长度首字节 ! 被当成 7；应答为 chunked，第一块 1 + M[:1]，第二块 !d + M[1:]，其余 CRLF 和 0 结尾合规，M 为共享合法 126 字节正文。
植错证据：Go 在 readChunked 的 parseChunkSize 前加 `if len(body)>0 && len(line)==2 && line[0]=='!' {line[0]='7'}`；Python 在对应处同改；原版两侧拒绝、植错两侧 clear、识别器拒绝（second_chunk_witness.hex）。
默认测试证据：植错 Go（仅跳过需 TCP 的 TestRandomSequences）全包通过，19.858 s；植错 Python（排除 12 项 subprocess CLI 用例）157 passed、2 skipped，21.03 s；已知名单的静态检查也通过。
最小修复：增加两个 chunk 且 last=0000 的基础应答，按相同规则生成替换/插入掩码，并把第二块非 HEX 种错纳入两侧名单；禁止网络的用例未执行，不能断言它们也漏检。
P2：api/internal/releasefreeze/read.go:199，defaultDial 在握手成功而 ALPN 非 http/1.1 时仍调用 tlsConn.Close，未统一到“不等待 close_notify”的关闭路径；拒绝 verdict 正确，未发现错误放行。
最小场景／修复：TLS 对端不协商 ALPN 且握手后不再读；改为 closeConn(tlsConn)。迟返是按代码路径推断，本轮未为此新建服务器，未实测该分支延迟。
关闭复核：read.go:148 的 defer 覆盖成功拨号后的正常、错误及 panic 退出，无关闭后读取；非 TLS 接缝仍调用 Close；握手失败关 raw。两侧 0.2 s 和 10 s 的 clear 测试均通过，Go 返回约 0.12 s／6.00 s。
字节规则／摘要：按每段 data 去掉首尾后的严格内部排除下标；a 替换/插入 56/57、c 83/84、i 90/91，共 461 位置、118,016 试验；完整重新生成 0.543 s，两份文件逐字节一致。
共享 HTTP 向量 239,430 字节，SHA-256 daf5e79f9893370e738eb0b5d15a9057caa2a36008fb5e1135aed940ddeaa5f5；两处常量一致，原 L 向量兄弟比对也通过。
种错：Go 42、Python 42，全部经原运行器阴性对照、点名失败与所要求的 evidence 检查；go_mutants.log／python_mutants.log，119.184 s／45.82 s；不是 41（Python 首项打印前带一个点）。
范围核对：生产 Python reader 未改；Go reader 只改 defer 关闭并加 closeConn；httplang.go、L、限额和二进制判定未改。
自检：go build ./...、go vet ./... 通过；离线 Go 包（跳过 TCP 随机部分）19.828 s；Python 离线子集 157 passed、2 skipped、12 deselected，22.36 s。
模型：963 状态、129,206 转移，0.060 s；2,000 随机内存序列通过。原默认整套 Python 162 passed、7 failed、2 skipped，22.79 s；失败全是依赖外部 kubectl/curl 的 TCP 通信，不能宣称整套通过。
整套 Go 重跑：releasefreeze 19.615 s（低于 40 s），该包仅 TestRandomSequences 的 TCP 部分失败，其他包亦有 TCP 受限失败；所以整套未通过。复用了 108 的内存传输适配器，没有新写 socket/TLS 服务器或交通整形代码。
设计须补：将字节类别基础应答扩展到第二块、多零 last，并明确所有退出（含 ALPN 拒绝）也不等待 TLS close_notify。
END OF REPORT
