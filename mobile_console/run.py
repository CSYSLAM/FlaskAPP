"""
手机控制台 —— 独立的 Flask 服务,用于在手机上:
  1. 启动/重启/关闭本机 Claude Code 会话,并实时与之交互
  2. 启动/重启/关闭游戏项目(FlaskAPP)的 app.py
  3. 直达游戏页面预览(局域网 IP)
  4. 实时查看 Flask 运行日志

与本项目的游戏代码完全解耦:它只负责"管 Claude + 管 Flask",
不 import 任何游戏模块。零额外依赖(只用 Flask 本身)。

启动:  python mobile_console/run.py
访问:  http://<本机局域网IP>:8765   (手机与电脑同 WiFi)
"""

import os
import sys
import json
import time
import shutil
import threading
import subprocess
import queue
from pathlib import Path

from flask import Flask, Response, request, jsonify, render_template_string

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # FlaskAPP 根目录
APP_PY = PROJECT_ROOT / "app.py"
PYTHON = sys.executable                                         # 当前解释器
HOST = "0.0.0.0"
CONSOLE_PORT = 8765
GAME_PORT = 5000

# 获取局域网 IP(供预览链接用)
def get_lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

LAN_IP = get_lan_ip()


def which(prog):
    """Windows 上 npm 全局命令是 .cmd 批处理,Popen 不带 shell 时找不到。
    解析成实际可执行的全路径(.exe / .cmd / .bat),失败则原样返回。"""
    return shutil.which(prog) or prog


def _win_quote(s):
    """Windows cmd.exe 引用规则:含空格/&|<>^" 等需用双引号包起,其余原样。
    路径里的 .cmd 已被 which 解析成全路径(常含空格,如 ...\\Roaming\\npm\\claude.cmd)。"""
    if s and not any(c in s for c in ' \t&|<>"^()'):
        return s
    return '"' + s.replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# 进程管理器
# ---------------------------------------------------------------------------
class ManagedProcess:
    """一个受管的长驻子进程:实时把 stdout/stderr 行喂进一个共享队列,
    供 SSE 推送给手机。支持启动/停止/重启和向 stdin 投递一行输入。"""

    def __init__(self, key, name, color):
        self.key = key
        self.name = name
        self.color = color
        self.proc = None
        self._reader = None
        self.log_q = queue.Queue(maxsize=2000)
        self._lock = threading.Lock()

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, cmd, cwd=None, env=None, shell=False):
        with self._lock:
            if self.is_running():
                return False, "已在运行中"
            # Windows 下用 shell 调 .cmd/.bat 时,cmd 必须是字符串
            display = cmd if isinstance(cmd, str) else ' '.join(cmd)
            self._push(f"▶ 启动 {self.name}: {display}", "system")
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            # shell=True 时若 cmd 是 list,Windows 上会被当成单条程序名 → 出错;
            # 此时改拼成字符串交给 cmd.exe 解析。
            popen_cmd = cmd
            if shell and isinstance(cmd, list):
                import shlex
                popen_cmd = " ".join(shlex.quote(c) if os.name != "nt" else _win_quote(c)
                                     for c in cmd)
            try:
                self.proc = subprocess.Popen(
                    popen_cmd,
                    cwd=cwd or str(PROJECT_ROOT),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    shell=shell,
                    creationflags=creationflags,
                )
            except Exception as e:
                self._push(f"✗ 启动失败: {e}", "error")
                return False, str(e)
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            return True, "已启动"

    def _read_loop(self):
        try:
            MAX_LINE = 8192
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_LINE:
                    line = line[:MAX_LINE] + f" …[截断,本行原长{len(line)}字符]\n"
                self._push(line.rstrip("\n"), self.key)
        except Exception as e:
            self._push(f"读取异常: {e}", "error")
        finally:
            code = self.proc.poll()
            self._push(f"■ {self.name} 已退出 (code={code})", "system")

    def _push(self, line, tag):
        try:
            self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
        except queue.Full:
            try:
                self.log_q.get_nowait()
                self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
            except Exception:
                pass

    def send(self, text):
        with self._lock:
            if not self.is_running():
                return False, "进程未运行"
            try:
                self.proc.stdin.write(text + "\n")
                self.proc.stdin.flush()
                return True, "已发送"
            except Exception as e:
                return False, str(e)

    def stop(self):
        with self._lock:
            if not self.is_running():
                return False, "未在运行"
            self._push(f"■ 停止 {self.name}", "system")
            try:
                self.proc.terminate()
            except Exception:
                pass
            return True, "已发送停止信号"

    def status(self):
        return {
            "key": self.key,
            "name": self.name,
            "running": self.is_running(),
            "pid": self.proc.pid if self.proc else None,
        }


