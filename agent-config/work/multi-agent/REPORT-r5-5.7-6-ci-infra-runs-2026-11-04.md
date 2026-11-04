# 实测：infra CI 运行记录（R5:5.7-6 §2.3、§2.4 的原始数据）

读取时间 2026-11-04 11:1x CST，来源 `cicd` 命名空间里 `tekton.dev/pipeline=bifrost-ci-infra` 的全部运行（集群保留的最早一条是 10-30 23:24 CST）。时间为 UTC。种类的判定优先级见设计稿 §2.3。失败行取失败那一段日志的第一条 `FAIL`（或 pytest 的 `E` 行）。

| 运行 | 创建（UTC） | 种类 | 结果 | revision | 失败段 | 第一条失败行 |
|---|---|---|---|---|---|---|
| `ci-infra-sbvmf` | 2026-10-31 05:24 | branch | Failed | `1396da4af6` | - | — |
| `bifrost-ci-infra-1793424335` | 2026-10-31 05:25 | branch | Failed | `1396da4af6` | - | — |
| `ci-infra-jr5zj` | 2026-10-31 05:32 | main | Failed | `f83a12e8a5` | - | — |
| `ci-infra-m2vl6` | 2026-10-31 05:33 | branch | Failed | `7717be6dd7` | - | — |
| `bifrost-ci-infra-1793424998` | 2026-10-31 05:36 | branch | Failed | `7717be6dd7` | check | E               subprocess.CalledProcessError: Command '['git', '-C', '/tmp/pytest-of-root/pytest-0/test_plan_lists_the_files_and_0/ws/bifrost-ui', 'commit', '- |
| `ci-infra-hhjs5` | 2026-10-31 05:42 | branch | Failed | `8afbab8878` | check | E               subprocess.CalledProcessError: Command '['git', '-C', '/tmp/pytest-of-root/pytest-0/test_plan_lists_the_files_and_0/ws/bifrost-ui', 'commit', '- |
| `bifrost-ci-infra-1793425365` | 2026-10-31 05:42 | branch | Failed | `8afbab8878` | check | E               subprocess.CalledProcessError: Command '['git', '-C', '/tmp/pytest-of-root/pytest-0/test_plan_lists_the_files_and_0/ws/bifrost-ui', 'commit', '- |
| `ci-infra-f8bsq` | 2026-10-31 05:52 | branch | Failed | `04dbba36d8` | check | — |
| `bifrost-ci-infra-1793425924` | 2026-10-31 05:52 | branch | Failed | `04dbba36d8` | check | — |
| `ci-infra-4cfp6` | 2026-10-31 05:58 | branch | Failed | `8a20b28d4d` | check | FAIL code_health_no_base |
| `bifrost-ci-infra-1793426297` | 2026-10-31 05:58 | branch | Succeeded | `8a20b28d4d` | - | — |
| `ci-infra-lb8qr` | 2026-10-31 06:04 | main | Succeeded | `1355f11983` | - | — |
| `ci-infra-4q8f7` | 2026-10-31 06:04 | branch | Failed | `057c18d5be` | check | E       AssertionError: 'workloads not recovered on ubt-k3s-04' not found in 'WARNING: approval appr_ok predates the claim protocol; the run is not recorded on  |
| `ci-infra-2k7hs` | 2026-10-31 06:04 | branch | Failed | `fd9181fac9` | check | FAIL code_health_no_base |
| `bifrost-ci-infra-1793426691` | 2026-10-31 06:04 | branch | Failed | `fd9181fac9` | check | FAIL hard_floor scripts/x.py |
| `bifrost-ci-infra-1793426693` | 2026-10-31 06:04 | branch | Failed | `057c18d5be` | check | FAIL unregistered_consumer scripts/x/read.py:2 |
| `bifrost-ci-infra-1793426696` | 2026-10-31 06:04 | branch | Failed | `8a20b28d4d` | clone | — |
| `ci-infra-j4hkc` | 2026-10-31 06:14 | main | Succeeded | `ae35f49a02` | - | — |
| `ci-infra-mdv4m` | 2026-10-31 06:45 | main | Succeeded | `b6a9aaf4e5` | - | — |
| `ci-infra-qblp4` | 2026-10-31 07:05 | main | Succeeded | `7cd0bf9fa0` | - | — |
| `landing-ci-infra-bef75880e62608d6f7b2d6d2-1` | 2026-10-31 07:22 | landing | Succeeded | `38495e452c` | - | — |
| `landing-ci-infra-432160ff81a6f55c03819df7-1` | 2026-10-31 08:43 | landing | Succeeded | `a85202289c` | - | — |
| `ci-infra-g28vr` | 2026-10-31 08:47 | main | Succeeded | `a85202289c` | - | — |
| `ci-infra-wwph4` | 2026-10-31 15:45 | main | Failed | `40c1af4da8` | check | FAIL unregistered_consumer scripts/landing/test_tekton_step_images.py:45 |
| `ci-infra-f895j` | 2026-10-31 15:54 | branch | Failed | `b3f0d92883` | check | FAIL code_health_no_base |
| `bifrost-ci-infra-1793462071` | 2026-10-31 15:54 | branch | Failed | `b3f0d92883` | clone | — |
| `bifrost-ci-infra-1793462085` | 2026-10-31 15:54 | branch | Failed | `b3f0d92883` | check | FAIL consumer_changed scripts/s5/test_pins.py |
| `bifrost-ci-infra-1793462258` | 2026-10-31 15:57 | branch | Failed | `925c40a477` | check | FAIL consumed_path k8s/cicd/tekton/pipeline-ci-platform.yaml |
| `ci-infra-5xlj8` | 2026-10-31 15:57 | branch | Failed | `925c40a477` | check | FAIL consumer_changed scripts/s5/test_pins.py |
| `ci-infra-9xzwb` | 2026-10-31 16:00 | branch | Succeeded | `8a5a5688ce` | - | — |
| `bifrost-ci-infra-1793462414` | 2026-10-31 16:00 | branch | Failed | `8a5a5688ce` | check | FAIL code_health_regressed code.duplication.rocket.infra-py 39→40 |
| `ci-infra-p7vh6` | 2026-10-31 16:07 | main | Succeeded | `f871bc4c0b` | - | — |
| `bifrost-ci-infra-1793462845` | 2026-10-31 16:07 | main | Succeeded | `f871bc4c0b` | - | — |
| `ci-infra-7nlpw` | 2026-10-31 16:12 | main | Failed | `148c865a7e` | check | FAIL unregistered_consumer scripts/landing/test_tekton_step_images.py:45 |
| `ci-infra-5kmsv` | 2026-10-31 16:17 | main | Succeeded | `f871bc4c0b` | - | — |
| `ci-infra-p9frq` | 2026-10-31 16:22 | branch | Failed | `971956d1f0` | check | FAIL code_health_no_base |
| `ci-infra-fkkk6` | 2026-10-31 17:19 | main | Succeeded | `2f29655371` | - | — |
| `landing-ci-infra-e6a8e3c56718f228f2a216cf-1` | 2026-11-01 04:36 | landing | Succeeded | `46e2ad0a05` | - | — |
| `ci-infra-bf9s7` | 2026-11-01 04:40 | main | Failed | `46e2ad0a05` | check | E       AssertionError: 'workloads not recovered on ubt-k3s-04' not found in 'WARNING: approval appr_ok predates the claim protocol; the run is not recorded on  |
| `ci-infra-kw8ng` | 2026-11-01 05:26 | main | Succeeded | `99ed5467b8` | - | — |
| `landing-ci-infra-e7f616bef55696632e947ecf-1` | 2026-11-01 06:37 | landing | Succeeded | `6d7b7623d0` | - | — |
| `ci-infra-h9qtg` | 2026-11-01 06:41 | main | Succeeded | `6d7b7623d0` | - | — |
| `ci-infra-wb5nr` | 2026-11-01 07:25 | main | Succeeded | `2cb92d123b` | - | — |
| `landing-ci-infra-9f0b62d474aeac73bcec2694-1` | 2026-11-01 07:40 | landing | Succeeded | `cba3c2bcb1` | - | — |
| `ci-infra-4vd6h` | 2026-11-01 07:46 | main | Succeeded | `cba3c2bcb1` | - | — |
| `landing-ci-infra-836d7ab68918c8468834d568-1` | 2026-11-01 08:20 | landing | Succeeded | `2a9c4b17fc` | - | — |
| `ci-infra-b5bbj` | 2026-11-01 08:25 | main | Succeeded | `2a9c4b17fc` | - | — |
| `ci-infra-g2qwv` | 2026-11-01 08:49 | main | Succeeded | `8063c0fc0e` | - | — |
| `landing-ci-infra-30c81920fc4438108f5670a0-1` | 2026-11-01 09:36 | landing | Succeeded | `e4eaf0816b` | - | — |
| `ci-infra-drp7q` | 2026-11-01 09:42 | main | Succeeded | `e4eaf0816b` | - | — |
| `landing-ci-infra-6db02b92b71bb3f7fcad8c91-1` | 2026-11-01 15:33 | landing | Succeeded | `803d04bd00` | - | — |
| `ci-infra-bd5sf` | 2026-11-01 15:37 | main | Succeeded | `803d04bd00` | - | — |
| `ci-infra-tjhl8` | 2026-11-01 17:26 | main | Failed | `cc2996aad4` | check | FAIL unregistered_consumer console/src/pages/shell/agents/planRoundModel.ts:45 |
| `ci-infra-djgcv` | 2026-11-01 18:59 | main | Failed | `b1c139f110` | check | FAIL unregistered_consumer console/src/pages/shell/agents/__tests__/workPage.test.tsx:50 |
| `landing-ci-infra-49ddb38d415c3faa5fd8d335-1` | 2026-11-01 21:04 | landing | Failed | `9c4c2a3bea` | check | FAIL consumer_changed console/src/pages/shell/agents/workViewModel.ts |
| `landing-ci-infra-8864264866abf7bdaa49cd95-2` | 2026-11-01 21:30 | landing | Succeeded | `0dd51d4959` | - | — |
| `ci-infra-wdm54` | 2026-11-01 21:35 | main | Succeeded | `0dd51d4959` | - | — |
| `ci-infra-w5wcl` | 2026-11-01 21:44 | main | Succeeded | `8291857db7` | - | — |
| `ci-infra-xhjbt` | 2026-11-01 23:54 | main | Succeeded | `de152c7340` | - | — |
| `landing-ci-infra-538b09b39fb65f792ebf72f2-1` | 2026-11-02 01:25 | landing | Failed | `3cceaf9ade` | check | FAIL code_health_regressed code.oversized.rocket.infra 57→58 |
| `ci-infra-lhmch` | 2026-11-02 01:33 | main | Succeeded | `ce43465788` | - | — |
| `landing-ci-infra-bf936851f4f916a9bc2838f7-2` | 2026-11-02 01:44 | landing | Succeeded | `8095841819` | - | — |
| `ci-infra-cw4x9` | 2026-11-02 01:48 | main | Succeeded | `8095841819` | - | — |
| `landing-ci-infra-76436bc1a641021aae5dfedf-1` | 2026-11-02 02:00 | landing | Succeeded | `e690411cba` | - | — |
| `ci-infra-lfvts` | 2026-11-02 02:04 | main | Succeeded | `e690411cba` | - | — |
| `ci-infra-vp2jj` | 2026-11-02 16:02 | main | Succeeded | `c60f8769e2` | - | — |
| `ci-infra-n722s` | 2026-11-02 18:07 | main | Succeeded | `bc9584ea01` | - | — |
| `ci-infra-bd2jk` | 2026-11-02 18:15 | main | Succeeded | `fa7e2e26ab` | - | — |
| `landing-ci-infra-bcd298e0c16ecbddd85a26da-1` | 2026-11-03 05:26 | landing | Failed | `cba6f54f80` | check | FAIL unregistered_consumer api/internal/agentrt/migrations/0011_debts.sql:2 |
| `ci-infra-x854g` | 2026-11-04 01:27 | main | Failed | `381ad383d6` | check | FAIL unregistered_consumer api/internal/agentrt/migrations/0011_debts.sql:2 |
| `landing-ci-infra-f9e128bdbde48c07a4c36fc2-1` | 2026-11-04 01:49 | landing | Succeeded | `473eaf4a9d` | - | — |
| `ci-infra-4tvl5` | 2026-11-04 01:53 | main | Succeeded | `473eaf4a9d` | - | — |
| `ci-infra-5h9cr` | 2026-11-04 02:23 | main | Failed | `80a8a4ab3b` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `ci-infra-nm54x` | 2026-11-04 03:33 | main | Failed | `f3e71fdbd8` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `ci-infra-fjsg2` | 2026-11-04 04:01 | main | Failed | `c9d21a642a` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `ci-infra-9w2lb` | 2026-11-04 04:16 | main | Failed | `3f2b041e04` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `landing-ci-infra-1e6eba19c719c7c8535845b6-1` | 2026-11-04 06:35 | landing | Failed | `982be71c60` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `ci-infra-xn7w9` | 2026-11-04 15:01 | main | Failed | `1e1c3b63d3` | check | FAIL unregistered_consumer k8s/storage/nfs-fast/render.py:96 |
| `ci-infra-nspnr` | 2026-11-04 15:24 | main | Succeeded | `85998cb3b7` | - | — |
| `ci-infra-zt22l` | 2026-11-04 15:41 | main | Failed | `0c841a4d68` | check | FAIL code_health_regressed code.duplication.rocket.infra-py 40→42 |
| `ci-infra-4xkk4` | 2026-11-04 16:04 | main | Succeeded | `1a6ae3449c` | - | — |
