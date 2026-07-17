# 手机控制台 · 实现文档

> 讲「代码长什么样 / 改哪里」。设计动机见 [设计文档](design.md)。本文对照 `mobile_console/run.py`（单文件，后端 + 内嵌前端 HTML/CSS/JS）。

## 文件总览

```
mobile_console/
├── run.py                 # 控制台全部代码(后端 + 内嵌前端单页),~1390 行
├── restart.sh             # 正确的重启脚本(先停干净再起,不留孤儿)
├── deploy.sh              # 全量部署脚本(装依赖 + 起,只在首次部署用)
├── mobile-console.service # systemd 单元(开机自启 + 崩溃重启)
├── .passwd                # 随机生成的访问密码(chmod 600,gitignore)
├── logs/                  # AI 交互历史持久化日志(按天,gitignore)
│   ├── claude-YYYY-MM-DD.log
│   └── codebuddy-YYYY-MM-DD.log
└── docs/                  # 本文档目录
```

`run.py` 没有拆分模块——整个控制台是一个文件，HTML 模板是文件底部两个大字符串（`LOGIN_HTML` / `PAGE_HTML`）。零额外依赖，只用 Flask 本身。

## 顶层常量与配置（run.py 顶部）

| 常量 | 值 | 说明 |
|------|----|------|
| `PROJECT_ROOT` | `FlaskAPP` 根目录 | claude / gunicorn 的工作目录 |
| `APP_PY` | `PROJECT_ROOT/app.py` | （历史遗留，实际已改用 gunicorn） |
| `PYTHON` | `sys.executable` | 当前解释器，跨平台 |
| `CONSOLE_PORT` | 8765 | 控制台端口 |
| `GAME_PORT` | 5000 | 游戏端口 |
| `LOG_DIR` | `mobile_console/logs/` | Claude 交互持久化日志目录 |
| `LAN_IP` | `get_public_ip()` | 页面预览链接用的 IP |

`get_public_ip()` = `PUBLIC_IP` 环境变量 > `get_lan_ip()`。服务器上 `PUBLIC_IP=117.72.209.69`（公网），否则 fallback 到内网网卡 IP。

## 两个核心类

### `ManagedProcess`（run.py:81）

一个受管的长驻子进程，实时把 stdout/stderr 行喂进共享队列供 SSE 推送。**用于 Flask（gunicorn）**。

关键方法：
- `start(cmd, cwd, env, shell)` — 跨平台 `Popen`。Windows 传 `creationflags=CREATE_NEW_PROCESS_GROUP`，Linux 传 `start_new_session=True`（让子进程整组可被杀）。
- `_read_loop()` — 后台线程，逐行读 stdout（超长行截断 8192），`_push` 进队列。
- `stop()` — Windows `CTRL_BREAK_EVENT`，Linux `os.killpg(SIGTERM)` 杀整个进程组。
- `send(text)` — 往 stdin 投一行（Flask 用不到，保留给通用场景）。
- `_push(line, tag)` — **只入内存队列，不持久化**。Flask 日志不落盘。

### `AgentRunner`（run.py:208）

通用 AI CLI 运行器（Claude / CodeBuddy 等）。**继承 `ManagedProcess`**（复用 `_push` / 日志双写 / `status`）。采用和「Claude 任务队列模型」相同的「逐条调 `<cli> -p`」方式，差别只在构造参数：

| 参数 | claude | codebuddy |
|------|--------|-----------|
| `binary` | `claude` | `codebuddy` |
| `log_prefix` | `claude` | `codebuddy` |
| `drop_user` | `console`（Linux 降权） | `None`（以当前用户/root 直接跑） |
| `env_file` | `~/.claude.env` | `None` |

