# Codex 复核 105 — 调度脚本（记录器）第一片第 4 轮：折叠结果做成不透明对象，种错清单证明测试能失败（分支 `w31/w66-recorder`，`c8e5b0e..7d9add8`）

2026-10-11 20:51 CDT · 只读 · 结论：先修；停线条件成立（P1 一处：`Folded` 的槽可写、可伪造、可浅拷贝）。统筹方的重跑另有 2 处自己种的错没有任何测试拦住（`unrecorded` 的 `run_id` 不同被当成已记录；工作没读进来时不再判 `unknown`）。第 5 轮按 Owner 当晚定的规矩交给 Codex 修，由 Claude 一侧复核。

VERDICT: fix first  
AN INPUT THAT BREAKS (1), (2) OR (3), OR A PLANTED VIOLATION NO TEST CATCHES: found  
以下文件路径相对 `agent-config/scripts/recorder/`。  
复核102 P1-1：已关闭；`publish.py:600` 拒绝普通字典，`:662` 也检查 `owner_now`。  
复核102 P1-2：部分关闭；字典被拒，但 `read.py:46` 的可写槽位仍允许制造并发布矛盾回退。  
复核102 P1-3：部分关闭；`test_fuzz.py:213` 的 C 族仍未到达所声称的事件叶子校验，D 族也未实现完整对象类别。  
复核102 P1-4：部分关闭；`test_round3.py:203` 已逐工作检查七级字段和值，但 `:32` 仍从手写文档进测试门。  
复核102 P1-5：已关闭；`test_arguments.py:1` 起覆盖类型、数值范围、空与非空日志及恶意对象。  
复核102 P2-1：已关闭；`publish.py:33` 先检查 host 确切类型，实测子类比较方法调用为零。  
复核102 P2-2：部分关闭；重复 pending 不移动起点，但 `ownerball.py:391` 未处理记录消失后重新出现。  
复核102 P2-3：已关闭；`read.py:514` 起在容量首个超限处截断整个后缀，两种输入顺序一致。  
STOP CONDITION: met；下面的实际输入使目标 (3) 不成立，按既定条件停线。  
P1 — `read.py:46`、`publish.py:605`：`f=fold_total([],[],True); f._doc["fold_complete"]=True; f._doc["ball"]={"holder":"nobody","why":"queue_done"}; publish_total(f)` 实测同时发布 `recorder_failed`、全清和 nobody，出口自检仍通过。最小修复：发布读取模块私有、按对象身份保存的不可变快照，补直接槽修改及 `object.__setattr__` 回归。  
同一漏洞允许普通代码伪造：`g=object.__new__(Folded); g._token=f._token; g._doc=合法文档` 即被接受，无须按名称读取模块私有令牌；调用者也能删除 `recorder_failed`，反向改变回退身份。  
封装核验：构造错误令牌、定义子类均被拒；`document()` 返回深拷贝。`copy.copy` 被接受且共享内部文档；deepcopy、pickle往返及另一模块副本的 Folded 均成为参数回退。未初始化 Folded 得到 caught、内部错误1，而非参数回退。  
P2 — `read.py:52`：在内存中把构造令牌检查改为 `if False:`，只读可运行套件仍为273通过、29排除；现有构造测试未抓住违规。最小修复：添加非法构造、空壳、令牌转移和复制的具名测试，并收入清单；未声称完整302项已独立验证。  
P2 — `test_fuzz.py:179`、`:232`：C族第二行的 `prev_sha256` 留空，且基线不是合法事件序列。实测默认640个降级样本：433 bad_chain、118 bad_json、55 limit_depth、34 bad_utf8，零个到达字段缺陷校验。最小修复：从合法序列改叶子、重封整链，并断言预期分类；观测事件放进观测日志。  
P2 — `test_fuzz.py:245`、`:263`、`:365`：D未生成覆盖表承诺的各种内建子类、生成器和环；E只断言任意降级，未逐块核对预期 incomplete。样本打印只展示日志，隐藏了D参数及E的host/blocks。最小修复：补齐生成器及逐族精确断言，打印实际变异对象。  
P2 — `read.py:72`、`test_folded.py:109`：测试门可由任何调用者直接导入，守卫只扫描包内名字，不能阻止非测试调用。`level-0..6`、commands夹具及大多数表B多级用例都经过它；真实验证器通过只证明这些手写输出被接受。最小修复：可从日志产生的标记必须走真实路径，限制测试门所在模块及用途。  
P2 — `ownerball.py:395`：真实封链日志中 `found@10 → not_found@20 → found@30`、同一uid且30时确认，球实测为 record_created/since=10；连续原因已中断。最小修复：取当前连续段起点并补返回原因测试，同时消除设计“第一条找到”与简报“连续成立”的冲突。`pending→approved→pending` 已正确返回30。  
P2 — `read.py:558`：重名z两份，加超容量a及空b，两种顺序均得到未读数4、名字 `["z","z","a","b"]`，违反按名字排序再限20项。最小修复：合并重名与容量后缀后统一排序、再截断；补超过20项的混合测试。  
P2 — `test_mutants.py:67`：任何非零退出均算捕获，语法错误、收集失败也能放行，而且未要求每个 must_fail 节点实际失败。最小修复：验证具名 FAILED 集合，拒绝收集/语法错误及节点缺失。  
清单抽查15项均在内存改写后触发具名 FAILED，未见语法错误；下列说明各自断言。  
`a2-always-skip`：row01–08、10–11断言未记账计数；`a2-never-skip`：row09断言同run_id开着时不计；`declared`：row03–06断言仅声明不能免计。三条实际覆盖十一行，并非条数少就构成缺口。  
`b-0-logs_unread`：row01断言未读数3及名字；`b-3-step_unknown`：row08断言unknown计数及原因；`b-6-unrecorded_runs`：row05逐工作断言1；`b-5-conservation`：row12断言清单与省略数守恒。  
`c-work-keep-first`：表C row01断言重名工作全部拒读；`keepfirst`：row02断言重名观测两种顺序都拒读。  
`limit-line`：断言131073字节为limit_line；`limit-name`：断言81码点标题为limit_text；`now0`：断言越界now在空、非空日志中均为参数回退。  
`arg-host`：断言子类比较调用零次；`guard-line`：断言异常造成内部断链并计数；`p2-since`：断言重复pending后起点仍10。  
清单分组与报告一致：3/86/2/13/9/4/5，共122；表B清单为逐项写出的数据，未由规则表自动生成。回退不进入缩减，其单例处理合理。  
默认1333×3可作快速门，但长度2无法形成完整的声明、开始、观测生命周期；完整47989×3仍必要。TASK-4验收要求默认、完整及完整mutants全部运行，设计应明确这是合并门槛。  
独立运行：只读子集273通过、29排除，11.59秒；构造检查变异后同子集273通过，11.02秒。需临时文件、Go或子进程验收的29项未独立运行；未写仓库、未调用HTTP或集群。  
协调方VERIFY现记录默认40.20/41.06秒、完整109.74秒、122 mutants 63.32秒、13夹具通过；这些仍是其记录，所读版本尚未给出完整Go及六个自种变异结论。  
范围符合：仅recorder路径改动，RATCHETS本轮未改；平台仍17c0c87，工作树干净，最长publish.py744行；折叠/发布路径未发现文件、时钟、环境、网络或子进程操作。  
报告的feed留尾、feed_cut及记录ref_state选择合理；未来unrecorded轮未套确认的+2秒规则须明确裁定，不能继续留作隐含选择。  
须补入设计：可验证的不透明对象身份及复制策略、测试门边界、真实字节路径的表B验收、完整模糊类别、连续since的中断语义、未来轮裁定，以及full与mutants的合并门槛。  
END OF REPORT
