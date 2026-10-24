# Dots 本机测试：Owner 与太太操作页

目的：完成 V1/V2；只用合成文字 `hello`，不接业务平台。
入口依据：[接业务设计 §11](DESIGN-crew-intake-2026-10-22.md) 的 10-23 截图记录。
本页没有在她 Mac 上实测；入口不同就记「未核实」。

## 1. 加一个只回声的本机 MCP

在她 Mac 点 Spotlight，输入 `Terminal`，回车。
先粘贴 `/usr/bin/python3 --version`；没有版本输出就停止并记录。
不要为测试改变 `Full access`、Approval 或 Sandbox。
再粘贴整段；只创建测试脚本，注册名为 `bifrost_echo_probe` 的 MCP。
若已有同名测试配置，先停下核对，避免覆盖。

```bash
mkdir -p "$HOME/Library/Application Support/BifrostDotsProbe"
cat > "$HOME/Library/Application Support/BifrostDotsProbe/echo.py" <<'PY'
import json, sys
tool = {"name": "echo", "description": "Echo synthetic test text only.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                        "required": ["text"], "additionalProperties": False}}
for line in sys.stdin:
    try:
        q = json.loads(line)
    except ValueError:
        continue
    if not isinstance(q, dict) or "id" not in q:
        continue
    method, p = q.get("method"), q.get("params") or {}
    error, result = None, {}
    if method == "initialize":
        result = {"protocolVersion": p.get("protocolVersion", "2024-11-05"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "bifrost-echo-probe", "version": "1.0"}}
    elif method == "tools/list":
        result = {"tools": [tool]}
    elif method == "tools/call":
        a = p.get("arguments", {})
        if p.get("name") == "echo" and set(a) == {"text"} and isinstance(a["text"], str):
            result = {"content": [{"type": "text", "text": a["text"]}]}
        else:
            error = {"code": -32602, "message": "Invalid echo arguments"}
    elif method != "ping":
        error = {"code": -32601, "message": "Method not found"}
    reply = {"jsonrpc": "2.0", "id": q["id"]}
    reply.update({"error": error} if error else {"result": result})
    print(json.dumps(reply), flush=True)
PY
"/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex" mcp add bifrost_echo_probe -- /usr/bin/python3 -u "$HOME/Library/Application Support/BifrostDotsProbe/echo.py"
```

脚本只读 stdin、写 stdout；没有网络、文件读取或命令执行工具。
它不记录输入，也不读取令牌。
注册命令按本机 CLI 的 `mcp add --help` 核对。
若应用路径不存在，记录失败；不要下载替代软件。

点 `ChatGPT → Settings → Integrations → Plugins → MCPs`。
查找 `bifrost_echo_probe`；需要重载时退出并重开 ChatGPT。
`Configuration → Open config.toml` 是截图确认的配置入口。
不要复制配置全文；只核对新增服务名。

## 2. V1：分别测试 Codex 与 Dots

先点 `New chat`，选择 Codex；再去她已有的 Dots 对话。
在两个入口分别输入以下文字；第二次把 `hello-1` 换为 `hello-2`。

> 请调用 bifrost_echo_probe 的 echo 工具，text 为 hello-1。不要用普通文字模拟返回，也不要改用终端。调用不可用就说不可用。

展开每次工具调用记录，核对工具名、参数和真实结果。
若弹允许框，只选本次允许；记录是否每次都弹。
再开一个新对话测试 `hello-3`，检查授权是否跨对话保留。
记录三个结果：每次允许、首次允许、从不询问，或不可用。
Codex 能调不代表 Dots 能调；两行分别填写。
Dots 没有该工具时，在插件选择器选已装的 `Remote Desktop Commander`。
输入：「只在我的 Mac 执行 `/bin/echo hello`，显示真实调用结果。」
重复一次并记录授权；这是命令插件兜底，不算 MCP 通过。

## 3. V2：定时在哪跑

在 Dots 输入：「请建一个五分钟后运行的一次性任务，名为 Bifrost echo awake。调用 bifrost_echo_probe 的 echo，text 为 hello-awake。不要改用其他工具。保留实际调用记录，失败就如实报告。」
核对任务已创建、有执行时间；保持 Mac 唤醒，等它执行。
再输入：「请建一个五分钟后运行的一次性任务，名为 Bifrost echo asleep。调用同一个 echo，text 为 hello-asleep。不要改用其他工具。保留实际调用记录，失败就如实报告。」
确认创建后，点 `Apple 菜单 → Sleep`；七分钟后唤醒。
打开两次任务的执行记录，核对开始时间、工具与执行环境。
若定时创建失败或没有任务记录，V2 写「未核实」。

| 看到什么 | 怎么记 |
|---|---|
| 云端任务记录，找不到本机 MCP | 云端定时；本机桥不可达 |
| 记录明确显示 Mac 本地执行 | 本机定时；附时间与入口 |
| 云端调度，再经远控到 Mac | 云端加远控；不能写成本机定时 |
| 只有 Dots 自述或唤醒后才完成 | 位置未核实；补记时间差 |
| Mac 睡眠时仍完成 | 只能证明不依赖 Mac 在线；位置还看执行记录 |

不能后台调用时，按既定方案：云端整理草稿，桌面交互时提交。
只回声不测业务写权限；无弹窗不能推导七个业务工具都免批。

**结果写在她 Mac 的 Apple Notes，新建笔记 `Bifrost Dots V1 V2 2026-10-24`。**
记录：应用版本、入口、三次授权结果、awake/asleep 时间、环境证据、未核实项。
只记测试文字和技术结果；不贴配置、私人对话或截图。
Owner 把这些技术结果带回统筹线程，写入接业务设计 §11 的 V1/V2。
最后在任务记录中取消尚未执行的测试任务。
在 MCPs 中停用测试项；移除注册可运行：

```bash
"/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex" mcp remove bifrost_echo_probe
```