关键方法：
- `start()` — 启动后台 `_work_loop` 线程。
- `submit(prompt)` — 入 `task_q` 队列，worker 逐条出队处理。
- `interrupt()` — 杀当前 CLI 子进程整个进程组 + 清空待办队列（等同按 Esc）。会设 `_interrupted` 标志，让 `_run_one` 不报「异常退出」。
- `_work_loop()` — `while self._started`：从 `task_q` 取一条 → `_push(prompt, "you")` 回显 → `_run_one(prompt)`。
- `_run_one(prompt)` — 组装并跑 `<binary> -p [--continue] --dangerously-skip-permissions`，prompt 走 stdin。逐行读 stdout 推队列（**tag 用 `self.key`**，所以 claude 输出进 `log-claude`、codebuddy 输出进 `log-codebuddy`，互不串）。首条成功后 `_has_session=True`，之后带 `--continue`。**详见下方「_run_one 平台分流」。**
- `_append_log(tag, line)` — **持久化日志**。按 `log_prefix` 写 `logs/<log_prefix>-YYYY-MM-DD.log`（claude→`claude-*.log`，codebuddy→`codebuddy-*.log`），多行内容每行带 `HH:MM:SS [tag]` 前缀，续行对齐。`_log_lock` 保证线程安全。失败静默（不影响主流程）。
- `_push(line, tag)` — **双写**：入内存队列（推手机）+ 调 `_append_log`（落盘）。

> 注意：`ManagedProcess._push` 和 `AgentRunner._push` 是两个独立方法。**只有 Claude/CodeBuddy 的会落盘**，Flask 的不会。

### `_run_one` 的平台分流（run.py:368，核心）

**Windows 分支**：
```python
cmd = [cli_bin, "-p", ("--continue",), "--dangerously-skip-permissions"]
# shell=True 仅当 cli 是 .cmd/.bat
Popen(cwd=PROJECT_ROOT, stdin=PIPE, creationflags=CREATE_NEW_PROCESS_GROUP, ...)
```

**Linux 分支（按 `drop_user` 分流）**：
- `drop_user` 设置时（claude，需降权到 console）：
  ```python
  inner = "claude -p --continue --dangerously-skip-permissions"  # shlex.quote 拼接
  # env_file 解析成降权用户的真实家目录绝对路径(/home/console/.claude.env):
  #   不能用 Python expanduser()(会以 root 解析成 /root),
  #   也不能字面 '~' 交给 shell 再用 shlex.quote 包成单引号(会阻止 ~ 展开)。
  shell_cmd = f"cd {PROJECT_ROOT} && source {env_path} && {inner}"
  cmd = ["runuser", "-l", "console", "-c", shell_cmd]
  ```
- `drop_user` 为 None 时（codebuddy，以当前用户/root 直接跑，凭据在自己 `~` 下）：
  ```python
  cmd = [cli_bin, "-p", "--continue", "--dangerously-skip-permissions"]   # 直接 Popen
  Popen(cwd=PROJECT_ROOT, stdin=PIPE, start_new_session=True, shell=False, ...)
  ```

为什么要 `runuser -l console` + `source /home/console/.claude.env`：
1. root 下 claude 2.1+ 拒绝 `--dangerously-skip-permissions` → 必须降权到 console 用户。
2. ANTHROPIC 凭据（`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` 等）存在 `/home/console/.claude.env`，由 console 用户加载。
3. `runuser -l` 是 login shell，会 `cd` 到家目录覆盖 Popen 的 cwd → 必须在 shell_cmd 里显式 `cd {PROJECT_ROOT}`。
4. codebuddy 允许 root 下 `--dangerously-skip-permissions`，且凭据在运行用户自己的 `~/.codebuddy` 下 → 无需降权、无需额外 source，直接以当前用户跑，互不干扰。

prompt 传递：`proc.stdin.write(prompt); proc.stdin.close()` → CLI 收 EOF 开始处理。

## 全局实例与 PROCS 字典（run.py:447）