class ClaudeRunner:
    """Claude CLI 在非 TTY 下无法常驻交互(默认交互模式要 TTY;
    -p 模式又是一次性)。所以采用『任务队列 + 逐条调用』模型:
    手机每发一条指令 → 入队 → 后台 worker 逐条执行
        claude -p --continue --dangerously-skip-permissions "<prompt>"
    --continue 让每条指令接着上一条在同一会话里,保持上下文记忆。
    首条指令无 --continue(claude 会自动忽略不存在的会话,但显式跳过更干净)。"""

    def __init__(self):
        self.key = "claude"
        self.name = "Claude Code"
        self.log_q = queue.Queue(maxsize=2000)
        self.task_q = queue.Queue()
        self._worker = None
        self._lock = threading.Lock()
        self._busy = False        # 正在处理某条指令
        self._started = False     # worker 是否已启用
        self._has_session = False # 是否已有会话可 continue

    def _push(self, line, tag):
        try:
            self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
        except queue.Full:
            try:
                self.log_q.get_nowait()
                self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
            except Exception:
                pass

    def is_running(self):
        return self._started

    def start(self):
        with self._lock:
            if self._started:
                return False, "Claude worker 已在运行"
            self._started = True
            self._worker = threading.Thread(target=self._work_loop, daemon=True)
            self._worker.start()
            self._push("▶ Claude worker 已就绪。在下方输入框发指令即可。", "system")
            return True, "已启动"

    def stop(self):
        with self._lock:
            if not self._started:
                return False, "未在运行"
            self._started = False
            # 清空待办队列
            while True:
                try:
                    self.task_q.get_nowait()
                except queue.Empty:
                    break
            self._push("■ Claude worker 已停止(未完成的指令已丢弃)。", "system")
            return True, "已停止"

    def submit(self, prompt):
        if not self._started:
            return False, "Claude 未启动,请先点启动"
        self.task_q.put(prompt)
        return True, "已加入队列"

    def _work_loop(self):
        while self._started:
            try:
                prompt = self.task_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._busy = True
            self._push(prompt, "you")
            try:
                self._run_one(prompt)
            except Exception as e:
                import traceback
                self._push(f"✗ worker 异常: {e}", "error")
                self._push(traceback.format_exc(), "error")
            self._busy = False

    def _run_one(self, prompt):
        # ⚠️ 中文必须走 stdin,不能放命令行参数:
        # Windows 上 claude.cmd 是批处理,cmd.exe 按 ANSI 代码页重新解析 argv,
        # UTF-8 中文会被替换成 '?',Claude 端收到全是问号。
        # 用 stdin 传 prompt(UTF-8 管道),claude -p 会把 stdin 当作输入。
        claude_bin = which("claude")
        cmd = [claude_bin, "-p", "--dangerously-skip-permissions"]
        if self._has_session:
            cmd.append("--continue")
        self._push(f"▶ 调用: claude -p{' --continue' if self._has_session else ''} --dangerously-skip-permissions \"<你的指令>\"", "system")
        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            # .cmd 批处理在 Windows 上需 shell=True 才能正确启动
            use_shell = os.name == "nt" and claude_bin.lower().endswith((".cmd", ".bat"))
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.PIPE,        # 通过 stdin 投递 prompt(UTF-8)
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=use_shell,
                creationflags=creationflags,
            )
            # 写入 prompt 并关闭 stdin,claude 收到 EOF 后开始处理
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except Exception as e:
                self._push(f"⚠ 写入 stdin 失败: {e}", "error")
            # 逐行读,但对超长无换行输出做截断,防止 OOM
            # (claude 偶尔会 dump 大块无换行内容,如 base64/压缩 JSON)
            MAX_LINE = 8192
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_LINE:
                    line = line[:MAX_LINE] + f" …[截断,本行原长{len(line)}字符]\n"
                self._push(line.rstrip("\n"), "claude")
            proc.wait()
            if proc.returncode == 0:
                self._has_session = True
                self._push(f"■ 本条完成 (exit=0)", "system")
            else:
                self._push(f"■ 本条异常退出 (exit={proc.returncode})", "error")
        except Exception as e:
            self._push(f"✗ 调用失败: {e}", "error")

    def status(self):
        return {
            "key": self.key,
            "name": self.name,
            "running": self._started,
            "busy": self._busy,
            "queued": self.task_q.qsize(),
            "pid": None,
        }


