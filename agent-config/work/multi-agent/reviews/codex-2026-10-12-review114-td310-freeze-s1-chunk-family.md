# Codex 复核 114 — 冻结协议第一片：分块用例改由程序生成（platform `3466ff9..c559018`，infra `908dedb`）

2026-10-12 06:59 CDT · 只读 · Cursor 实现、统筹方验收 · 结论：可以合并。没有找到会答错的应答。只缺测试 1 条（第七个数据块的长度行——同一个分块循环的下一次重复）：按事先写下的做法记为接受，不再开轮次，除非找到会答错的应答。

VERDICT: safe to merge
A RESPONSE THAT IS ANSWERED WRONGLY: not found
RULES THAT ONLY LACK A TEST: 1
固定复核 platform c559018、infra 908dedb；只在本目录副本运行，未新写 socket/TLS 服务器或流量整形代码。
scripts/release/freeze_http_vectors.py:449：独立重算种子 31020282363 的 64 位 LCG；k=1..6、无放回切点、1..4 零循环、带/不带 trailer 均符合规则，k3 为 1、1、124 字节。
scripts/release/freeze_http_vectors.py:513：逐位置独立核查，无抽样缩减；2,654 个替换/插入位置、679,424 次字节试验；生成文件 403,600 字节。
两仓向量与本地重新生成结果逐字节一致；SHA-256 819e95a595677d4114368528a7a8c1c4a9fd3a27bf07946f461c6ae8cd1b5b36，两处常量匹配（generation.log）。
api/internal/releasefreeze/http_vectors_test.go:90、scripts/release/test_freeze_http.py:62：基线通过；Go 内存子集含语料 9.536 秒，Python HTTP 六项 44.498 秒、L 三项通过（并行负载下计时）。
112 第三块缺口已关闭：独立重植原错误，两侧点名测试失败于 k3/k3t replace 73 0x21；未植错基线通过（third_go.log、third_python.log）。
api/internal/releasefreeze/httplang.go:283、scripts/release/freeze_gate.py:712：对照 platform 3466ff9 / infra main，两个 reader 及 L、decision 文件逐字节未变；完整提交差异只含测试/向量/生成器，H 识别器、限额和 verdict 未变（scope.log）。
180,843 份旧语料重跑：两侧 clear 各 4,623，逐行判定零差异；Python BufferedReader、_Reader、识别器零差异；12,342 组缓冲分割通过（go_baseline.log、python_audit.log）。
P2-test：scripts/release/freeze_http_vectors.py:469，家族止于六块，未覆盖第七块长度行的对应位置；这是同一 chunk 循环的后续实例覆盖缺口，按 brief 接受、不阻塞合并。
独立植错：上述生产循环仅在 len(body)==6、两字节长度行首字节为 ! 时将其改为 7；M 分成六个单字节块及余下 120 字节，第七块 !8 在偏移 97，last=0000、带 trailer（seventh_chunk_witness.hex）。
原版 Go/Python 均拒绝此应答；植错后两侧 clear、识别器拒绝；既有 Go 内存子集与 Python HTTP/L 八项仍通过，新增 witness 未计入杀错证据（seventh_go.log、seventh_python.log、*_witness_*.log）。
边界：未运行需要 TCP/TLS 服务器的默认完整套件；P2-test 描述的是植错版答错，未发现本次提交原版答错的应答。
END OF REPORT
