# 切法：运行时的目标与计划能派到 bifrost-trade-infra（W-31 第 2 轮，T26 前提，2026-10-19）

台账：`WORK.md` 第 2 轮 2.4「★ 一件活从派出到验收」那一行（10-19 02:1x 查出：运行时只认 `bifrost-platform`，T26 的 Python 那件没有仓库可派）。
线程：local_cc97b04f-7fb8-4b2b-bc39-88ca90296e3f（由统筹线程 local_accccb4e 起）。平台分支 `w31/repo-infra`（`f77abf9` 实现，`0e52030` 复核 330 的修复，`0c5ad12` 窄确认 331 的修复）。

## 为什么

T26 要 Go、Python、TS 各一件活。`store.Repos`（`bifrost-platform/api/internal/agentrt/store/repos.go`）里只有平台仓库：
一句目标只能落到 `bifrost-platform`，计划里的任务也只能写它。infra 是 Python 脚本和它们的测试最多的仓库，
但它没有 CI 的 pytest 任务、没有 `pyproject.toml`，检查命令要这里定。

## 摸底（10-19 02:1x–05:0x 实测，infra 主线 `710723d`，收尾在 `b62f810` 上重跑）

- infra 的 Python 测试有 79 个文件：`agent-config/scripts/recorder`（33）、`scripts/release`（24）、`scripts/` 顶层（13）、
  `scripts/benchmark`（3）、`k8s/cicd/gitea-backup`（3）、`scripts/agent-host`（2）、`scripts/cicd`（2），
  另有 `agentrt`、`gitea`、`k3s`、`role-matrix`、`agent-config/scripts` 各 1。
- 第三方依赖：pytest、PyYAML 是普遍要的；`scripts/test_audit_retention_archive.py` 要 pyarrow，`scripts/test_iv_gap_audit.py` 要 `bifrost_research`。
  很多测试自己起 `python3`（不是 `sys.executable`），要求 PATH 上的 `python3` 就有 pytest 和 PyYAML（benchmark 的出题脚本、gitea 脚本、pre-commit 测试）。
- 每个目录在断网、只有本仓库快照（真 git 克隆，有历史）、干净环境下的结果与用时（Mac；Linux 容器 `python:3.11-slim` 断网复核了不需要 git 的部分）：

  | 目录 | 结果 | 用时 | 进不进检查 |
  |---|---|---|---|
  | `scripts/benchmark` | 77 过（要 PATH 上的 python3 有 pytest；8 条要 Go） | 约 60 s | 进 |
  | `scripts/k3s` | 39 过 | 28–40 s | 进 |
  | `scripts/agentrt`、`k8s/data/role-matrix`、`agent-config/scripts/test_check_hardcoded_paths.py` | 全过 | 各 1 s 内 | 进 |
  | `scripts/` 顶层 13 个文件 | 9 个全过（另 4 个见下面四行） | 共约 7 s | 进这 9 个 |
  | `scripts/test_access_checks.py` | 1 条在主线上就坏（review 261/262 改了 `check_admission_guards.live` 先读 Application，测试的假 `subprocess.run` 没跟着改，`json.loads("no")`） | — | 不进，记 TD-378 |
  | `scripts/test_agentrt_infra.py` | 要真 `kubectl kustomize`，06 出集群后没有 kubectl | — | 不进 |
  | `scripts/test_audit_retention_archive.py`、`scripts/test_iv_gap_audit.py` | pyarrow、`bifrost_research` | — | 不进 |
  | `scripts/cicd` | 18 过，但 10 条在 127.0.0.1 上起假 Gitea | 14 s | 不进（见下「回环」） |
  | `scripts/agent-host/test_probe_gitea_protection.py` | 14 条全在回环上起假 Gitea | — | 不进 |
  | `scripts/agent-host/test_agent_06_owner.py` | 测的是你 Mac 上的脚本，调 macOS 的 `shasum`（perl） | — | 不进 |
  | `scripts/release` | 497 过 | 234 s（Linux 容器 258 s） | 不进（时间） |
  | `scripts/gitea` | 103 过（要真 git 克隆） | 198–207 s | 不进（时间） |
  | `k8s/cicd/gitea-backup` | 102 过（Linux；Mac 上 2 条 BSD 工具差异） | 264–289 s | 不进（时间） |
  | `agent-config/scripts/recorder` | 745 过、3 败 | 797 s | 不进：`test_guard` 一条把 `scripts/release` 整套跑三遍（732 s）；3 条要旁边有 `bifrost-platform` 再跑 Go；目录本身「不可信、未接线」（STATUS.md） |