claude_proc = ClaudeRunner()
flask_proc = ManagedProcess("flask", "FlaskAPP (app.py)", "flask")

PROCS = {"claude": claude_proc, "flask": flask_proc}


def start_flask():
    """以独立进程启动游戏 app.py,绑 0.0.0.0:5000。"""
    env = os.environ.copy()
    # 关掉 reloader,避免双进程干扰日志/管理
    env["FLASK_ENV"] = "development"
    env["FLASK_DEBUG"] = "0"
    return flask_proc.start([PYTHON, str(APP_PY)], env=env)


def start_claude():
    """启用 Claude worker(任务队列模式)。

    无人值守说明:
    - 每条指令以 `claude -p --continue --dangerously-skip-permissions` 调用,
      不弹任何权限确认,直接读改代码/执行命令。
    - --continue 让多条指令共享同一会话,Claude 记得前文。
    - ⚠️ 任何从手机输入的指令都会被无确认执行。仅在你信任手机输入、
      且控制台只在局域网(无密码)时使用。
    - 想恢复逐项授权:去掉 _run_one 里的 --dangerously-skip-permissions。"""
    return claude_proc.start()


# ---------------------------------------------------------------------------
# Flask 控制台 app
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def index():
    return render_template_string(PAGE_HTML, lan_ip=LAN_IP,
                                  console_port=CONSOLE_PORT, game_port=GAME_PORT)


@app.route("/api/status")
def api_status():
    return jsonify({
        "procs": [p.status() for p in PROCS.values()],
        "lan_ip": LAN_IP,
        "game_url": f"http://{LAN_IP}:{GAME_PORT}",
    })


@app.route("/api/start/<key>", methods=["POST"])
def api_start(key):
    if key == "flask":
        ok, msg = start_flask()
    elif key == "claude":
        ok, msg = start_claude()
    else:
        return jsonify({"ok": False, "msg": "未知进程"}), 400
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/startall", methods=["POST"])
def api_startall():
    """一键启动:Claude worker + Flask。已运行的跳过,不重启。"""
    results = {}
    # 先启 Flask(等它绑端口),再启 Claude worker
    fok, fmsg = start_flask()
    results["flask"] = {"ok": fok, "msg": fmsg}
    cok, cmsg = start_claude()
    results["claude"] = {"ok": cok, "msg": cmsg}
    all_ok = fok and cok
    return jsonify({"ok": all_ok, "results": results,
                    "msg": "Flask:" + fmsg + " | Claude:" + cmsg})


@app.route("/api/stop/<key>", methods=["POST"])
def api_stop(key):
    p = PROCS.get(key)
    if not p:
        return jsonify({"ok": False, "msg": "未知进程"}), 400
    ok, msg = p.stop()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/restart/<key>", methods=["POST"])
def api_restart(key):
    p = PROCS.get(key)
    if not p:
        return jsonify({"ok": False, "msg": "未知进程"}), 400
    if p.is_running():
        p.stop()
        time.sleep(1.2)
    if key == "flask":
        ok, msg = start_flask()
    else:
        ok, msg = start_claude()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/send/<key>", methods=["POST"])