```python
claude_proc = AgentRunner(key="claude", name="Claude Code", color="claude",
                          binary="claude", log_prefix="claude",
                          drop_user="console", env_file="~/.claude.env")
codebuddy_proc = AgentRunner(key="codebuddy", name="CodeBuddy", color="codebuddy",
                             binary="codebuddy", log_prefix="codebuddy",
                             drop_user=None, env_file=None)
flask_proc = ManagedProcess("flask", "FlaskAPP (app.py)", "flask")
PROCS = {"claude": claude_proc, "codebuddy": codebuddy_proc, "flask": flask_proc}
```

`start_flask()` 组装 gunicorn 命令调 `flask_proc.start()`；`start_claude()` / `start_codebuddy()` 分别调各自 `AgentRunner.start()`。`start_agent(key)` 按 key 统一分发（供 `/api/start` `/api/restart` 复用）。

## Flask app 与鉴权（run.py:495）

### 密码加载（`_load_or_gen_password`）
优先级：`MOBILE_CONSOLE_PASSWORD` 环境变量 > `mobile_console/.passwd` 文件 > 启动时 `secrets.token_urlsafe(12)` 随机生成并写进 `.passwd`（chmod 600）+ 打印到终端。

`app.secret_key = CONSOLE_PASSWORD`（session 签名密钥复用密码）。

### cookie 配置
```python
SESSION_COOKIE_NAME = "mobile_console_session"  # 故意和游戏 app 的 "session" 区分
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
```
原因：浏览器 cookie 按域共享不区分端口，两边都叫 `session` 会互相覆盖。

### 单窗口登录
- `_ACTIVE_TOKEN`：全局，当前唯一有效的登录 token。
- `_new_login()`：生成新 token 设进 session，并令其成为唯一有效 token（踢掉旧窗口）。
- `_is_current_session()`：当前 session 的 token 是否仍等于 `_ACTIVE_TOKEN`。
- `@app.before_request _require_auth`：登录页 + `/api/login` + favicon 放行；其余未登录 → 页面请求重定向登录页，API/SSE 返回 401（前端 `onKicked()` 弹遮罩）。

## API 清单

| 方法 | 路径 | 鉴权 | 作用 |
|------|------|------|------|
| GET | `/login` | 免 | 登录页 |
| POST | `/api/login` | 免 | body=密码，验密登录 |
| POST | `/api/logout` | 登录 | 清 session |
| GET | `/` | 登录 | 主页（PAGE_HTML） |
| GET | `/status` | **免** | 只读看板页（status.html） |
| GET | `/api/peek` | **免** | 只读状态 JSON（供看板/终端） |
| GET | `/api/status` | 登录 | 各进程状态 + lan_ip + game_url |
| POST | `/api/start/<key>` | 登录 | key=claude/codebuddy/flask，启动 |
| POST | `/api/startall` | 登录 | 一键启 Claude + CodeBuddy + Flask |
| POST | `/api/stop/<key>` | 登录 | 停止 |
| POST | `/api/restart/<key>` | 登录 | 重启 |
| POST | `/api/send/<key>` | 登录 | key=claude/codebuddy 入队；key=flask 投 stdin |
| POST | `/api/interrupt/<key>` | 登录 | 打断指定 agent 当前指令 |
| POST | `/api/upload` | 登录 | 上传 .txt/.md，返回上下文块 |
| GET | `/api/logs` | 登录 | SSE 流，实时推所有进程日志 |
| GET | `/api/logdump` | 登录 | 非流式快照（诊断用，会清空队列） |

## 只读状态看板（电脑端防冲突）

让电脑端在不登录、不影响手机端的前提下查看运行状态。三个文件：

- **`/api/peek`**（run.py，免登录）：复用 `PROCS` 的 `status()`，返回 `console` / `claude` / `codebuddy` / `flask` 各自的 running/pid/端口占用 + `lan_ip`。`_port_listening(port)` 用 `socket.connect_ex` 探测端口。`@app.before_request` 放行 `/api/peek` 和 `/status`。
- **`/status`**（run.py `status_page`）：免登录，从磁盘读 `status.html` 返回。
- **`status.html`**：纯静态前端，3s 轮询 `/api/peek`，状态灯（绿=运行、橙=处理中/端口占用、灰=未运行）。任一 AI（Claude / CodeBuddy）busy 时顶部弹冲突预警条。`peekUrl()` 支持 `?host=` 参数连别的地址，否则同源，兜底 `127.0.0.1:8765`（支持 `file://` 直接打开）。
- **`status.sh`**：终端版，curl `/api/peek` 后用 python3 解析格式化打印。

