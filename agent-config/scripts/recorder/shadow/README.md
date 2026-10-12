# 影子周：统筹方要跑的命令

都在 `bifrost-trade-infra` 里。状态在 `--root`（默认 `~/agent-work/shadow-recorder`）。`start-step` 先看 `rec.py --help` 有没有 `run`：有就走 `run`，没有就自己起监督进程，用 `declare` / `start` / `finish` 记账。今天没有 `run`。

## 派出一件活

```bash
python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  start-step \
  --title "工作标题" \
  --step "步骤名" \
  --pattern "给 pgrep -f 的文字" \
  --done /绝对路径/job.done
```

成功时打一行 `pid=<监督进程或 run 的 pid>`，退出码 0。完成标记里第一次出现的 `exit=<非负整数>` 是这件活的退出码。进程没了、标记再缺 30 秒，影子以 70 结束。

## 关掉一步不是进程的步骤

```bash
python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  mark --title "工作标题" -- \
  open --work w1 --title "工作标题"

python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  mark --title "工作标题" --step "步骤名" -- \
  declare --work w1 --name "步骤名" --kind other --who Cursor --watch none

python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  mark --title "工作标题" --step "步骤名" -- \
  start --work w1 --step <declare 印出的 step_id>

python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  mark --title "工作标题" --step "步骤名" -- \
  finish --work w1 --step <step_id> --reported finished
```

`mark` 把记录器的标准输出、标准错误和退出码原样交还。失败时不写映射。

## 比一次，报一天

```bash
python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  compare --board /绝对路径/status.json

python3 agent-config/scripts/recorder/shadow/shadow.py \
  --root "$HOME/agent-work/shadow-recorder" \
  report --day 2026-10-12
```

`compare` 的汇总行是 `steps=… owners=… differences=…`。记录器的命令行还记不下 Owner 事项时，另有一行 `owner items not comparable: the recorder cannot record them (TD-319 item 5)`，不为它们逐条写差异。折叠出来的开着的 Owner 事项没有 `since` 时，另有一行 `since of owner items not comparable (TD-319 item 6)`。这两行都是当场试出来的，记录器修好了就自己消失。读不到看板、映射或差异日志时退出码 2，否则 0。

`report` 打一行 `comparisons=… differences=… 脚本错=… 看板错=… 两边的模型不同=… unexplained=…`。分类在统筹方自己留的 `triage.json`，形如 `{"d1": "脚本错"}`。

监督进程先死、结束没记上时，这一步的状态类是 `started_supervisor_gone`（已经开始，监督进程没了），不会被当成还在跑。

## 映射 `map.json`

`works`：`title` 看板标题，`work_id` 记录器工作 id。

`steps`：`title`、`name` 看板的标题和步骤名；`work_id`、`step_id` 记录器 id；`pattern` 给 `pgrep -f` 的文字；`done` 完成标记的路径；`pid` 脱离后还在的进程（`run`，或记账路径上的监督进程）；`run_id` 这次开始的运行 id；`run_exit` 启动后两秒内已经退出时的退出码，还在跑就是 `null`；`via` 是 `run` 或 `bookkeeping`。

`owners`：`title`、`name` 看板标题和事项名；`work_id`、`wait_id` 记录器 id。命令行记不下 `owner-open` 时，这里不会多出一条。
