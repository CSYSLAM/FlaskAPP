# 手机控制台 · 使用文档

> 讲「日常怎么用」。设计见 [设计文档](design.md)，代码结构见 [实现文档](implementation.md)，遇到坑见 [踩坑文档](pitfalls.md)。

## 快速开始（已部署过，日常用）

### 0. 电脑端查运行状态（防手机操作冲突）

设计者可能在远程用手机控制台操作 Claude / 改代码，电脑端的你随时查一眼状态，避免两边同时改代码冲突。**只读、免登录、不影响手机端任何功能**（不会踢掉手机登录）。

浏览器看板（推荐，自动刷新，有状态灯）：
```
http://127.0.0.1:8765/status          # 电脑本机打开
http://117.72.209.69:8765/status      # 外网/别处打开
```
Claude 处理中时顶部会醒目提示「设计者正在用手机操作，请勿在电脑上同时改代码」。

终端版（ssh/终端场景）：
```bash
bash /mnt/FlaskAPP/mobile_console/status.sh          # 打印一次
watch -n3 /mnt/FlaskAPP/mobile_console/status.sh     # 每 3 秒刷新
# 连别的地址: HOST=http://1.2.3.4:8765 bash status.sh
```

### 1. 重启控制台（改了 run.py 后，或服务挂了）

```bash
bash /mnt/FlaskAPP/mobile_console/restart.sh
```

