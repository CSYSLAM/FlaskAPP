# 手机控制台 (mobile_console)

在手机上驱动 Claude 改代码 + 实时看 Flask 运行效果的闭环工具。
**独立 Flask 服务,与游戏代码完全解耦**,零额外依赖(只用 Flask 本身)。

## 启动

在电脑上(项目根目录):

```bash
python mobile_console/run.py
```

启动后控制台常驻在 `0.0.0.0:8765`。手机连同一 WiFi,浏览器打开:

```
http://192.168.8.109:8765      # 替换成你电脑的局域网 IP
```

(控制台启动时会在终端打印实际的局域网 IP。)

## 手机上能做什么

1. **启用 Claude**:点「启用Claude」→ worker 就绪 → 在输入框发指令
2. **和 Claude 实时交互**:每条指令实时回流输出,带「处理中/排队 N」状态
3. **启动 Flask**:点「启动Flask」→ 游戏 app.py 跑在 `0.0.0.0:5000`
4. **直达游戏页面**:点页面上的「打开游戏页面」链接,手机直接玩
5. **实时日志**:Flask 的输出实时推到手机,报错立刻能看到、贴给 Claude

## 工作原理(关键设计)

### Claude 用「任务队列」而非长驻进程

`claude` CLI 在非交互(非 TTY)下:
- 默认交互模式要 TTY → 手机网页这种非 TTY 用不了
- `-p`(print)模式是一次性 → 每条指令跑完就退出

所以控制台采用**任务队列 + 逐条调用**模型:
- 手机每发一条指令 → 入队 → 后台 worker 逐条执行
  `claude -p --continue --dangerously-skip-permissions`(prompt 从 stdin 投递)
- `--continue` 让多条指令**共享同一会话**,Claude 记得前文(已验证记忆链)
- 首条不带 `--continue`(无会话可续)

### 无人值守

`--dangerously-skip-permissions` 跳过所有权限确认,Claude 直接读改代码/跑命令。
适合手机端无交互连续操作。⚠️ 风险:任何从手机输入的指令都会无确认执行——
仅在你信任手机输入、且控制台只在局域网(无密码)时使用。
想恢复逐项授权:去掉 `_run_one` 里的 `--dangerously-skip-permissions`。

### 中文必须走 stdin(踩过的坑)

Windows 上 `claude.cmd` 是批处理,`cmd.exe` 按 ANSI 代码页(GBK)重新解析命令行参数,
UTF-8 中文会被替换成 `?`,Claude 端收到全是问号。
**修复**:prompt 不放 argv,而是通过 stdin(UTF-8 管道)投递,`claude -p` 把 stdin 当输入。

### stdin 必须关闭(踩过的坑)

`claude -p` 启动后会等 stdin ~3 秒(以为有管道输入),若 stdin 不关闭会挂起。
**修复**:`Popen(stdin=PIPE)` → 写入 prompt 后立即 `proc.stdin.close()`。

## 常驻运行

控制台是普通 Flask 进程。要让它不受终端关闭影响,用独立进程启动:

```powershell
# Windows:后台独立进程,不随当前终端退出
Start-Process -FilePath python -ArgumentList "mobile_console\run.py" -WindowStyle Hidden
```

停止:在手机页面点「停止」只停 Claude/Flask worker;停控制台本身需杀进程
(`Stop-Process` 对应 pid,或重启电脑)。

## 文件

- `run.py` — 控制台全部代码(后端 + 内嵌前端单页),~700 行
- 不 import 任何游戏模块,可单独删除/移动