- **回环**：06 上 codex 的沙箱完全没网，连 127.0.0.1 也不行（Linux 上 seccomp 禁 AF_INET 套接字）。执行者交卷前要自己跑检查命令，
  起本地端口的测试在它那里必失败、又不是它改坏的。所以检查只放「完全没网也能过」的测试。
- **Go 的构建缓存**：benchmark 的 8 条 Go 测试在 codex 沙箱里写不了 `$HOME/.cache/go-build`（只能写工作区和自己的临时目录）。
  新 agentd（`35eafb7`，TD-371 写墙）给每次尝试固定了 `GOCACHE` 在尝试的临时目录；旧 agentd 没有。
- **release 套件在长**：10-12 时还是「过了一分钟」（`test_guard.py` 的注释），10-19 是 4 分钟。放进每件 infra 任务都跑的检查，几周内就会顶到 900 秒。

## 做法（平台分支 `w31/repo-infra`）

`store.Repos["bifrost-trade-infra"]`：

- **Setup**（agentd 在检出里、执行者开工前跑，有网）：

      python3 -I -m venv --clear .git/venv
      env PIP_CONFIG_FILE=/dev/null .git/venv/bin/python3 -I -m pip --isolated install --quiet --no-cache-dir --no-input --disable-pip-version-check --only-binary=:all: --no-deps pytest==9.0.2 pluggy==1.6.0 iniconfig==2.1.0 packaging==25.0 pygments==2.19.2 pyyaml==6.0.3

  - venv 放在检出的 `.git/venv`：提交（`git add --all`）不会带上它，检查用的是新克隆、里面没有它，所以执行者的改动和上一次尝试都决定不了用哪个解释器、哪些包跑测试。
    放在检出里（不放 `../`）是为了跟着每次尝试走、跟着检出一起删；放 `.git` 而不是 `.venv` 是因为 infra 的 `.gitignore` 不忽略 `.venv`，放进去会被整个提交。
  - `-I`：检出根目录不在模块路径上，执行者在根放的 `venv/`、`pytest.py`、`sitecustomize.py` 不会被执行（实测）。
  - 六个包全钉、`--no-deps`、只收 wheel、不用缓存、`--isolated`，再加 `PIP_CONFIG_FILE=/dev/null`（全局、站点级配置文件也不读；`--isolated` 只管环境变量和用户级，复核 330 B5）：
    以后谁发了新版本、主机上有什么 pip 配置都改变不了检查；不跑 sdist 的构建脚本。
    pytest 9.0.2 的四个依赖按它的要求钉在 2025 年中的版本（`pip check` 无冲突），Linux 3.11 与 Mac 3.12 上都装得上、跑得起来；
    Python 3.10 及以下还要 `exceptiongroup`、`tomli`，06 是 3.12，不涉及。
