#!/usr/bin/env bash
# 数据库查看启动脚本
# 用法: bash scripts/db_view.sh
#   DB_VIEW_PORT=8899 bash scripts/db_view.sh   # 自定义端口
#   VENV_PY=venv/bin/python bash scripts/db_view.sh
#
# 流程: 1) 解析 game_data.db 生成 db_view.html
#       2) 把 HTML 复制到隔离目录, 用内置 HTTP 服务打开
#       3) 打印浏览器访问地址 (并尝试本地直接打开)
#
# 注意: HTTP 只暴露 db_view.html 这一个文件, 不会暴露项目源码或数据库文件。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${DB_VIEW_PORT:-8899}"
VENV_PY="${VENV_PY:-venv/bin/python}"
SERVE_DIR="/tmp/db_view_serve"

echo "[1/3] 解析数据库 -> db_view.html"
"$VENV_PY" scripts/db_viewer.py

echo "[2/3] 准备只读服务目录并启动 HTTP (端口 $PORT)"
# 若端口已被占用, 先按 PID 结束旧服务(避免 pkill 误杀自身命令行)
OLD_PID=$(ss -ltnp 2>/dev/null | grep ":${PORT} " | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)
if [ -n "$OLD_PID" ]; then kill "$OLD_PID" 2>/dev/null; sleep 1; fi
rm -rf "$SERVE_DIR"
mkdir -p "$SERVE_DIR"
cp instance/db_view.html "$SERVE_DIR"/db_view.html
# 完全脱离当前会话, 工具/终端退出后服务仍常驻
setsid "$VENV_PY" -m http.server "$PORT" --bind 0.0.0.0 --directory "$SERVE_DIR" \
  >/tmp/db_view_server.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 1

echo "[3/3] 打开查看"
LAN_IP=$("$VENV_PY" -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0])" 2>/dev/null || echo 127.0.0.1)
URL="http://${LAN_IP}:${PORT}/db_view.html"
echo "===================================================="
echo " 在浏览器打开: $URL"
echo " 本机亦可:      http://127.0.0.1:${PORT}/db_view.html"
echo "===================================================="
# 本机有 GUI 时尝试直接打开浏览器(远程服务器会静默失败, 用上面的 URL 即可)
( xdg-open "$URL" 2>/dev/null || open "$URL" 2>/dev/null ) || true
echo "停止服务: pkill -f 'http.server ${PORT}'"
