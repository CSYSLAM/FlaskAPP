# 手机控制台 · 设计文档

> 讲清「是什么 / 为什么这么设计」。实现细节见 [实现文档](implementation.md)，踩过的坑见 [踩坑文档](pitfalls.md)，怎么用见 [使用文档](usage.md)。

## 一句话定位

手机控制台是一个**独立的 Flask 服务（端口 8765）**，让你在手机浏览器上：驱动本机 Claude Code / CodeBuddy 改代码 + 启停游戏进程 + 实时看日志。它和游戏 app（`app.py`，端口 5000）是两个完全独立的进程，**不 import 任何游戏模块**，可以单独删除/移动而不影响游戏。

## 解决的问题

项目是 Flask 文字 RPG（见根目录 `CLAUDE.md`）。开发者想在外出时用手机「改代码 + 看运行效果」闭环。手机浏览器没法直接 ssh，也没法跑 Claude Code 的交互式 CLI，所以需要一个中间层：**把手机 HTTP 请求翻译成「调 claude CLI / 管 flask 进程」，再把子进程输出实时推回手机**。

## 两个进程，互不依赖

| 进程 | 端口 | 是什么 | 谁起的 |
|------|------|--------|--------|
| 控制台 | 8765 | `mobile_console/run.py`，一个 Flask app | 用户手动 / systemd / `restart.sh` |
| 游戏 | 5000 | `app.py` 的 `create_app()`，由 gunicorn 跑 | 控制台在手机上点「启动 Flask」时拉起 |

控制台是游戏的「管家」：它能启停游戏进程，但游戏跑不跑不影响控制台本身运行。反过来，游戏对控制台一无所知。

## 核心设计决策

### 1. AI CLI 用「任务队列」而非长驻进程

`claude` / `codebuddy` 等 CLI 有两种模式：
- **默认交互模式**：要 TTY。手机网页是非 TTY，用不了。
- **`-p`（print）模式**：一次性。每条指令跑完进程就退出。

没法让一个 CLI 进程常驻着、手机往里灌指令。所以采用**任务队列 + 逐条调用**模型（被 `AgentRunner` 抽象，Claude / CodeBuddy 共用）：

```
手机发指令 → POST /api/send/<key> → 入 task_q 队列(key=claude/codebuddy)
                                      ↓
                          后台 _work_loop 线程逐条出队
                                      ↓
        subprocess: <binary> -p [--continue] --dangerously-skip-permissions
        (prompt 从 stdin 投递，写完立即 close → CLI 收 EOF 开始处理)
                                      ↓
        逐行读 stdout → push 到 log_q(按 self.key 打 tag) → SSE 实时推给手机
```

- 首条指令不带 `--continue`（没会话可续），之后每条带 `--continue` 接续同一会话，**CLI 记得前文**（记忆链靠 CLI 自己的会话存储，在 `~/.claude/` 或 `~/.codebuddy/` 下，不是控制台管的）。
- 队列模式天然支持「排队」：上一条没跑完时，新指令入队等，前端显示「排队 N」。
- tag 用 `self.key`，所以 claude 输出进 `log-claude`、codebuddy 输出进 `log-codebuddy`，两个 agent 互不串。

### 2. 无人值守（`--dangerously-skip-permissions`）

手机端没法逐条点「允许执行」，所以加 `--dangerously-skip-permissions` 跳过所有权限确认，Claude 直接读改代码/跑命令。

**风险已知且用户已接受**：任何从手机输入的指令都会无确认执行。所以必须配密码保护，且只在私人/受信场景用。想恢复逐项授权：去掉 `_run_one` 里的这个 flag。

### 3. prompt 走 stdin，不走 argv

中文 prompt 不能放命令行参数：
- Windows：`claude.cmd` 是批处理，`cmd.exe` 按 GBK 重新解析 argv，UTF-8 中文变 `?`。
- Linux：`runuser -l console -c '... claude ...'` 包了一层 shell，argv 塞中文 + 引号太脆。

所以 prompt 统一走 stdin（UTF-8 管道），写完立即 `close()`，claude 收到 EOF 开始处理。详见 [踩坑文档](pitfalls.md)。

### 4. Linux 下 claude 必须降权到非 root 用户（codebuddy 不需要）

