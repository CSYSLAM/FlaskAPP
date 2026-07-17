# 手机控制台 · 踩坑文档

> 实际部署/运行中踩过的坑，按「会再犯」的可能性排序。每条含现象、根因、解法。改代码或部署前过一遍，能省很多事。设计背景见 [设计文档](design.md)。

##坑 1（最高频）：重启 mobile_console 留下孤儿 gunicorn 占着 5000

**现象**：重启 mobile_console 后，手机点「启动 Flask」报 `Address already in use: ('0.0.0.0', 5000)`，gunicorn 起不来。

**根因**：mobile_console（run.py）起的 gunicorn 用了 `start_new_session=True`，**脱离了父进程**。如果直接 `pkill -f "mobile_console/run.py"` 杀主进程，gunicorn（占 5000）和 claude 子进程不会跟着死，变成孤儿继续占端口。新 mobile_console 起的 gunicorn 自然就 `Address already in use`。

> 注意：这**不是** `ManagedProcess.stop()` 的 bug——它的 `stop()` 用 `killpg` 杀整个进程组，是干净的。问题出在「绕过 stop() 直接 pkill 主进程」这个操作上。

**解法**：
- **重启用 `bash mobile_console/restart.sh`**，它会：pkill run.py + pkill gunicorn + pkill runuser-claude → 确认 5000/8765 释放 → 再 setsid 起新进程。
- **不要**用 `deploy.sh` 重启（它是全量部署，会重装依赖，还假设路径 `/root/FlaskAPP`）。
- **不要**直接 `pkill -f "mobile_console/run.py"`。
- 已经留了孤儿的话：`kill <gunicorn master pid>`（master 收到 TERM 会带走所有 worker），或 `pkill -f "gunicorn.*app:create_app"`。

## 坑 2：root 下 claude 拒绝 `--dangerously-skip-permissions`

**现象**：Linux 上以 root 跑 mobile_console，手机发指令调 claude，claude 报 `--dangerously-skip-permissions: cannot be used with root/sudo privileges`，指令失败。

**根因**：claude CLI 2.1+ 出于安全，禁止 root 用 `--dangerously-skip-permissions`。但服务器/systemd 常以 root 跑控制台。

**解法**：`AgentRunner._run_one` Linux 分支（claude，`drop_user="console"`）用 `runuser -l console -c '...'` 切到 `console` 用户跑 claude：
```python
shell_cmd = f"cd {PROJECT_ROOT} && source /home/console/.claude.env && {inner}"
cmd = ["runuser", "-l", "console", "-c", shell_cmd]
```
前提：服务器上要有一个 `console` 用户，且 `/home/console/.claude.env` 里写好 ANTHROPIC 凭据。