**为什么免登录不破坏单窗口登录**：看板不调 `/api/login`，不会生成 token、不会改 `_ACTIVE_TOKEN`，所以不会踢掉手机端的 session。它只是读 `PROCS` 的内存状态。

改动入口：

| 想改 | 改哪里 |
|------|--------|
| 看板 UI | `status.html` |
| peek 返回字段 | `api_peek`（run.py） |
| 放行清单 | `_require_auth` 里的 `request.path in (...)` |
| 终端输出 | `status.sh` 的 python 解析段 |

## SSE 数据流（run.py:730 `api_logs`）

生成器 `stream()` 轮询所有 `PROCS` 的 `log_q`，有就 `yield` 一条 JSON（`{ts, tag, line}`），每 ~15s 发心跳防代理断连。前端 `EventSource('/api/logs')` 自动带同源 cookie，`onmessage` 按 `tag` 分流到 `log-all` / `log-claude` / `log-codebuddy` / `log-flask` 四个终端区。

## 前端（PAGE_HTML，run.py:833）

单页 + 原生 JS，无框架。四个 tab：控制台总览 / Claude / CodeBuddy / Flask。关键行为：
- `connectSSE()`：建 SSE，`onerror` 1.5s 后重连（除非已被踢）。
- `refreshStatus()`：每 3s 轮询 `/api/status`，更新状态灯 + busy 横幅。
- `send(key)`：把已载入的文件上下文块（`_fileBlocks[key]`，按 agent 隔离）拼在指令前一起发，发送后清空。
- `onFilesPicked(input, agent)`：逐个上传文件，服务端返回上下文块，前端按 agent 累积成 chip，可单独移除。
- `interruptAgent(key)`：打断指定 agent（等同按 Esc，不影响会话记忆）。
- `onKicked()`：被踢时弹全屏遮罩，`_kickedShown` 保证只弹一次。

## 持久化日志格式（`logs/claude-YYYY-MM-DD.log` 与 `logs/codebuddy-YYYY-MM-DD.log`）

```
10:50:13 [you] test
10:50:13 [sys] ▶ 调用: claude -p --dangerously-skip-permissions "<你的指令>"
10:50:20 [claude] Test received. What would you like me to help you with?
10:50:20 [claude]
10:50:20 [claude] Looking at your repo...
10:50:20 [sys] ■ 本条完成 (exit=0)
```

（codebuddy 日志同构，tag 用 `codebuddy`，文件为 `codebuddy-YYYY-MM-DD.log`。）

tag 缩写：`you` / `claude` / `codebuddy` / `sys`(system) / `ERR`(error)。多行回复续行对齐（缩进等于时间戳+标签宽度），方便 `grep` / `tail` 时行行可定位。

## 改代码时的常见入口

| 想改 | 改哪里 |
|------|--------|
| AI 调用参数 | `AgentRunner._run_one`（run.py:368） |
| 恢复逐项授权 | 去掉 `_run_one` 里 `--dangerously-skip-permissions` |
| 持久化更多东西 | 在 `AgentRunner._push` 里已是双写；要给 Flask 也落盘就改 `ManagedProcess._push` 加 `_append_log` |
| 加新 AI agent | 新增 `AgentRunner(...)` 实例加进 `PROCS`，并补前端 tab/section |
| 改前端 UI | `PAGE_HTML` / `LOGIN_HTML` 字符串 |
| 改端口/路径 | 顶部常量区（run.py:32-41） |
| 加新受管进程 | 新建 `ManagedProcess(...)` 实例加进 `PROCS` |