claude CLI 2.1+ 拒绝以 root 跑 `--dangerously-skip-permissions`（报 `cannot be used with root/sudo privileges`）。但控制台本身常以 root 跑（服务器/systemd）。所以 Linux 下调 claude 用 `runuser -l console -c '...'` 切到 `console` 用户执行，ANTHROPIC 凭据从 `/home/console/.claude.env` 加载。

codebuddy 允许 root 下 `--dangerously-skip-permissions`，且凭据在运行用户自己的 `~/.codebuddy` 下，因此 `AgentRunner` 对 codebuddy 设 `drop_user=None`，**直接以当前用户（root）跑**，不经过 `runuser`、不额外 source env——两个 agent 互不干扰，可同时运行。详见 [踩坑文档](pitfalls.md)。

### 5. 日志双写：内存队列 + 持久化文件

历史上有两个需求拉扯：
- **实时推手机**：子进程输出要尽快喂给 SSE → 用内存 `queue.Queue(maxsize=2000)`，满了丢旧的。
- **电脑端查历史**：手机发的指令有时电脑上想回看，但内存队列服务重启就没了。

所以 AI 交互（`AgentRunner._push`）做**双写**：入内存队列（推手机）+ 追加到 `mobile_console/logs/<log_prefix>-YYYY-MM-DD.log`（claude→`claude-*.log`，codebuddy→`codebuddy-*.log`，电脑可 `tail`/`cat`，重启不丢）。Flask 进程的日志只入内存队列（不持久化），因为它有自己的 gunicorn 日志。

### 6. 游戏用 gunicorn 而非 Flask dev server

`app.run(debug=True)` 的 dev server 在移动端多连接 / keep-alive 下会「网页无法加载」。改用 gunicorn（`-w 4 -k gthread --threads 4`，16 并发）彻底解决。控制台的「启动 Flask」就是拉起 gunicorn，stop 时用 `killpg` 杀整个进程组（master + workers），不留孤儿。

### 7. 鉴权：session cookie + 登录页 + 单窗口登录

公网部署必须鉴权。早期用 Basic Auth，后改成 session cookie + 登录页（体验更好，且 SSE 配 cookie 比 Basic Auth 稳）。额外两点：
- **cookie 名独立**：`mobile_console_session`，不和游戏 app 的 `session` cookie 撞（浏览器 cookie 按域共享不区分端口，撞名会互相覆盖，导致访问游戏页后控制台被踢回登录）。
- **单窗口登录**：同一密码只允许一个有效 session，新登录踢掉旧 session，旧窗口下次请求/SSE 心跳时检测到被踢 → 前端弹全屏遮罩跳回登录页。

## 安全边界

- **控制台本身**：有密码，但走 HTTP 明文（公网下可被嗅探）。要更强上 Cloudflare 套 HTTPS（用户暂未要求）。
- **Claude 无人值守**：手机输入 = 直接代码执行权。密码别泄露。
- **`.passwd` 文件**：存密码，`chmod 600`，已在 `.gitignore`。
- **`logs/`**：可能含你贴进去的代码/敏感内容，已在 `.gitignore`。

## 不做什么

- 不碰游戏代码（`app.py` / `blueprints` / `services` / `models`）。
- 不做数据库迁移、不动游戏 schema。
- 不替代 ssh——它是「手机友好的 claude + flask 遥控器」，不是通用 shell。

## 配套：只读状态看板（电脑端防冲突）

有个场景：设计者在远程用手机控制台操作 Claude / 改代码，电脑端的你完全不知道，容易两边同时改代码冲突。所以加了一个**只读状态看板**，让电脑端随时看到「控制台 / Claude worker / Flask 各自跑没跑」，**只读、免登录、不影响手机任何功能**。

- `/api/peek`：免登录只读 JSON 端点，返回各进程开没开 + pid + 端口占用。**不含密码/日志内容，不支持任何写操作**。
- `/status`：配套的纯静态看板页（`status.html`），前端轮询 `/api/peek`，3s 刷新，有状态灯。任一 AI（Claude / CodeBuddy）处理中时醒目提示「有 AI 正在处理指令，请勿在电脑上同时改代码」。
- `status.sh`：终端版，`watch -n3 mobile_console/status.sh` 循环刷新。

关键设计：它**不登录**，所以不会触发单窗口登录踢人（不会把手机端的 session 踢掉）。手机端控制台一切照旧。详见 [实现文档](implementation.md#只读状态看板)。
