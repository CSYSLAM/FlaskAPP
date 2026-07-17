#!/usr/bin/env bash
# 电脑端终端查看手机控制台运行状态(只读,防手机操作时电脑盲目冲突)。
#
# 用法:
#   bash mobile_console/status.sh            # 打印一次
#   watch -n3 mobile_console/status.sh       # 每 3 秒刷新(推荐)
#
# 数据来自 mobile_console 的 /api/peek(免登录只读端点,不含密码/日志内容)。
# 默认连本机 127.0.0.1:8765;可改:HOST=http://1.2.3.4:8765 bash status.sh
set -uo pipefail

HOST="${HOST:-http://127.0.0.1:8765}"

# 用 python3 解析 JSON(服务器都有,且 run.py 本来就要 python3)
raw="$(curl -s -m 3 "$HOST/api/peek" 2>/dev/null)"
if [ -z "$raw" ]; then
  echo "✗ 无法连接 mobile_console ($HOST) —— 控制台可能没启动"
  echo "  启动: bash /mnt/FlaskAPP/mobile_console/restart.sh"
  exit 1
fi

python3 -c '
import json,sys
d=json.load(sys.stdin)
def on(b): return "● 运行中" if b else "○ 未运行"
c=d.get("console",{})
cl=d.get("claude",{})
f=d.get("flask",{})
cr=c.get("running")
print()
print("🎮 FlaskAPP 运行状态  (来源: /api/peek, 只读)")
print("="*48)
print("控制台(8765)  " + on(cr) + "  本机")
clr=cl.get("running")
if clr:
    if cl.get("busy"):
        state="⚙ 处理中…  ← 设计者正在用手机操作,请勿在电脑上同时改代码"
    else:
        state="● 就绪"
    q=cl.get("queued",0)
    print("Claude worker  " + state + (("  (队列 " + str(q) + ")") if q else ""))
else:
    print("Claude worker  ○ 未启用")
fr=f.get("running")
fl=f.get("listening")
if fr and fl:
    print("Flask  (5000)  ● 运行中  pid " + str(f.get("pid")))
elif fl:
    print("Flask  (5000)  ⚠ 端口占用(可能是孤儿 gunicorn)")
else:
    print("Flask  (5000)  ○ 未运行")
print("="*48)
print("IP: " + str(d.get("lan_ip","?")))
' <<< "$raw"