- **Verify**（一条）：

      sh -c '<拒绝包> PATH="$PWD/.git/venv/bin:$PATH" GOCACHE="${TMPDIR:-$HOME/.cache}/go-build" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 exec python3 -I -m pytest -c /dev/null --rootdir="$PWD" --noconftest -q -p no:cacheprovider <14 个路径>'

  `<拒绝包>`（`repos.go` 的 `infraCheck` 由测试清单生成）：入选测试的包祖先链上（根目录、`scripts/`、`k8s/`、`k8s/data/`、`agent-config/`、`agent-config/scripts/`）
  或四个入选目录里（跟随链接）只要有 `__init__.py`（含同名链接），就以 3 退出并写明是哪个文件。

  - venv 放 PATH 最前：测试自己起的 `python3` 也是这个环境（有 pytest、PyYAML）。06 的 `/bin/sh` 是 dash，前缀赋值会带进 `exec` 的程序（容器里实测）。
  - `GOCACHE`：有 TMPDIR（codex 有自己的；新 agentd 每次尝试都有）就放在下面，否则就是 Go 在 Linux 上的默认位置，确定性检查上等于没改。
  - `-c /dev/null --rootdir="$PWD" --noconftest`、不自动加载插件（复核 330 A1）：pytest 不读任何配置文件和 `conftest.py`——检出里的（改动可以加）和检出以上各级目录里的
    （pytest 找配置会一直往上走，旧 agentd 下没有写墙的尝试能在 `tasks/<任务>/`、agentd 根、HOME 留下）。否则一个只写 `addopts = --collect-only` 的 `pytest.ini`，
    或把 `session.exitstatus` 改成 0 的 `conftest.py`，就能让带着失败测试的改动过检查。入选的测试都没有自己的 conftest；以后 infra 若加 pytest 配置或 conftest，
    检查不会读到，要同时改这里。
  - 拒绝包（窄确认 331 A1）：pytest 会导入包的 `__init__.py`，里面写 `pytest_plugins = [__name__]` 就把自己注册成插件，同样能改退出码，上面几个开关都挡不住。
    infra 现在一个 `__init__.py` 都没有，所以直接拒绝。以后真要在这些地方建包，要同时改这里（比如由受信任的启动器限制插件加载）。
    测试本身的代码仍由改动决定（比如在测试模块里写 `pytest_plugins`、直接退出），那是评审的事。
  - `-p no:cacheprovider`：不在检出里留 `.pytest_cache`（infra 的 `.gitignore` 不忽略它）；`__pycache__` 已被忽略。实测跑完 `git status` 为空。
  - 14 个路径见上表「进」的那些，写在 `repos.go` 的 `infraTests`，每个被拿掉的都在注释里写了原因。
- **不设 TestDirs**：计划不能给 infra 任务加自己的检查（`checkTest` 只认 `go -C <模块> test`，在 plan-import 线的文件里，这里不动）。
  计划格式的文字按仓库说：infra 是「不收计划自带的检查，verify 留空」，平台照旧；并写明「每件任务都在目标的仓库里」（目标的 mission 只含这一个仓库）。
  计划真加了检查时，`checkTest` 的退回原因也说「这个仓库不收计划自带的检查」，不再叫它写一个不存在的 Go 模块（复核 330 B3，三行，plan-import 分支没动这个函数）。
  快照的小标题从「计划可以写的仓库」改成「运行时认得的仓库及各自的检查」：参谋长简报也用这份快照（B4）。
- **命令显示**：给执行者和计划者看的命令改成 shell 能原样执行的写法（含空格、引号、`$` 的参数加单引号；第一个词像赋值或是保留字也加，B1），否则 `sh -c` 的脚本会被看成好几个词。平台的命令显示不变。

## 跑多久（SpecTimeoutS = 900 秒，所有检查命令合计）

