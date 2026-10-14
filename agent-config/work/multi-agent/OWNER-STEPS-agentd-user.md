# 给 agentd 建专用系统用户（你 10-14 15:49 回「A8 A」）

**为什么**：任务里的 codex / cursor 会加载「运行它的那个系统用户」配置的全部 MCP 服务器，包括平台的写工具；两个 CLI 都没有开关能清掉（10-14 实测）。让 agentd 以一个从没配过 MCP 的用户运行，任务就拿不到这些工具。

**在哪做**：你自己的终端（要 sudo 密码，所以不能由我执行）。一共 4 步，前 3 步现在就可以做；第 4 步等平台那半上线（Gate A 前）我再给你。

**做完怎么回**：线程里回「agentd 用户好了」，我读 `/tmp/agentd-user-check.txt` 核对，读完删掉。

---

## 1. 建用户（约 1 分钟）

会先问你的管理员密码，再问新用户的密码（自己定一个，记进密码管理器；agentd 运行时用不到它）。

```bash
sudo sysadminctl -addUser bifrost-agentd -fullName "Bifrost agentd" -password -
```

```bash
sudo createhomedir -c -u bifrost-agentd
```

不在登录界面显示它：

```bash
sudo dscl . create /Users/bifrost-agentd IsHidden 1
```

## 2. 给它 codex 并登录（约 3 分钟）

codex 用 ChatGPT 应用里自带的那一份，给新用户建一个链接：

```bash
sudo -u bifrost-agentd -H mkdir -p ~bifrost-agentd/.local/bin
```

```bash
sudo -u bifrost-agentd -H ln -sf /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex ~bifrost-agentd/.local/bin/codex
```

登录：它会打印一个网址和一个代码，在浏览器里打开网址、输入代码、用你的 ChatGPT 账号确认。

```bash
sudo -u bifrost-agentd -H ~bifrost-agentd/.local/bin/codex login --device-auth
```

## 3. 给它 cursor-agent 并登录（约 3 分钟）

cursor-agent 现在装在你自己的家目录里，新用户读不到，所以给它单独装一份。**这一步会从 cursor.com 下载安装脚本并运行**，是你的决定；不想装就跳过，agentd 只提供 codex 和确定性检查。

```bash
sudo -u bifrost-agentd -H bash -c 'curl https://cursor.com/install -fsS | bash'
```

登录：会打印一个网址，在浏览器里打开并确认。

```bash
sudo -u bifrost-agentd -H env NO_OPEN_BROWSER=1 ~bifrost-agentd/.local/bin/cursor-agent login
```

## 核对（把结果写进文件给我读）

```bash
{ sudo -u bifrost-agentd -H ~bifrost-agentd/.local/bin/codex login status; sudo -u bifrost-agentd -H ~bifrost-agentd/.local/bin/codex mcp list --json; sudo -u bifrost-agentd -H ~bifrost-agentd/.local/bin/cursor-agent status; sudo -u bifrost-agentd -H ls -la ~bifrost-agentd/.cursor; id bifrost-agentd; } > /tmp/agentd-user-check.txt 2>&1; echo exit=$? >> /tmp/agentd-user-check.txt
```

我看的是：codex 已登录；`mcp list` 是 `[]`；cursor 已登录；`~/.cursor` 里没有 `mcp.json`；用户不在 admin 组。cursor 的登录凭据可能存在钥匙串里，而这个用户从没在图形界面登录过：如果 `cursor-agent status` 说没登录，告诉我，我改用 API 密钥文件的方式（那时再给你步骤）。

## 4. 安装 agentd（以后，Gate A 前）

需要平台那半先上线：给这台主机签发 agentd 令牌、放进 `~bifrost-agentd/.config/bifrost/agentd.token`（属主 bifrost-agentd，权限 600），然后用 `sudo install-agentd.sh bifrost-agentd …` 安装成系统级 launchd 服务。到时我把确切命令（不留占位符）写在这一节。

## 这样做挡住了什么、没挡住什么

- 挡住：任务里的 Agent 通过 MCP 调平台的工具；Agent 读你家目录里的东西（新用户读不到你的家目录）。
- 没挡住（设计 §6.2、§7 第 7 条已接受，第 3 轮再做）：任务 Agent 和 agentd 是同一个用户，能读到 agentd 自己的令牌和 Git 令牌。
