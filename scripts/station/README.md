# 办事指南：想办一件事，要带什么

Station 管（法 77，2026-11-21）。给任何一个新来的成员：办之前先查这里，不靠一次次被拒碰出来。

- 查：`python3 scripts/station/howto.py` 列出能查的事；`python3 scripts/station/howto.py land` 打印合入 main 要带什么。
- 办之前自查：`python3 scripts/station/precheck.py <检出目录> [<提交>]`，跑合入时同样的检查（同一份代码，从 `pipeline-land.yaml` 里读出来执行），告诉你会因为什么被拒。

## 格式 `station.requires/v1`

每件工具一个文件，放在 `requires/<tool>.yaml`。内容由管那件工具的线给，Station 收在这里、管格式。

| 键 | 是什么 |
|---|---|
| `tool` | 工具的名字，也是文件名 |
| `owner` | 管它的领域（归属表里的 domain id） |
| `task` | 用这件工具办的是什么事，按事来查 |
| `how` | 一两句：怎么办、怎么知道办成了 |
| `precheck` | 办之前自查的命令；没有就不写 |
| `checked_by` | 默认的检查文件（infra 里的路径） |
| `bring[]` | 要带的东西：`id`、`what`（要带什么）、`get_from`（缺了去哪拿）、`command`（可选）、`refused_with`（缺了会听到哪句：`says` 原文，`file` 不写就是 `checked_by`，不在 infra 的写 `repo`，不在仓库里的 `file: none`）、`precheck`（自查管没管：`checked`、`printed` 打印正确写法、`warned` 只提醒、`not-covered`） |
| `refusals[]` | 这件工具会说的每一句拒绝：`match`（原文前缀，`%s` 照脚本里写）、`kind`（`you` 推的人改、`system` 系统的毛病、`wall` 墙）、`do`（该做什么） |
| `ci_red[]`、`must_answer[]` | 可选：检查红了的几类怎么本地复现；找这条线它必须答的 |

对账（`test_requires.py`）：`refused_with.says`、`refusals[].match` 必须是检查文件里的原文；反过来，检查文件里每一句 `refused: …` 都要有一条 `refusals`。检查改了措辞，测试就红，指南必须跟着改，不会悄悄过期。不在 infra 里的（比如 platform 的 codeguard）写 `repo`，这里不对账；不在仓库里的（比如 auto mode）写 `file: none`。

现在只有合入一份，内容是 CI 线（3·4）给的。下一批：发布窗口、建卡、发信。每份由管它的线给内容。地图的读口怎么读这些文件，由地图线定。