| 条件 | Setup | Verify | 结果 |
|---|---|---|---|
| 确定性检查（agentd 自己的 `setup` / `verify` 子命令，新克隆，Setup 有网、Verify 断网但有回环，PATH 有 Go，`710723d`） | 2.6 s | 106 s | 201 过 |
| 同上，infra 主线 `b62f810` | 3.6 s | 103 s | 201 过，跑完 `git status` 为空 |
| 同上，复核 330 修复后的命令（`0e52030`），`b62f810` | 3.3 s | 90 s | 201 过，`git status` 为空 |
| 同上，最终命令（`0c5ad12`），`b62f810` | 3.4 s | 89 s | 201 过，`git status` 为空 |
| 执行者（全禁网含回环，只可写检出和 TMPDIR，Mac 沙箱；`0e52030`、`0c5ad12` 的命令） | — | 83–118 s | 196 过，5 败：全在 `scripts/k3s`，是 macOS 的 `mktemp` 不认 TMPDIR；同样条件（含新参数）在 Linux 容器里这些全过 |
| 弄坏一条入选测试（阴性对照） | 3.0 s | 91 s | 判失败，`sh ended 1`，尾部写明是哪条 |
| 同上，再在根目录放 `pytest.ini`、`pyproject.toml`（只收集）、改退出码的 `conftest.py`，上一级目录放同样的 `pytest.ini` 和 `conftest.py`，根目录放 `venv/`、`pytest.py`、`sitecustomize.py`（`0e52030`） | 有 | 117 s | 判失败，写明是哪条；植入的文件一个都没运行 |
| 同上，再加声明自己为插件的 `scripts/__init__.py`（`0c5ad12`） | 有 | 0.3 s | 以 3 退出，写明 `scripts/__init__.py`；植入的文件一个都没运行 |

用掉预算的八分之一左右；06 是 16 核，单核不比 Mac 快的话也在 4 分钟内。拿掉的三个大目录合起来约 12 分钟，单放任何一个进来都把余量吃掉一半，而且它们在长。

## 06 上 agentd 要不要改

**不用改 agentd，也不用你在 06 上动手**：

- Setup 和 Verify 都是任务说明里的数据，平台发出去，agentd 照跑。06 上要的东西已经在：`python3`、`python3-venv`（`prepare-agent-06.sh` 为基准题装过）、
  git、bash、Go（`/usr/local/go/bin` 在两个 agentd 的 PATH 上）。出站规则放行公网 443，pip 访问 pypi.org 和 files.pythonhosted.org 可以。
- 新 agentd（`35eafb7`，写墙）下：Setup 有自己的 HOME、能写检出（`.git/venv` 在检出里）、有网；检查命令只能写检出、兄弟仓库和尝试的临时目录——
  入选的测试在「HOME 不可写」下实测都过（上表执行者那行）。旧 agentd（`d788296`）下也一样能跑。
- Gitea：infra 已在 Gitea 主仓、接受 `agent/**` 分支（10-17 起）；平台读 infra 的 `main` 用的是同一个 Gitea 读取器（`agentrt_heads.go`，按仓库名拼路径）。
  上 STG 后第一件 infra 任务就会验证这一条，读不到会在提交目标时直接报「main 读不到」，不会半路失败。

## 上 PROD 要什么

- 只是平台发版：STG（`bifrost-deliver-platform`，规矩内由统筹线程做）→ 核对 → PROD 审批单（你在 Console 上批）。无 DDL、无新路由、无新外部依赖进平台本身；
  `POST /goals` 多收一个仓库名（加法，旧调用不变）。pytest 等六个包只装进每次检查的临时环境，不进任何镜像。
- 建议在 STG 先跑一件 infra 小目标（经接口或 MCP 提交，见下一节），走到 review 再上 PROD。

## 要统筹线程定的：T26 的「一个 mission 里 Go、TS、Python 各一件」现在出不来

两处限制，都不在这条线的改动范围里：

1. **Console 提交目标时仓库写死**：`console/src/api/agentRuntime.ts:119` `repo: 'bifrost-platform'`。你在界面上提不了 infra 的目标；接口（`POST /goals`）和 MCP 可以。
2. **一个目标只有一个仓库**：`ProposeGoal` 建的 mission 只含目标的仓库，计划里的任务只能写它（`planresult.go` 用 mission 的仓库过滤）。
   所以一句目标出不来「Go/TS 在平台、Python 在 infra」的同一个 mission。