def api_send(key):
    p = PROCS.get(key)
    if not p:
        return jsonify({"ok": False, "msg": "未知进程"}), 400
    # 显式按 UTF-8 解码请求体(curl/手机发中文时未必带 charset 声明)
    raw = request.get_data() or b""
    try:
        text = raw.decode("utf-8").rstrip("\n")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace").rstrip("\n")
    if not text:
        return jsonify({"ok": False, "msg": "空输入"})
    if key == "claude":
        # ClaudeRunner 自己会在日志里回显 "you",这里只入队
        ok, msg = p.submit(text)
    else:
        # 长驻进程(flask):回显后投递 stdin
        p._push(text, "you")
        ok, msg = p.send(text) if hasattr(p, "send") else (False, "不支持输入")
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/logs")
def api_logs():
    """SSE: 把所有进程的日志实时推给手机。"""
    def stream():
        # 先发一条就绪信息
        yield "event: hello\ndata: connected\n\n"
        # 记录每个队列上次读到的位置——这里简单起见用轮询合并
        last_heartbeat = time.time()
        while True:
            got_any = False
            for p in PROCS.values():
                try:
                    ts, tag, line = p.log_q.get_nowait()
                    payload = json.dumps({"ts": ts, "tag": tag, "line": line}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    got_any = True
                except queue.Empty:
                    pass
            if not got_any:
                # 每 ~15s 发一次心跳,避免代理断连
                if time.time() - last_heartbeat > 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.time()
                time.sleep(0.2)
    return Response(stream(), mimetype="text/event-stream; charset=utf-8",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


@app.route("/api/logdump")
def api_logdump():
    """非流式:一次性把所有队列里现有的日志快照返回(诊断用,会清空队列)。"""
    out = []
    for p in PROCS.values():
        while True:
            try:
                ts, tag, line = p.log_q.get_nowait()
                out.append({"proc": p.key, "ts": ts, "tag": tag, "line": line})
            except queue.Empty:
                break
    return jsonify(out)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
PAGE_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>🎮 手机控制台</title>
<style>
  :root{
    --bg:#0f1115; --panel:#181b22; --panel2:#20242e; --line:#2a2f3a;
    --txt:#e6e8ee; --dim:#8a93a6; --claude:#d4a8ff; --flask:#7fd1b9;
    --you:#ffd479; --sys:#6fb3ff; --err:#ff8b8b; --ok:#7fd1b9;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font:15px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
       -webkit-text-size-adjust:100%;padding-bottom:env(safe-area-inset-bottom)}
  header{position:sticky;top:0;z-index:10;background:var(--panel);
         border-bottom:1px solid var(--line);padding:10px 12px}
  header h1{margin:0;font-size:16px}
  header .ip{font-size:12px;color:var(--dim);margin-top:2px;word-break:break-all}
  .tabs{display:flex;gap:6px;margin-top:8px}
  .tabs button{flex:1;padding:8px;border:1px solid var(--line);background:var(--panel2);
               color:var(--txt);border-radius:8px;font-size:14px;cursor:pointer}
  .tabs button.active{background:var(--panel2);border-color:#4a6cf7;color:#fff}
  main{padding:10px 12px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
        padding:12px;margin-bottom:10px}
  .card h3{margin:0 0 8px;font-size:14px;color:var(--dim);font-weight:600}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .btn{flex:1;min-width:70px;padding:10px;border:0;border-radius:8px;font-size:14px;
       font-weight:600;cursor:pointer;color:#fff}
  .btn.start{background:#2e7d5b}
  .btn.stop{background:#a3433a}
  .btn.restart{background:#3a5a9a}
  .btn.preview{background:#4a6cf7;text-decoration:none;text-align:center}
  .btn-startall{width:100%;margin-top:8px;padding:11px;border:0;border-radius:9px;
       background:linear-gradient(135deg,#4a6cf7,#7a3df2);color:#fff;font-size:15px;
       font-weight:700;cursor:pointer;box-shadow:0 2px 8px rgba(74,108,247,.3)}
  .btn-startall:active{transform:scale(.98)}
  .btn-startall.busy{opacity:.6;pointer-events:none}
  .state{font-size:13px;font-weight:600}
  .state.on{color:var(--ok)}
  .state.off{color:var(--dim)}
  .pid{font-size:11px;color:var(--dim);margin-left:6px}
  /* 终端 */
  .term{background:#07090d;border:1px solid var(--line);border-radius:10px;
        height:42vh;min-height:240px;overflow-y:auto;padding:8px 10px;
        font:12.5px/1.45 "SFMono-Regular",Consolas,Menlo,monospace;white-space:pre-wrap;word-break:break-word}
  .term .ln{display:block}
  .tag-claude{color:var(--claude)} .tag-flask{color:var(--flask)}
  .tag-you{color:var(--you)} .tag-system{color:var(--sys)}
  .tag-error{color:var(--err)}
  .ts{color:#5a6377;margin-right:6px}
  .inputbar{display:flex;gap:8px;margin-top:8px}
  .inputbar textarea{flex:1;background:var(--panel2);color:var(--txt);
       border:1px solid var(--line);border-radius:8px;padding:10px;font-size:14px;
       resize:none;height:60px;font-family:inherit}
  .inputbar button{width:64px;background:#4a6cf7;color:#fff;border:0;border-radius:8px;
       font-weight:600;cursor:pointer}
  .hint{font-size:12px;color:var(--dim);margin-top:6px}
  a.lnk{color:#6fb3ff}
  .hidden{display:none}
</style>
</head>
<body>
<header>
  <h1>🎮 FlaskAPP 手机控制台</h1>
  <div class="ip">电脑IP: {{ lan_ip }} · 控制台:{{ console_port }} · 游戏:{{ game_port }}</div>
  <button id="startall" class="btn-startall" onclick="startAll()">⚡ 一键启动 Claude + Flask</button>
  <div class="tabs">
    <button id="tab-console" class="active" onclick="showTab('console')">控制台</button>
    <button id="tab-claude" onclick="showTab('claude')">Claude</button>
    <button id="tab-flask" onclick="showTab('flask')">Flask</button>
  </div>
</header>

<main>
  <!-- 控制台总览 -->
  <section id="sec-console">
    <div class="card">
      <h3>Claude Code</h3>
      <div class="row">
        <span id="st-claude" class="state off">● 已停止</span>
        <button class="btn start" onclick="act('start','claude')">启动</button>
        <button class="btn stop" onclick="act('stop','claude')">停止</button>
        <button class="btn restart" onclick="act('restart','claude')">重启</button>
      </div>
      <div class="hint">Claude 工作目录 = 项目根目录 FlaskAPP</div>
    </div>
    <div class="card">
      <h3>FlaskAPP 游戏</h3>
      <div class="row">
        <span id="st-flask" class="state off">● 已停止</span>
        <button class="btn start" onclick="act('start','flask')">启动</button>
        <button class="btn stop" onclick="act('stop','flask')">停止</button>
        <button class="btn restart" onclick="act('restart','flask')">重启</button>
      </div>
      <div class="row" style="margin-top:8px">
        <a class="btn preview" href="http://{{ lan_ip }}:{{ game_port }}" target="_blank">▶ 在新页打开游戏</a>
      </div>
      <div class="hint">手机同 WiFi 下直接访问,需先启动 Flask</div>
    </div>
    <div class="card">
      <h3>实时日志(全部)</h3>
      <div class="term" id="log-all"></div>
    </div>
  </section>

  <!-- Claude 交互 -->
  <section id="sec-claude" class="hidden">
    <div class="card">
      <h3>Claude Code <span id="st-claude2" class="state off" style="font-size:12px">● 已停止</span></h3>
      <div class="row">
        <button class="btn start" onclick="act('start','claude')">启用Claude</button>
        <button class="btn stop" onclick="act('stop','claude')">停止</button>
      </div>
      <div class="hint">启用后,在下方输入框发指令。每条指令以无人值守模式执行(--dangerously-skip-permissions),Claude 会直接读改代码/跑命令,多条指令共享同一会话保持记忆。</div>
    </div>
    <div class="card">
      <h3>对话 / 指令</h3>
      <div class="term" id="log-claude"></div>
      <div class="inputbar">
        <textarea id="msg-claude" placeholder="例:把登录页标题改成‘三国理财’,然后重启 Flask"></textarea>
        <button onclick="send('claude')">发送</button>
      </div>
      <div class="hint">回车=换行,需点发送按钮提交(Ctrl+Enter 也可发送)</div>
    </div>
  </section>

  <!-- Flask 运行 -->
  <section id="sec-flask" class="hidden">
    <div class="card">
      <h3>FlaskAPP 运行日志</h3>
      <div class="row">
        <span id="st-flask2" class="state off">● 已停止</span>
        <button class="btn start" onclick="act('start','flask')">启动</button>
        <button class="btn restart" onclick="act('restart','flask')">重启</button>
      </div>
    </div>
    <div class="card">
      <div class="term" id="log-flask"></div>
    </div>
    <div class="card">
      <h3>页面预览</h3>
      <a class="btn preview" href="http://{{ lan_ip }}:{{ game_port }}" target="_blank">▶ 打开游戏页面</a>
      <div class="hint">如显示无法访问,先点上方"启动"。</div>
    </div>
  </section>
</main>

<script>
const TAG_LABEL = {claude:"claude", flask:"flask", you:"你", system:"系统", error:"错误"};
function showTab(t){
  document.querySelectorAll('[id^="sec-"]').forEach(e=>e.classList.add('hidden'));
  document.getElementById('sec-'+t).classList.remove('hidden');
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

async function act(action,key){
  const r = await fetch('/api/'+action+'/'+key,{method:'POST'});
  const j = await r.json();
  flash(j.msg||'');
  refreshStatus();
}
async function startAll(){
  const btn=document.getElementById('startall');
  if(!btn) return;
  btn.classList.add('busy'); btn.textContent='⚡ 启动中…';
  try{
    const r = await fetch('/api/startall',{method:'POST'});
    const j = await r.json();
    flash(j.msg||'');
    setTimeout(refreshStatus, 600);
    setTimeout(refreshStatus, 2000);
  }finally{
    setTimeout(()=>{btn.classList.remove('busy');btn.textContent='⚡ 一键启动 Claude + Flask';},1200);
  }
}
async function send(key){
  const ta = document.getElementById('msg-'+key);
  const text = ta.value;
  if(!text.trim()) return;
  await fetch('/api/send/'+key,{method:'POST',body:text});
  ta.value='';
}
// Ctrl/Cmd+Enter 发送
document.getElementById('msg-claude').addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){send('claude');}
});

function appendLog(termId, ts, tag, line){
  const box = document.getElementById(termId);
  if(!box) return;
  const div = document.createElement('div');
  div.className='ln';
  div.innerHTML = '<span class="ts">'+esc(ts)+'</span><span class="tag-'+esc(tag)+'">'+esc(line)+'</span>';
  box.appendChild(div);
  // 限长,防止爆内存
  while(box.children.length>800) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}
function flash(msg){ /* 简单提示 */
  let n=document.getElementById('flash'); if(!n){n=document.createElement('div');n.id='flash';
    n.style.cssText='position:fixed;left:0;right:0;bottom:0;background:#333;color:#fff;text-align:center;padding:8px;font-size:13px;z-index:99';document.body.appendChild(n);}
  n.textContent=msg; n.style.opacity='1';
  clearTimeout(window._ft); window._ft=setTimeout(()=>{n.style.opacity='0';},1800);
}

function refreshStatus(){
  fetch('/api/status').then(r=>r.json()).then(j=>{
    const set=(id,p)=>{
      const e=document.getElementById(id); if(!e)return;
      e.className='state '+(p.running?'on':'off');
      let extra='';
      if(p.key==='claude' && p.running){
        if(p.busy) extra='<span class="pid">处理中…</span>';
        else if(p.queued) extra='<span class="pid">排队 '+p.queued+'</span>';
      } else if(p.pid){
        extra='<span class="pid">pid '+p.pid+'</span>';
      }
      e.innerHTML = p.running?('● 运行中'+extra):'● 已停止';
    };
    j.procs.forEach(p=>{
      set('st-'+p.key, p);
      set('st-'+p.key+'2', p);
    });
  });
}

// SSE 日志流
function connectSSE(){
  const es = new EventSource('/api/logs');
  es.addEventListener('hello', ()=>{});
  es.onmessage = function(ev){
    try{
      const d = JSON.parse(ev.data);
      appendLog('log-all', d.ts, d.tag, d.line);
      if(d.tag==='claude'||d.tag==='you'||d.tag==='system'||d.tag==='error')
        appendLog('log-claude', d.ts, d.tag, d.line);
      if(d.tag==='flask'||d.tag==='system'||d.tag==='error')
        appendLog('log-flask', d.ts, d.tag, d.line);
    }catch(e){}
  };
  es.onerror = ()=>{ setTimeout(connectSSE, 1500); };
}
refreshStatus();
setInterval(refreshStatus, 3000);
connectSSE();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    # Windows GBK 控制台不支持 emoji,这里用纯 ASCII 提示
    print("=" * 60)
    print("[Mobile Console] started")
    print(f"   PC:      http://127.0.0.1:{CONSOLE_PORT}")
    print(f"   Phone:   http://{LAN_IP}:{CONSOLE_PORT}   (same WiFi)")
    print(f"   Game:    http://{LAN_IP}:{GAME_PORT}     (start Flask first in console)")
    print("=" * 60)
    # threaded=True 让 SSE 流不阻塞其它请求
    app.run(host=HOST, port=CONSOLE_PORT, debug=False, threaded=True)
