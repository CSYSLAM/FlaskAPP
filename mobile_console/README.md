# 手机控制台 (mobile_console)

在手机上驱动 Claude Code 改代码 + 实时看 Flask 运行效果的闭环工具。
**独立 Flask 服务（端口 8765），与游戏代码完全解耦**，零额外依赖（只用 Flask 本身）。

## 文档

完整文档在 [`docs/`](docs/)，按需读：

| 文档 | 讲什么 | 什么时候看 |
|------|--------|------------|
| [docs/design.md](docs/design.md) | 设计：是什么 / 为什么这么设计 | 想理解整体架构 |
| [docs/implementation.md](docs/implementation.md) | 实现：代码结构 / 类 / API / 改哪里 | 要改代码 |
| [docs/pitfalls.md](docs/pitfalls.md) | 踩坑：12 个坑 + 已知风险 | 部署/排错前必看 |
| [docs/usage.md](docs/usage.md) | 使用：日常怎么用 / 首次部署 / FAQ | 日常操作 |

## 最常用三件事

```bash
# 电脑端查运行状态(防手机操作冲突,只读不影响手机端)
#   浏览器: http://127.0.0.1:8765/status   或   watch -n3 mobile_console/status.sh

# 重启控制台(改了 run.py 后,或服务挂了)——用这个,别用 pkill/deploy.sh
bash mobile_console/restart.sh

# 电脑上看手机发过的指令历史(重启不丢)
cat mobile_console/logs/claude-$(date +%F).log

# 手机访问
# http://117.72.209.69:8765   密码: cat mobile_console/.passwd
```

## 文件

- `run.py` — 控制台全部代码（后端 + 内嵌前端单页）
- `status.html` — 电脑端只读状态看板页（配 `/status` 路由 + `/api/peek` 端点）
- `status.sh` — 电脑端终端查状态（`watch -n3` 循环）
- `restart.sh` — 正确的重启脚本（先停干净再起，不留孤儿）
- `deploy.sh` — 全量部署脚本（首次部署装依赖用，**不是**日常重启用的）
- `mobile-console.service` — systemd 单元（开机自启）
- `.passwd` — 访问密码（chmod 600，gitignore）
- `logs/` — Claude 交互历史持久化日志（按天，gitignore）
- `docs/` — 本文档目录
