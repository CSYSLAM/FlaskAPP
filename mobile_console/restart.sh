#!/usr/bin/env bash
# mobile_console 重启脚本(正确停-启,不留孤儿进程)
#
# 用法:  bash mobile_console/restart.sh
#
# 为什么需要这个脚本:
#   直接 pkill "mobile_console/run.py" 会留下孤儿——run.py 起的 gunicorn
#   用 start_new_session=True 脱离了父进程,mobile_console 一被 kill,
#   gunicorn(占 5000)和 claude 子进程就变孤儿继续跑,导致新进程起不来
#   (Address already in use)。本脚本先杀干净整个进程组再起。
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

PUBLIC_IP="${PUBLIC_IP:-117.72.209.69}"
LOGFILE="/root/mobile_console.log"

echo "==> [1/3] 停止旧 mobile_console 及其子进程(gunicorn / claude worker)"
# 1. 杀 mobile_console 主进程
# 用 [m] 括号技巧:正则 [m]obile_console 能匹配 "mobile_console",但字面 "[m]obile_console"
# 不会出现在被匹配进程的 cmdline 中 —— 避免 pkill 误杀调用本脚本的 shell 自身
# (某些自动化终端会把整条命令写进自身 cmdline,导致 pkill 把自己也干掉)。
pkill -f "[m]obile_console/run.py" 2>/dev/null && echo "    已停 run.py" || echo "    run.py 未在运行"
sleep 1
# 2. 杀它遗留的孤儿 gunicorn(占 5000)和 claude 子进程
pkill -f "gu[n]icorn.*app:create_app" 2>/dev/null && echo "    已清孤儿 gunicorn" || true
pkill -f "runu[s]er.*claude" 2>/dev/null && echo "    已清 claude 子进程" || true
sleep 1.5

# 3. 确认 5000 / 8765 都释放了
echo "==> [2/3] 检查端口释放"
if ss -ltn 2>/dev/null | grep -qE ':5000\b'; then
    echo "    ⚠ 5000 仍被占用,强杀:"
    ss -ltnp 2>/dev/null | grep ':5000' | grep -oP 'pid=\K[0-9]+' | sort -u | while read pid; do
        kill -9 "$pid" 2>/dev/null && echo "      kill -9 $pid"
    done
    sleep 1
fi
ss -ltn 2>/dev/null | grep -qE ':5000\b' && echo "    ✗ 5000 仍未释放" || echo "    ✓ 5000 已释放"
ss -ltn 2>/dev/null | grep -qE ':8765\b' && echo "    ⚠ 8765 仍被占用(可能有残留)" || echo "    ✓ 8765 已释放"

echo "==> [3/3] 启动新 mobile_console"
# ANTHROPIC_* 由 console 用户的 ~/.claude.env 提供(runuser -l console 时 source),
# 所以这里只需传 PUBLIC_IP。
PUBLIC_IP="$PUBLIC_IP" setsid "$PROJECT_DIR/venv/bin/python" mobile_console/run.py \
    > "$LOGFILE" 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 2.5

# 验证
NEW_PID=$(pgrep -f "mobile_console/run.py" | head -1)
if [ -n "$NEW_PID" ]; then
    echo "    ✓ 已启动, PID=$NEW_PID"
    echo "    控制台: http://$PUBLIC_IP:8765"
    echo "    日志:   tail -f $LOGFILE"
else
    echo "    ✗ 启动失败,看日志: $LOGFILE"
    tail -10 "$LOGFILE" 2>&1
    exit 1
fi