> codebuddy 不需要降权：`AgentRunner` 对 codebuddy 设 `drop_user=None`，直接以当前用户（root）跑，凭据在 `~/.codebuddy` 下，互不干扰。详见 [坑13](#坑-13env_file-路径解析错导致-source-失败)。

## 坑 3：ANTHROPIC 凭据不是 `ANTHROPIC_API_KEY`

**现象**：照 `deploy.sh` / `mobile-console.service` 里写的设 `ANTHROPIC_API_KEY=xxx`，但手机发指令 claude 仍认证失败。

**根因**：这套环境实际用的是**自建中转**（`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`），不是官方 `ANTHROPIC_API_KEY`。凭据存在 `/home/console/.claude.env`，由 `runuser -l console` + `source ~/.claude.env` 加载。控制台进程自己的环境**不需要**任何 ANTHROPIC 变量。

**解法**：
- 把全部 ANTHROPIC 变量写进 `/home/console/.claude.env`（chmod 600，console 用户可读）：
  ```
  export ANTHROPIC_AUTH_TOKEN=...
  export ANTHROPIC_BASE_URL=https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic
  export ANTHROPIC_MODEL=...
  export ANTHROPIC_DEFAULT_SONNET_MODEL=...
  # ... 其余 ANTHROPIC_DEFAULT_*
  ```
- mobile_console 启动时**不用**传 ANTHROPIC 变量，`restart.sh` 也没传。
- `deploy.sh` / `mobile-console.service` 里那个 `ANTHROPIC_API_KEY` 是早期官方直连方案遗留的，**当前环境用不上**，可忽略（文档里保留是历史遗留，改它不影响）。

## 坑 4：`runuser -l` 覆盖了工作目录

**现象**：Linux 下 claude 报「找不到项目代码 / trust 不匹配」，或在工作目录不对的地方操作。

**根因**：`runuser -l console` 是 **login shell**，启动时会先 `cd` 到 console 家目录（`/home/console`），**覆盖了 Popen 的 `cwd=PROJECT_ROOT`**。claude 以为工作目录是 `/home/console`，看不到项目代码。

**解法**：在 shell_cmd 里显式 `cd` 回项目根：
```python
shell_cmd = f"cd {shlex.quote(str(PROJECT_ROOT))} && source ~/.claude.env && {inner}"
```
注意 `Popen(cwd=PROJECT_ROOT)` 仍要保留（双保险）。

## 坑 5：`creationflags` 是 Windows 专属，Linux 上 TypeError

**现象**：早期代码在 Linux 启动 Claude/Flask 时崩 `TypeError: __init__() got an unexpected keyword argument 'creationflags'`。

**根因**：`subprocess.Popen` 在 Linux 上不认 `creationflags`（Windows 专属）。

**解法**：按平台分流组装 kwargs：
```python
if os.name == "nt":
    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    popen_kwargs["start_new_session"] = True   # setsid，让 stop 能 killpg
```
`ManagedProcess.start` 和 `ClaudeRunner._run_one` 都改了。

## 坑 6：Linux 上 stop 只 terminate 父进程，留孤儿占端口

**现象**：手机点「停止 Flask」，状态显示停了，但 5000 端口没释放，重启报 `Address already in use`。

**根因**：gunicorn（或 Flask reloader）会 fork 子进程，真正监听端口的是 worker 子进程。只 `proc.terminate()` 杀父进程，子进程变孤儿继续占端口。

**解法**：`ManagedProcess.stop` Linux 分支用 `os.killpg(os.getpgid(self.proc.pid), SIGTERM)` 杀整个进程组（靠 `start_new_session=True` 建的 session）。Windows 用 `CTRL_BREAK_EVENT`。

## 坑 7：中文 prompt 走 argv 会变 `?`

**现象**：手机发中文指令，Claude 收到全是问号，答非所问。

**根因**：
- Windows：`claude.cmd` 是批处理，`cmd.exe` 按 ANSI 代码页（GBK）重新解析 argv，UTF-8 中文变 `?`。
- Linux：`runuser -l console -c '...'` 包了一层 shell，argv 塞中文 + 引号太脆。

**解法**：prompt 不放 argv，统一走 stdin（UTF-8 管道）：
```python
proc.stdin.write(prompt)
proc.stdin.close()   # 关键：写完立即 close → claude 收 EOF 开始处理
```

## 坑 8：claude -p 的 stdin 不关会挂起 3 秒

**现象**：发指令后 claude 卡住不输出，或打印 `Warning: no stdin data received in 3s`。

**根因**：`claude -p` 启动后会等 stdin（以为有管道输入），若 stdin 一直不关，它会等 3 秒甚至挂死。

**解法**：写完 prompt 立即 `proc.stdin.close()`。注意：`ManagedProcess`（Flask）的 stdin 要保留 PIPE（Flask 不读 stdin 无所谓），只有 Claude 的子进程必须 close。

## 坑 9：cookie 名和游戏 app 撞车，导致被踢回登录页

**现象**：在控制台点「打开游戏页面」访问 5000 后，回到控制台发现被踢回登录页。

**根因**：浏览器 cookie 按**域**共享、**不区分端口**。控制台和游戏同域（都是 `117.72.209.69`），如果两边 session cookie 都叫默认的 `session`，会互相覆盖。

**解法**：控制台 cookie 名改成 `mobile_console_session`：
```python
app.config.update(SESSION_COOKIE_NAME="mobile_console_session", ...)
```

## 坑 10：`python` 是 2.7，run.py 用 f-string

**现象**：`python -m py_compile mobile_console/run.py` 报 SyntaxError，但代码看着没问题。

**根因**：服务器上 `python` 指向 Python 2.7.18，而 run.py 全是 f-string（3.6+）。

**解法**：始终用 `python3` 或 venv 的 python（`/mnt/FlaskAPP/venv/bin/python`）。`restart.sh` 用的是 venv python，没问题。

## 坑 11：`deploy.sh` 假设路径 `/root/FlaskAPP`

**现象**：在当前服务器跑 `bash mobile_console/deploy.sh`，脚本在「准备项目代码」步骤报 `!!! /root/FlaskAPP 不是 git 仓库 !!!` 并退出，没重启。

**根因**：`deploy.sh` 硬编码 `PROJECT_DIR=${PROJECT_DIR:-/root/FlaskAPP}`，但本机项目实际在 `/mnt/FlaskAPP`。

**解法**：要么 `PROJECT_DIR=/mnt/FlaskAPP bash mobile_console/deploy.sh`，要么直接别用 deploy.sh 重启（用 `restart.sh`）。deploy.sh 是首次全量部署用的，不是日常重启用的。

## 坑 12：超长无换行输出导致 OOM / 卡顿

**现象**：偶发 claude dump 出大块无换行内容（base64 / 压缩 JSON），手机端卡。

**解法**：`_read_loop` / `_run_one` 逐行读时，超 8192 字符的行截断：
```python
if len(line) > MAX_LINE:
    line = line[:MAX_LINE] + f" …[截断,本行原长{len(line)}字符]\n"
```

## 坑 13：`env_file` 路径解析错，导致 `source` 失败

**现象**：手机发指令调 claude，日志里出现 `/root/.claude.env: Permission denied`，或 `~/.claude.env: No such file or directory`，claude 起不来（且往往是在「同时开着 codebuddy」时才被发现，因为 codebuddy 以 root 跑、claude 降权到 console，两者环境不同）。

**根因**：`env_file` 配的是 `~/.claude.env`（相对 console 家目录）。两种错误写法：
1. 在 Python（以 root 运行）里 `Path(env_file).expanduser()` → `~` 被解析成 `/root`，runuser 以 console 身份去读 `/root/.claude.env` → 没权限 → **Permission denied**。
2. 把字面 `~` 交给 shell 又用 `shlex.quote()` 包成 `'~/.claude.env'` → 单引号阻止 `~` 展开 → 当成字面文件名 → **No such file or directory**。

**解法**：按降权用户的真实家目录拼成**绝对路径**，既不用 Python `expanduser()`，也不依赖 shell 的 `~` 展开：
```python
if self.env_file.startswith("~/"):
    home = pwd.getpwnam(self.drop_user).pw_dir   # console → /home/console
    env_path = os.path.join(home, self.env_file[2:])
env_part = f"source {shlex.quote(env_path)} && "   # → source /home/console/.claude.env
```
（codebuddy 的 `env_file=None`，根本不走这条，所以不受影响。）

## 已知风险（非 bug，需知悉）

1. **HTTP 明文**：密码在公网明文传输，可被嗅探。要更强上 Cloudflare HTTPS。
2. **无人值守**：手机输入 = 代码执行权，密码别泄露。
3. **会话记忆随重启丢**：`--continue` 靠 claude CLI 的会话存储（`~/.claude/`）。服务器重启后第一次发指令是新会话，丢上文——这是 claude CLI 机制，不是控制台 bug。但**持久化日志**（`logs/`）不丢，电脑上能查历史。
4. **SSE 队列有界**：`log_q` maxsize=2000，满了丢旧的（只丢实时推手机的，持久化日志不受影响）。