> ⚠️ **别用** `pkill -f "mobile_console/run.py"`（会留孤儿 gunicorn 占 5000），**也别用** `deploy.sh`（它是全量部署，会重装依赖 + 假设路径 `/root/FlaskAPP`）。详见 [踩坑文档坑1](pitfalls.md#坑-1最高频重启-mobile_console-留下孤儿-gunicorn-占着-5000)。

### 2. 手机访问

```
http://117.72.209.69:8765
```
输密码登录。密码：
```bash
cat /mnt/FlaskAPP/mobile_console/.passwd
```
（或启动时终端会打印。可设 `MOBILE_CONSOLE_PASSWORD` 环境变量自定义。）

### 3. 手机上操作

1. 进主页，点 **「⚡ 一键启动 Claude + Flask」**（或分别点启动）。
2. 切到 **Claude** tab → 在输入框发指令（回车换行，点「发送」或 `Ctrl+Enter` 提交）。
3. Claude 输出实时回流。处理中时顶部有横幅，可点 **「✋ 打断」** 中止当前指令（等同按 Esc，不影响会话记忆）。
4. 切到 **Flask** tab → 点「▶ 打开游戏页面」直达 `http://117.72.209.69:5000`。
5. 报错实时看 **实时日志** 区，可贴给 Claude 让它修。

### 4. 电脑上看手机发过的指令历史

手机发的每条指令 + Claude 回复都落盘了（服务重启不丢）：

```bash
# 看今天的
cat /mnt/FlaskAPP/mobile_console/logs/claude-$(date +%F).log

# 实时跟踪
tail -f /mnt/FlaskAPP/mobile_console/logs/claude-$(date +%F).log

# 看有哪些天的日志
ls /mnt/FlaskAPP/mobile_console/logs/

# 搜关键词
grep '你搜的词' /mnt/FlaskAPP/mobile_console/logs/claude-*.log
```

日志格式：每行 `HH:MM:SS [you/claude/sys/ERR] 内容`。

## 手机端功能清单

| 功能 | 怎么用 |
|------|--------|
| 启动/停止/重启 Claude | 控制台 tab 或 Claude tab 的按钮 |
| 启动/停止/重启 Flask | 控制台 tab 或 Flask tab 的按钮 |
| 一键启动 | 主页顶部「⚡ 一键启动 Claude + Flask」 |
| 发指令给 Claude | Claude tab 输入框 → 发送 |
| 打断当前指令 | Claude tab「✋ 打断」 |
| 附文件作上下文 | Claude tab「📎 附文件」选 `.txt`/`.md`（≤256KB），发送时拼在指令前 |
| 直达游戏页面 | Flask tab 或控制台 tab「▶ 打开游戏页面」 |
| 实时日志 | 控制台 tab（全部）/ 各 tab（分类） |

## 首次部署到新服务器（不常用）

需要：Ubuntu 22.04 服务器 + 公网 IP + 一个 `console` 普通用户。

```bash
# 1. 把项目代码弄到服务器(任选其一)
git clone <仓库地址> /mnt/FlaskAPP      # 或 scp -r 上传
cd /mnt/FlaskAPP

# 2. 装系统依赖 + Node + claude CLI + venv(首次)
PROJECT_DIR=/mnt/FlaskAPP bash mobile_console/deploy.sh
# 注意:deploy.sh 默认 PROJECT_DIR=/root/FlaskAPP,本机路径不同要显式传 PROJECT_DIR

# 3. 给 console 用户配 ANTHROPIC 凭据(关键!)
#    写进 /home/console/.claude.env(chmod 600):
cat > /home/console/.claude.env <<'EOF'
export ANTHROPIC_AUTH_TOKEN=...
export ANTHROPIC_BASE_URL=https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic
export ANTHROPIC_MODEL=...
export ANTHROPIC_DEFAULT_SONNET_MODEL=...
# ... 其余 ANTHROPIC_DEFAULT_*
EOF
chown console:console /home/console/.claude.env
chmod 600 /home/console/.claude.env
# ⚠️ 不是 ANTHROPIC_API_KEY!这套环境用 AUTH_TOKEN+BASE_URL(中转)。详见踩坑文档坑3。

# 4. 启动
bash mobile_console/restart.sh
```

### 可选：systemd 开机自启

```bash
# 先编辑 mobile_console/mobile-console.service,把 WorkingDirectory/ExecStart
# 里的 /root/FlaskAPP 改成 /mnt/FlaskAPP
sudo cp mobile_console/mobile-console.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mobile-console
journalctl -u mobile-console -f   # 看日志
```

> 注意：service 文件里那个 `Environment=ANTHROPIC_API_KEY=` 实际用不上（凭据在 console 用户的 `.claude.env` 里），可留空或删掉。

## 常见问题

**Q: 手机点「启动 Flask」报 `Address already in use: 5000`？**
A: 有孤儿 gunicorn 占着 5000。跑 `pkill -f "gunicorn.*app:create_app"` 清掉，再点启动。根因和彻底解法见 [踩坑文档坑1](pitfalls.md#坑-1最高频重启-mobile_console-留下孤儿-gunicorn-占着-5000)。

**Q: 手机发中文指令，Claude 收到全是问号？**
A: 不应发生（prompt 走 stdin）。若发生，检查 `_run_one` 里 `proc.stdin.write(prompt); proc.stdin.close()` 是否还在。见 [踩坑文档坑7](pitfalls.md#坑-7中文-prompt-走-argv-会变-)。

**Q: Claude 报 `cannot be used with root/sudo privileges`？**
A: 没降权。确认 `_run_one` Linux 分支用的是 `runuser -l console -c '...'`。见 [踩坑文档坑2](pitfalls.md#坑-2root-下-claude-拒绝---dangerously-skip-permissions)。

**Q: 手机访问游戏页后，控制台被踢回登录页？**
A: cookie 名撞车。确认 `SESSION_COOKIE_NAME="mobile_console_session"`。见 [踩坑文档坑9](pitfalls.md#坑-9cookie-名和游戏-app-撞车导致被踢回登录页)。

**Q: 重启控制台后，之前手机发的对话历史没了？**
A: 实时推手机的内存队列重启会丢（claude CLI 机制），但**持久化日志不丢**——电脑上 `cat mobile_console/logs/claude-*.log` 能看到全部历史。

**Q: 想恢复 Claude 逐项授权（不要无人值守）？**
A: 去掉 `_run_one`（run.py:356）里 `claude_args.append("--dangerously-skip-permissions")`。但手机端没法点确认，会卡住，仅在你改用别的交互方式时才合适。