选项（改公开接口，按 §5 先定再写）：

- **A（推荐）目标可以选多个仓库**：`POST /goals` 的 `repo` 改成 `repos`（旧字段照收、当一个），mission 含这些仓库，计划每件任务写其中之一；
  Console 的目标框加一个仓库多选（默认平台）。约半天，加复核一轮。T26 照原定义跑。
- **B 两句目标**：T26 拆成平台一句（Go、TS）和 infra 一句（Python），两个 mission。只要 Console 加单选（约 1 小时）。T26 的「一个 mission」那条要你改口径。
- **C 不经目标**：统筹线程用 `propose_mission`（repos 两个）和 `propose_tasks` 直接派四件，任务说明照 `ImplementSpec` 写。不改代码，但 T26 少了「你给一句目标」这一环。

## 不做的

- 不给计划开 pytest 自带检查（让触及 `scripts/release` 的任务带上那个目录的测试）：要改 `checkTest`（plan-import 线的文件）；等那条线合并后另起，作为下一步。
- 不在检查里放回环测试和三个大目录；它们由评审和以后的「计划自带检查」覆盖。
- 不修 `scripts/test_access_checks.py`：记 TD-378，由 infra 侧修。

## 验收（已做）

- 单元测试（平台）：infra 的检查与准备步骤（每个包钉版本、没有拿掉的目录、路径不带 `..` 或 shell 字符）；命令的引号；
  目标指定 infra 时计划说明写对、收下计划后实现任务的说明就是 infra 的；infra 计划自带检查被退回；平台目标的计划写 infra 被退回；不认识的仓库被拒。
- 端到端（平台，本地测试库）：`POST /goals`（infra）→ 计划者交计划 → 收下 → 实现任务（agentd 领活：Setup 先跑、执行者改一个文件、推送不含 venv）
  → `StartVerification` → agentd 用自己的确定性执行者在推送的提交上先跑 Setup、再跑 infra 的命令（venv 在 PATH 最前、pip 不读配置文件、GOCACHE 是这次检查尝试自己的临时目录下的 go-build）→ 通过 → 进评审。
  `python3` 用记录调用的替身，不下载东西；真跑见上表。
- 真 pytest 的回归测试（主机有 pytest 时跑，CI 没有就跳过）：失败的测试在根目录各种配置、`conftest.py` 和上级目录配置下都判失败；换回复核 330 前的命令，六种植入全部「假通过」。
  另有五种 `__init__.py` 植入（根目录、`scripts/`、入选目录内、更深一层带自己的测试、链接）都被点名拒绝；换回 `0e52030` 的命令，五种全部「假通过」。
- 变异：把 Verify 里的 PATH 前缀去掉，端到端和单元测试都变红。
- 平台全套 `go test ./...`（测试库、Redis）过；改动的文件 golangci-lint 0 条（仓库其余文件原有 100 条，CI 不跑 golangci-lint）；code-health 12/12（阳性对照触发 13 > 12）。
- 复核：Codex 330（1 A、5 B、1 C）→ `0e52030` 全部照改，A 与 B 各配在旧代码上失败的测试；窄确认 331（B2–B5、C1 确认修好；新 1 A、1 B）→ `0c5ad12`：
  A 照改并配旧代码上失败的测试，B（shell 里已有 alias 时首词会被展开）把注释的承诺收窄到「没有 alias 的 shell」。按 10-17 的规矩到此收线。

## 没能在本机量的（06 上第一次 infra 任务时看）

- 06 上冷启动的真实用时（pip 从 PyPI 下六个 wheel、Python 3.12、16 核），以及旧 agentd 与写墙 agentd、codex 沙箱三种情况下的通过数。
- 06 主机上是否有全局 pip 配置——现在不读了，不影响结果。
