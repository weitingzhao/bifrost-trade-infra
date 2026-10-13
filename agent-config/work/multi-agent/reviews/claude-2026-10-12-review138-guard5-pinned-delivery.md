VERDICT: fix first
A SEQUENCE FOR (a)–(f): found
RULES THAT ONLY LACK A TEST: 1

（复核 138，Claude 的子代理，只看 platform `f6738e6`；由统筹方按交回的全文存盘。方法：一个带状态的假 Gitea，同样的 2,316 个调用在 main `26a10b5` 和分支的副本上各跑一遍逐条比对。真 Gitea 的行为都没实测。证据在 `~/agent-work/claude-review-138/`。）

一问的答案：平台两条流水线（本片的目标）上，(a)(d)(e)(f) 没找到；(c) 没有哪个 main 能建的 run 变了或被误拒，只是多了同步和等待；(b) 有一条，是任务书保留的规则带来的（P3 第一条）。找到的 (a)(c)(e) 都在 Trade 一侧，而且只在「`bifrost-trade-socket` 的镜像有应答」这个状态下出现。新测试正是按这个状态写的；线上这个镜像已删，所以现在被盖住。

**P1**：无。
**P2（Trade 的表有两处不对，本片在 Trade 上的承诺线上不成立）** `supply_chain.go:75-76,80`：表里 deliver-stg 的 `bifrost-ui` 写的是 `revision`，而流水线定义克隆 ui 用的是 `uiRevision`；表和仓库清单里还留着 `bifrost-trade-socket`（`:48,:57`），两条流水线都不克隆它，它已从 Gitea 清除。线上后果：socket 的探测永远是「不知道」，按「有一处不知道就不拦」的规则，deliver-stg、deliver-prod 和所有走兜底清单的流水线什么都拦不住，也从不同步，main 和分支一样。socket 有应答时：`release.sh prod` 的真实请求体（顶层 `revision=main`，`params.revision=<core sha>` 加各仓库的 SHA）在 main 上建 run，在分支上被拒，拒绝里点的还是一个不克隆的仓库；同一状态下 `bifrost-deliver-stg revision=main params.uiRevision=<不存在的 ui sha>` 照样建 run。
**P2-test** CI 的缺失路径没有测试：把 `ref_preflight.go:258-260` 的提前返回删掉，整包照过。
**P3**：① 「有一个仓库不知道，就一个都不拦」（`ref_preflight.go:255`）：platform 的提交查询返回 500、而 ui 的 SHA 确定不存在时，分支建了 run；main 在这里是拒的。② 只给 `revision=<platform sha>`、忘了 uiRevision：先同步两个镜像，再为一个永远不会出现在 ui 里的 SHA 轮询，最长 90 秒后才给出提示。③ 分支或标签名缺失时，第二次查看紧跟在同步请求之后，而镜像同步是排队异步的，刚推的分支多半还是被拒；SHA 会轮询。④ 分支和标签列表只取前 50 条（原有）。⑤ 兜底清单里那个死掉的 socket 现在是「承重」的：research 和各插件的交付没有自己的清单，查的是 8 个 Trade / 平台仓库，全靠 socket 这一处「不知道」才不被拒；只把 socket 从 `trackedGiteaRepos` 里删掉，会让这些交付全部被拒。⑥ ref 检查挪到了读取 Pipeline 和规则 8 之后。

七点：1. 是同一份：被创建的 run 的 `spec["params"]` 就是被探测的；表没覆盖或覆盖错的克隆参数：deliver-stg 的 `uiRevision`、build-frontend-stg、research 和各插件。2. `revision=main, params.revision=<platform sha>` 两边建出的 run 逐字节相同，ui 用 `main`，不报错——对生产请求是个坑；两个都钉用：顶层 `revision=<platform sha>`，`params={"uiRevision":"<ui sha>"}`。3. 过了这里、之后一定被来源检查拒的：同名的分支和标签；顶层给缩写 SHA 或大写的 40 位 SHA 再配一个钉住的 uiRevision（新出现的）。4. 提交查询用包里原有的接口和凭证；404 只有在同一仓库的分支和标签列表随后都返回 200 时才算缺失，其它都算不知道，不触发同步也不拒绝。5. 三条种错都被杀死；另外把表里 stg 的 ui 在两个参数之间对调，整包都过。6. 两份 main 基线没动；两边都建 run 的 671 个调用逐字节相同；main 拒、分支能起的 154 个；main 能起、分支拒的 96 个里 72 个是 main 建出来也克隆不了的，4 个是同步失败，20 个只出现在 socket 有应答的假想状态里。7. 合并前：改表、补测试；给 CI 的缺失路径补测试；忘了 uiRevision 时不等 90 秒。上正式环境之前：定 Trade 的检查要不要生效；生产请求用第 2 点的写法。

测试运行：go test 8 次。
END OF REPORT
