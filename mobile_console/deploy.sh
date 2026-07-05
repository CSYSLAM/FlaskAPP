#!/usr/bin/env bash
# 手机控制台一键部署脚本(Linux / Ubuntu)
# 用法:  bash mobile_console/deploy.sh
# 可覆盖: PROJECT_DIR=... PUBLIC_IP=... ANTHROPIC_API_KEY=... bash mobile_console/deploy.sh
set -euo pipefail

# ===== 配置(可用环境变量覆盖) =====
PROJECT_DIR="${PROJECT_DIR:-/root/FlaskAPP}"
PUBLIC_IP="${PUBLIC_IP:-117.72.209.69}"
CONSOLE_PORT=8765
GAME_PORT=5000

echo "==> [1/6] 安装系统依赖(python3 / venv / pip / git / curl)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl

echo "==> [2/6] 安装 Node.js 20(claude CLI 依赖)"
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
echo "    node: $(node -v 2>/dev/null || echo '未装上,请手动装 Node.js')"

echo "==> [3/6] 安装 claude CLI"
if ! command -v claude >/dev/null 2>&1; then
    npm install -g @anthropic-ai/claude-code   # 包名若有变,以官方为准
fi
echo "    claude: $(which claude 2>/dev/null || echo '未装上,需手动 npm install -g @anthropic-ai/claude-code')"

echo "==> [4/6] 准备项目代码"
if [ -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    echo "    已存在 git 仓库,拉取最新: git pull"
    git pull || echo "    git pull 失败(可能离线/无远程),继续用现有代码"
else
    echo "    !!! $PROJECT_DIR 不是 git 仓库 !!!"
    echo "    请先把项目代码弄到服务器(git clone <仓库地址> $PROJECT_DIR,或本地 scp -r 上传)"
    echo "    然后重新跑本脚本。"
    exit 1
fi

echo "==> [5/6] 安装 Python 依赖(到 venv)"
python3 -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
echo "    依赖安装完成"

echo "==> [6/6] 启动控制台(nohup 后台)"
# 必须先有 ANTHROPIC_API_KEY,否则 claude -p 无人值守会失败
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "    !!! 警告: 未设置 ANTHROPIC_API_KEY 环境变量"
    echo "    claude 无人值守需要它(console.anthropic.com 申请,需充值)"
    echo "    可先 export ANTHROPIC_API_KEY=xxx 再跑本脚本,控制台仍能起,但 Claude 调用会失败"
fi

# 若已装 systemd 服务,优先用 systemctl(见 mobile-console.service)
if systemctl list-unit-files 2>/dev/null | grep -q '^mobile-console\.service'; then
    echo "    检测到 systemd 服务,用 systemctl 启动"
    systemctl restart mobile-console
else
    # 否则 nohup 后台跑
    pkill -f "mobile_console/run.py" 2>/dev/null || true
    cd "$PROJECT_DIR"
    nohup env ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
        PUBLIC_IP="$PUBLIC_IP" \
        venv/bin/python mobile_console/run.py \
        > /root/mobile_console.log 2>&1 &
    echo "    已用 nohup 启动,日志: /root/mobile_console.log"
fi

echo ""
echo "========================================"
echo " 控制台:  http://$PUBLIC_IP:$CONSOLE_PORT"
echo " 游戏:    http://$PUBLIC_IP:$GAME_PORT   (进控制台后点 启动 Flask)"
echo " 账号:    admin"
echo " 密码:    cat $PROJECT_DIR/mobile_console/.passwd"
echo " 日志:    tail -f /root/mobile_console.log"
echo "========================================"
echo ""
echo "提示: 推荐(可选)装 systemd 实现开机自启 + 崩溃重启:"
echo "  cp $PROJECT_DIR/mobile_console/mobile-console.service /etc/systemd/system/"
echo "  (编辑里面的 ANTHROPIC_API_KEY / PUBLIC_IP 后)"
echo "  systemctl daemon-reload && systemctl enable --now mobile-console"
