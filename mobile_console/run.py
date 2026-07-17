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
import secrets
import base64
import threading
import subprocess
import queue
from pathlib import Path

from flask import Flask, Response, request, jsonify, render_template_string, session

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # FlaskAPP 根目录
APP_PY = PROJECT_ROOT / "app.py"
PYTHON = sys.executable                                         # 当前解释器
HOST = "0.0.0.0"
CONSOLE_PORT = 8765
GAME_PORT = 5000

# Claude 交互历史持久化目录(手机发的每条指令 + Claude 回复都追加到这里的按天日志)。
# 这样电脑上随时能 tail/cat 看历史,服务重启也不丢。
LOG_DIR = Path(__file__).resolve().parent / "logs"

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

# 服务器上 get_lan_ip() 拿到的是内网网卡 IP,手机从外网访问不到。
# 部署时用 PUBLIC_IP 环境变量覆盖(写进 systemd / 启动脚本)。
def get_public_ip():
    return os.environ.get("PUBLIC_IP") or get_lan_ip()

LAN_IP = get_public_ip()


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
            # shell=True 时若 cmd 是 list,Windows 上会被当成单条程序名 → 出错;
            # 此时改拼成字符串交给 cmd.exe 解析。
            popen_cmd = cmd
            if shell and isinstance(cmd, list):
                import shlex
                popen_cmd = " ".join(shlex.quote(c) if os.name != "nt" else _win_quote(c)
                                     for c in cmd)
            # 跨平台 Popen kwargs:Windows 用 CREATE_NEW_PROCESS_GROUP,
            # Linux 用 start_new_session(setsid)让子进程整组可被杀,避免 Flask
            # reloader fork 的孤儿子进程占着端口。creationflags 是 Windows 专属
            # kwarg,Linux 上传了会抛 TypeError,所以按平台分流组装 kwargs。
            popen_kwargs = dict(
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
            )
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            try:
                self.proc = subprocess.Popen(popen_cmd, **popen_kwargs)
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
                if os.name == "nt":
                    # Windows:CREATE_NEW_PROCESS_GROUP 下用 CTRL_BREAK_EVENT 杀整组
                    self.proc.send_signal(subprocess.CTRL_BREAK_EVENT)
                else:
                    # Linux:start_new_session 建了独立 session,杀整个进程组,
                    # 连 Flask reloader fork 出的子进程(真正监听端口的)一起带走,
                    # 否则只 terminate 父进程会留孤儿占端口,重启时报 Address already in use。
                    import signal
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
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


class AgentRunner:
    """通用 AI CLI 常驻交互运行器(Claude / CodeBuddy 等)。

    CLI 在非 TTY 下无法常驻交互(默认交互模式要 TTY;-p 模式又是一次性)。
    所以采用『任务队列 + 逐条调用』模型:
        手机每发一条指令 → 入队 → 后台 worker 逐条执行
            <binary> -p [--continue] --dangerously-skip-permissions "<prompt>"
    --continue 让每条指令接着上一条在同一会话里,保持上下文记忆。
    首条指令无 --continue(CLI 会自动忽略不存在的会话,但显式跳过更干净)。

    各 agent 通过构造参数区分(二进制名、日志前缀、Linux 降权用户、env 文件),
    行为保持一致。"""

    def __init__(self, key, name, color, binary, log_prefix,
                 drop_user=None, env_file=None):
        self.key = key              # 进程 key,也作日志 tag
        self.name = name            # 展示名
        self.color = color          # 展示用颜色名(前端 CSS class)
        self.binary = binary        # CLI 二进制名(claude / codebuddy / ...)
        self.log_prefix = log_prefix  # 按天日志文件前缀
        self.drop_user = drop_user  # Linux 下降权到的用户(None=不降权,以当前用户跑)
        self.env_file = env_file    # Linux 下降权后需 source 的 env 文件(None=不 source)
        self.skip_flag = "--dangerously-skip-permissions"  # 免确认 flag(各 CLI 一致)
        self.log_q = queue.Queue(maxsize=2000)
        self.task_q = queue.Queue()
        self._worker = None
        self._lock = threading.Lock()
        self._busy = False        # 正在处理某条指令
        self._started = False     # worker 是否已启用
        self._has_session = False # 是否已有会话可 continue
        self._current_proc = None # 当前正在跑的 claude 子进程(供打断用)
        self._interrupted = False # 当前这条是否被用户打断
        self._log_lock = threading.Lock()  # 持久化日志文件写入锁

    def _append_log(self, tag, line):
        """把一条交互追加到按天的纯文本日志文件(电脑端历史记录)。
        路径:mobile_console/logs/<log_prefix>-YYYY-MM-DD.log
        tag: you / claude / system / error,决定行首标签。失败不影响主流程。"""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            fname = LOG_DIR / f"{self.log_prefix}-{time.strftime('%Y-%m-%d')}.log"
            # 多行内容每行都带时间戳+标签,方便 grep / tail 时行行可定位
            ts = time.strftime("%H:%M:%S")
            label = {"you": "you", "claude": "claude", "system": "sys", "error": "ERR"}.get(tag, tag)
            body = str(line).rstrip("\n")
            stamp = f"{ts} [{label}] "
            out = "".join(
                (stamp if i == 0 else " " * len(stamp)) + ln + "\n"
                for i, ln in enumerate(body.split("\n"))
            )
            with self._log_lock:
                with open(fname, "a", encoding="utf-8") as f:
                    f.write(out)
        except Exception:
            # 持久化日志写失败不能影响手机端实时交互
            pass

    def _push(self, line, tag):
        try:
            self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
        except queue.Full:
            try:
                self.log_q.get_nowait()
                self.log_q.put_nowait((time.strftime("%H:%M:%S"), tag, line))
            except Exception:
                pass
        # 同步落盘:手机端历史 = 电脑端历史,服务重启不丢
        self._append_log(tag, line)

    def is_running(self):
        return self._started

    def start(self):
        with self._lock:
            if self._started:
                return False, f"{self.name} 已在运行"
            self._started = True
            self._worker = threading.Thread(target=self._work_loop, daemon=True)
            self._worker.start()
            self._push(f"▶ {self.name} 已就绪。在下方输入框发指令即可。", "system")
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
            self._push(f"■ {self.name} 已停止(未完成的指令已丢弃)。", "system")
            return True, "已停止"

    def submit(self, prompt):
        if not self._started:
            return False, f"{self.name} 未启动,请先点启动"
        self.task_q.put(prompt)
        return True, "已加入队列"

    def interrupt(self):
        """打断当前正在处理的指令(相当于在 claude 交互界面按 Esc)。
        做法:杀掉当前 claude 子进程的整个进程组 + 清空待办队列。
        claude CLI 的会话记忆存在 ~/.claude/ 下,杀进程不会丢失会话,
        下一条 --continue 仍能接上文。"""
        with self._lock:
            killed = False
            proc = self._current_proc
            if proc is not None and proc.poll() is None:
                self._push("■ 用户打断当前指令(杀 claude 进程组)", "system")
                try:
                    if os.name == "nt":
                        proc.send_signal(subprocess.CTRL_BREAK_EVENT)
                    else:
                        import signal
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    killed = True
                except Exception:
                    try:
                        proc.terminate()
                        killed = True
                    except Exception:
                        pass
            self._interrupted = True   # 通知 _run_one 这条是被打断的,别报"异常退出"
            # 清空待办队列(用户选择:打断当前并清空队列)
            dropped = 0
            while True:
                try:
                    self.task_q.get_nowait()
                    dropped += 1
                except queue.Empty:
                    break
            if dropped:
                self._push(f"■ 已清空队列中 {dropped} 条待办指令", "system")
            msg = "已打断当前指令" + (f"并清空 {dropped} 条排队指令" if dropped else "")
            if not killed and dropped == 0:
                return False, "当前没有正在处理的指令"
            return True, msg

    def _work_loop(self):
        while self._started:
            try:
                prompt = self.task_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._busy = True
            self._interrupted = False
            self._push(prompt, "you")
            try:
                self._run_one(prompt)
            except Exception as e:
                import traceback
                self._push(f"✗ worker 异常: {e}", "error")
                self._push(traceback.format_exc(), "error")
            finally:
                self._current_proc = None
            self._busy = False

    def _run_one(self, prompt):
        # prompt 传递:统一走 stdin(UTF-8 管道),写完立即 close → CLI 收到 EOF 处理。
        #  - Windows:直接调二进制(.cmd 可能需 shell)
        #  - Linux:若配置了 drop_user(如 claude 需降权到 console,root 下拒绝
        #    --dangerously-skip-permissions),则用 runuser -l <user> -c 降权,
        #    prompt 通过 stdin 喂进去(runuser 包了 shell,argv 塞中文+引号太脆);
        #    否则(如 codebuddy,以当前用户/root 直接跑,凭据在自己 home 下)直接调。
        cli_bin = which(self.binary)
        on_windows = os.name == "nt"

        # 组装 CLI 参数(不含 prompt,prompt 走 stdin)
        cli_args = [cli_bin, "-p"]
        if self._has_session:
            cli_args.append("--continue")
        cli_args.append(self.skip_flag)

        if on_windows:
            # Windows:直接调二进制(.cmd 可能需 shell)
            cmd = cli_args
            use_shell = cli_bin.lower().endswith((".cmd", ".bat"))
            popen_kwargs = dict(
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                shell=use_shell,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        elif self.drop_user:
            # Linux:降权到指定用户,source 环境变量后调 CLI。
            # 注意:runuser -l 是 login shell,会先 cd 到家目录(~),覆盖 Popen 的 cwd,
            # 导致 CLI 以为工作目录是家目录(看不到项目代码,trust 也不匹配)。
            # 所以必须在 shell 命令里显式 cd 到 PROJECT_ROOT。
            # 用 shlex 把参数拼成安全的 shell 命令字符串
            import shlex, pwd
            inner = " ".join(shlex.quote(a) for a in cli_args)
            env_part = ""
            if self.env_file:
                # 把 env 文件路径解析为降权用户的真实家目录下的绝对路径
                # (console 的 ~/.claude.env → /home/console/.claude.env)。
                # 不能:1) 用 Python expanduser()(会以 root 身份解析成 /root);
                #       2) 把字面 '~' 交给 shell 又用 shlex.quote 包起来(单引号会阻止 ~ 展开,
                #          变成 source '~/.claude.env' → No such file)。
                # 直接按降权用户的家目录拼成绝对路径,最稳妥。
                if self.env_file.startswith("~/"):
                    home = pwd.getpwnam(self.drop_user).pw_dir
                    env_path = os.path.join(home, self.env_file[2:])
                else:
                    env_path = os.path.expanduser(self.env_file)
                env_part = f"source {shlex.quote(env_path)} && "
            shell_cmd = f"cd {shlex.quote(str(PROJECT_ROOT))} && {env_part}{inner}"
            cmd = ["runuser", "-l", self.drop_user, "-c", shell_cmd]
            popen_kwargs = dict(
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                start_new_session=True,   # 让 interrupt() 能杀整个进程组
                shell=False,
            )
        else:
            # Linux:不降权,以当前用户(如 root)直接调 CLI。
            cmd = cli_args
            popen_kwargs = dict(
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                start_new_session=True,   # 让 interrupt() 能杀整个进程组
                shell=False,
            )

        self._push(f"▶ 调用: {self.binary} -p{' --continue' if self._has_session else ''} {self.skip_flag} \"<你的指令>\"", "system")
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            self._current_proc = proc   # 记录给 interrupt() 用
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
                self._push(line.rstrip("\n"), self.key)
            proc.wait()
            if self._interrupted:
                # 被 interrupt() 杀掉的,不算异常
                self._push("■ 本条已打断", "system")
            elif proc.returncode == 0:
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


claude_proc = AgentRunner(
    key="claude", name="Claude Code", color="claude",
    binary="claude", log_prefix="claude",
    # claude 在 root 下拒绝 --dangerously-skip-permissions,需降权到 console 用户,
    # 并通过 ~/.claude.env 注入 API key 等环境变量(见 start_claude 说明)。
    drop_user="console", env_file="~/.claude.env",
)
codebuddy_proc = AgentRunner(
    key="codebuddy", name="CodeBuddy", color="codebuddy",
    binary="codebuddy", log_prefix="codebuddy",
    # codebuddy 凭据在运行用户(本机为 root)自己的 ~/.codebuddy 下,且允许 root 下
    # 使用 --dangerously-skip-permissions,故不降权、不额外 source env。
    drop_user=None, env_file=None,
)
flask_proc = ManagedProcess("flask", "FlaskAPP (app.py)", "flask")

PROCS = {"claude": claude_proc, "codebuddy": codebuddy_proc, "flask": flask_proc}


def start_flask():
    """以 gunicorn 启动游戏（生产级 WSGI 服务器），绑 0.0.0.0:5000。

    用 gunicorn 替代 Flask 自带 dev server，解决移动端多连接/keep-alive 下
    "网页无法加载"的问题。4 worker × gthread，每 worker 4 线程，共 16 并发。
    stop() 用 killpg 杀整个进程组（master + workers），不会留孤儿 worker。
    """
    env = os.environ.copy()
    env["FLASK_ENV"] = "development"
    # 单 worker 多线程 + --preload：
    # 世界BOSS/地面物品/劫匪等状态存进程内存(WorldBossService._bosses 等类级 dict)，
    # 多 worker 下各进程内存独立、击杀状态会分裂(玩家杀BOSS后请求落到别的worker还能再打)。
    # 单 worker 保证内存唯一，gthread 线程池扛并发；--preload 让 init_bosses() 在启动期完成。
    # 2核机器上单worker×16线程 IO密集文本页 QPS~300+/s，远超 200-400人在线峰值(~100QPS)。
    # --timeout 60 兜底单请求卡死(会被杀重启)。
    cmd = [
        PYTHON, "-m", "gunicorn",
        "-w", "1",
        "-k", "gthread",
        "--threads", "16",
        "--preload",
        "-b", "0.0.0.0:5000",
        "--access-logfile", "-",
        "--error-logfile", "-",
        "--timeout", "60",
        "--graceful-timeout", "30",
        "--access-logformat", '%(h)s "%(r)s" %(s)s %(b)s',
        "app:create_app()",
    ]
    return flask_proc.start(cmd, env=env)


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


def start_codebuddy():
    """启用 CodeBuddy worker(任务队列模式)。

    与 Claude 同模型:每条指令以 `codebuddy -p --continue --dangerously-skip-permissions`
    调用,默认无确认(--dangerously-skip-permissions,即用户无需点 yes),直接执行。
    codebuddy 凭据在运行用户(本机为 root)的 ~/.codebuddy 下,允许 root 下免确认,
    故以当前用户直接跑(不降权)。多条指令共享同一会话保持记忆。"""
    return codebuddy_proc.start()


def start_agent(key):
    """按 key 分发到对应启动函数(供 api_start / api_restart 复用)。"""
    if key == "flask":
        return start_flask()
    if key == "claude":
        return start_claude()
    if key == "codebuddy":
        return start_codebuddy()
    return False, "未知进程"


# ---------------------------------------------------------------------------
# Flask 控制台 app
# ---------------------------------------------------------------------------
app = Flask(__name__)


# ---------------------------------------------------------------------------
# 登录鉴权:session cookie + 登录页(替代 Basic Auth)
# 密码来源优先级:环境变量 MOBILE_CONSOLE_PASSWORD > .passwd 文件 > 启动时随机生成
# 单窗口登录:同一账号只允许一个有效 session,新登录会踢掉旧 session,
# 旧窗口下次请求/SSE 心跳时检测到被踢 → 前端弹全屏遮罩跳回登录页。
# ---------------------------------------------------------------------------
def _load_or_gen_password():
    p = os.environ.get("MOBILE_CONSOLE_PASSWORD")
    if p:
        return p
    pwfile = Path(__file__).parent / ".passwd"
    if pwfile.exists():
        cached = pwfile.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    pw = secrets.token_urlsafe(12)   # 随机 ~16 字符密码
    try:
        pwfile.write_text(pw, encoding="utf-8")
        pwfile.chmod(0o600)
    except Exception:
        pass   # 写不进也不阻塞,密码照样回显到终端
    print("=" * 60)
    print(f"[Mobile Console] 已生成访问密码(保存在 {pwfile}):")
    print(f"    {pw}")
    print("=" * 60)
    return pw

CONSOLE_PASSWORD = _load_or_gen_password()
app.secret_key = CONSOLE_PASSWORD   # session 签名密钥复用密码
# 关键:cookie 名改成独立的,和游戏 app.py(端口 5000,默认 cookie 名 'session')
# 区分开。浏览器 cookie 按域共享不区分端口,若两边都叫 'session' 会互相覆盖,
# 导致访问游戏页(▶ 打开游戏页面)后控制台 session 失效被踢回登录页。
app.config.update(
    SESSION_COOKIE_NAME="mobile_console_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ---------------------------------------------------------------------------
# Claude API 配置切换:两套 env(讯飞 xf-yun / unisound),通过覆盖
# /home/console/.claude.env 切换。claude 每条指令都 source 该文件,所以切换后
# 下一条指令即生效(当前正在执行的指令已 source 旧值,需等其结束)。
# ---------------------------------------------------------------------------
CLAUDE_USER = "console"
CLAUDE_ENV_DIR = Path("/home/" + CLAUDE_USER)
# 可选配置: name -> (模板文件, 显示名, 模型, 网关)
CLAUDE_CONFIGS = {
    "xfyun": {
        "file": ".claude.env.xfyun",
        "label": "讯飞(xf-yun 华北1)",
        "model": "astron-code-latest",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "auto": {
        "file": ".claude.env.auto",
        "label": "讯飞 auto",
        "model": "auto",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "xopglm52": {
        "file": ".claude.env.xopglm52",
        "label": "讯飞 xopglm52",
        "model": "xopglm52",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "xopglm51": {
        "file": ".claude.env.xopglm51",
        "label": "讯飞 xopglm51",
        "model": "xopglm51",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "xopdeepseekv4pro": {
        "file": ".claude.env.xopdeepseekv4pro",
        "label": "讯飞 xopdeepseekv4pro",
        "model": "xopdeepseekv4pro",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "xopkimik26": {
        "file": ".claude.env.xopkimik26",
        "label": "讯飞 xopkimik26",
        "model": "xopkimik26",
        "base": "maas-coding-api.cn-huabei-1.xf-yun.com",
    },
    "unisound": {
        "file": ".claude.env.unisound",
        "label": "云知声(unisound)",
        "model": "glm-5.2",
        "base": "maas-api.unisound.com",
    },
}
CLAUDE_ENV_ACTIVE = ".claude.env.active"   # 记录当前激活的配置名
CLAUDE_ENV_LIVE = ".claude.env"            # claude 实际 source 的文件


def _claude_active_config():
    """返回当前激活的配置名(xfyun/unisound),读不到则回退 xfyun。"""
    try:
        f = (CLAUDE_ENV_DIR / CLAUDE_ENV_ACTIVE)
        name = f.read_text(encoding="utf-8").strip() if f.exists() else ""
        return name if name in CLAUDE_CONFIGS else "xfyun"
    except Exception:
        return "xfyun"


def _claude_switch_config(name):
    """切换配置:把模板复制为 .claude.env,并写 active 标记。以 console 身份执行。"""
    if name not in CLAUDE_CONFIGS:
        return False, "未知配置: " + name
    info = CLAUDE_CONFIGS[name]
    src = CLAUDE_ENV_DIR / info["file"]
    live = CLAUDE_ENV_DIR / CLAUDE_ENV_LIVE
    active = CLAUDE_ENV_DIR / CLAUDE_ENV_ACTIVE
    if not src.exists():
        return False, "模板文件不存在: " + info["file"]
    # 复制 + 写标记 都以 console 身份(这些文件权限 600, root 可读写但保持归属一致更稳)
    import shlex
    shell_cmd = (
        f"cp {shlex.quote(str(src))} {shlex.quote(str(live))} && "
        f"chmod 600 {shlex.quote(str(live))} && "
        f"printf %s {shlex.quote(name)} > {shlex.quote(str(active))} && "
        f"chmod 600 {shlex.quote(str(active))}"
    )
    try:
        r = subprocess.run(
            ["runuser", "-l", CLAUDE_USER, "-c", shell_cmd],
            capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False, "切换失败: " + (r.stderr or r.stdout).strip()
    except Exception as e:
        return False, "切换异常: " + str(e)
    return True, f"已切换到 {info['label']}({info['model']})。下条指令生效。"


# 单窗口登录状态:token -> 当前有效 session_id
# 登录时生成新 token 并把 _ACTIVE_TOKEN 指向它;旧 session 的 token 不再匹配即视为被踢
import threading as _t
_session_lock = _t.Lock()
_ACTIVE_TOKEN = None   # 当前有效的登录 token,只有持有它的 session 才算在线


def _new_login():
    """登录成功:生成新 token,设到 session,并令其成为唯一有效 token(踢掉旧窗口)。"""
    global _ACTIVE_TOKEN
    token = secrets.token_urlsafe(24)
    with _session_lock:
        _ACTIVE_TOKEN = token
    session.permanent = True
    session["token"] = token


def _is_current_session():
    """当前请求的 session 是否仍是有效登录(没被新窗口踢掉)。"""
    tok = session.get("token")
    if not tok:
        return False
    with _session_lock:
        return tok == _ACTIVE_TOKEN


@app.before_request
def _require_auth():
    # 登录页本身和登录接口放行,其余一律要登录
    if request.endpoint in ("login_page", "api_login") or request.path == "/favicon.ico":
        return None
    # /api/peek 是免登录只读状态探针(供电脑端看板/终端查看运行状态,防冲突)。
    # 只返回各进程开没开 + pid,不暴露密码/日志内容,不支持任何写操作。
    # /status 是配套的只读看板页(纯静态 HTML,只调 /api/peek),也放行。
    if request.path in ("/api/peek", "/status"):
        return None
    if not _is_current_session():
        # 浏览器页面请求 → 重定向到登录页;API/SSE → 返回 401 让前端跳转
        if "text/event-stream" in request.headers.get("Accept", "") or \
           request.path.startswith("/api/"):
            return jsonify({"ok": False, "kicked": not (session.get("token") is None and _ACTIVE_TOKEN is None),
                            "msg": "未登录或已下线"}), 401
        return redirect_to_login()
    return None


def redirect_to_login():
    from flask import redirect, url_for
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET"])
def login_page():
    # 已登录且有效就直接进主页
    if _is_current_session():
        from flask import redirect, url_for
        return redirect(url_for("index"))
    return render_template_string(LOGIN_HTML)


@app.route("/api/login", methods=["POST"])
def api_login():
    pwd = (request.get_data() or b"").decode("utf-8", "replace").strip()
    if not pwd:
        return jsonify({"ok": False, "msg": "请输入密码"}), 400
    if pwd == CONSOLE_PASSWORD:
        _new_login()
        return jsonify({"ok": True, "msg": "登录成功"})
    return jsonify({"ok": False, "msg": "密码错误"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True, "msg": "已退出"})


@app.route("/")
def index():
    return render_template_string(PAGE_HTML, lan_ip=LAN_IP,
                                  console_port=CONSOLE_PORT, game_port=GAME_PORT)


@app.route("/status")
def status_page():
    """免登录只读看板页(电脑端查运行状态,防手机操作冲突)。
    纯静态 HTML,前端轮询 /api/peek。从文件读避免占内存。"""
    try:
        html = (Path(__file__).parent / "status.html").read_text(encoding="utf-8")
        return html
    except Exception as e:
        return f"看板页读取失败: {e}", 500


@app.route("/api/status")
def api_status():
    return jsonify({
        "procs": [p.status() for p in PROCS.values()],
        "lan_ip": LAN_IP,
        "game_url": f"http://{LAN_IP}:{GAME_PORT}",
        "claude_config": _claude_active_config(),
    })


def _port_listening(port):
    """探测本机某端口是否在监听(用于 peek 端点补全端口状态)。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


@app.route("/api/peek")
def api_peek():
    """免登录只读状态探针(供电脑端看板/终端查看,防止手机操作时电脑端盲目冲突)。
    只返回各进程开没开 + pid + 端口占用,不含密码/日志内容,不支持任何写操作。"""
    procs = {p.status()["key"]: p.status() for p in PROCS.values()}

    def _agent_view(k):
        s = procs.get(k, {})
        return {"running": s.get("running", False),
                "busy": s.get("busy", False),
                "queued": s.get("queued", 0)}

    return jsonify({
        "console": {                       # 控制台本身:能响应这个请求就说明活
            "running": True,
            "port": CONSOLE_PORT,
            "listening": True,
        },
        "claude": _agent_view("claude"),
        "codebuddy": _agent_view("codebuddy"),
        "flask": {
            "running": procs["flask"]["running"],
            "pid": procs["flask"].get("pid"),
            "port": GAME_PORT,
            "listening": _port_listening(GAME_PORT),
        },
        "lan_ip": LAN_IP,
    })


@app.route("/api/start/<key>", methods=["POST"])
def api_start(key):
    ok, msg = start_agent(key)
    if not ok and msg == "未知进程":
        return jsonify({"ok": False, "msg": msg}), 400
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/startall", methods=["POST"])
def api_startall():
    """一键启动:Claude worker + CodeBuddy worker + Flask。已运行的跳过,不重启。"""
    results = {}
    # 先启 Flask(等它绑端口),再启两个 AI worker
    fok, fmsg = start_flask()
    results["flask"] = {"ok": fok, "msg": fmsg}
    cok, cmsg = start_claude()
    results["claude"] = {"ok": cok, "msg": cmsg}
    bok, bmsg = start_codebuddy()
    results["codebuddy"] = {"ok": bok, "msg": bmsg}
    all_ok = fok and cok and bok
    return jsonify({"ok": all_ok, "results": results,
                    "msg": "Flask:" + fmsg + " | Claude:" + cmsg + " | CodeBuddy:" + bmsg})


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
    ok, msg = start_agent(key)
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
    if key in ("claude", "codebuddy"):
        # 任务队列型 agent 自己会在日志里回显 "you",这里只入队
        ok, msg = p.submit(text)
    else:
        # 长驻进程(flask):回显后投递 stdin
        p._push(text, "you")
        ok, msg = p.send(text) if hasattr(p, "send") else (False, "不支持输入")
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/interrupt/<key>", methods=["POST"])
def api_interrupt(key):
    """打断某 agent 当前正在处理的指令(相当于在交互界面按 Esc)。"""
    p = PROCS.get(key)
    if not p or not hasattr(p, "interrupt"):
        return jsonify({"ok": False, "msg": "未知进程"}), 400
    ok, msg = p.interrupt()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/claude_config", methods=["GET"])
def api_claude_config_get():
    """返回当前激活的 Claude 配置 + 可选列表。"""
    active = _claude_active_config()
    options = [
        {"name": n, "label": c["label"], "model": c["model"], "active": n == active}
        for n, c in CLAUDE_CONFIGS.items()
    ]
    return jsonify({"ok": True, "active": active, "options": options})


@app.route("/api/claude_config/<name>", methods=["POST"])
def api_claude_config_set(name):
    """切换 Claude API 配置(覆盖 .claude.env)。下一条指令即生效。"""
    ok, msg = _claude_switch_config(name)
    return jsonify({"ok": ok, "msg": msg})



@app.route("/api/upload", methods=["POST"])
def api_upload():
    """上传 txt/md 文件,把文件名+内容拼成上下文块返回给前端,
    前端再连同用户输入的指令一起发到 /api/send/claude。
    不直接提交给 claude,而是返回文本,让用户能在发送前看到/编辑(更安全)。"""
    if "file" not in request.files:
        return jsonify({"ok": False, "msg": "未收到文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "msg": "文件名为空"}), 400
    name = f.filename.lower()
    if not name.endswith((".txt", ".md", ".markdown")):
        return jsonify({"ok": False, "msg": "仅支持 .txt / .md 文件"}), 400
    raw = f.read()
    # 限制 256KB,避免 prompt 爆掉(claude -p 的 argv/stdin 都有长度上限)
    MAX = 256 * 1024
    if len(raw) > MAX:
        return jsonify({"ok": False, "msg": f"文件过大({len(raw)} 字节),上限 {MAX} 字节,请精简后重传"}), 400
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8", "replace")
    # 拼成上下文块,前端把它放在用户指令前面一起发给 claude
    block = f"【上传文件:{f.filename}】\n```\n{content}\n```\n"
    return jsonify({"ok": True, "msg": f"已载入 {f.filename}({len(content)} 字符)",
                    "filename": f.filename, "block": block})


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
LOGIN_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>登录 - 手机控制台</title>
<style>
  :root{--bg:#0f1115;--panel:#181b22;--line:#2a2f3a;--txt:#e6e8ee;--dim:#8a93a6;--accent:#4a6cf7}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font:16px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
       display:flex;min-height:100vh;align-items:center;justify-content:center;padding:20px}
  .box{background:var(--panel);border:1px solid var(--line);border-radius:14px;
       padding:28px 22px;width:100%;max-width:340px}
  h1{margin:0 0 6px;font-size:20px;text-align:center}
  .sub{color:var(--dim);font-size:13px;text-align:center;margin-bottom:22px}
  input{width:100%;background:#07090d;border:1px solid var(--line);color:var(--txt);
        border-radius:9px;padding:13px;font-size:16px;font-family:inherit;margin-bottom:12px}
  input:focus{outline:none;border-color:var(--accent)}
  button{width:100%;padding:13px;border:0;border-radius:9px;background:var(--accent);
         color:#fff;font-size:16px;font-weight:600;cursor:pointer}
  button:active{transform:scale(.98)}
  .err{color:#ff8b8b;font-size:13px;text-align:center;min-height:18px;margin-top:8px}
</style>
</head>
<body>
  <form class="box" onsubmit="doLogin(event)">
    <h1>🎮 手机控制台</h1>
    <div class="sub">请输入访问密码</div>
    <input id="pw" type="password" autocomplete="current-password" autofocus placeholder="密码">
    <button type="submit">登录</button>
    <div class="err" id="err"></div>
  </form>
<script>
async function doLogin(e){
  e.preventDefault();
  const err=document.getElementById('err');
  err.textContent='';
  const pw=document.getElementById('pw').value;
  try{
    const r=await fetch('/api/login',{method:'POST',body:pw});
    const j=await r.json();
    if(j.ok){location.href='/';}
    else{err.textContent=j.msg||'登录失败';}
  }catch(ex){err.textContent='网络错误:'+ex;}
}
document.getElementById('pw').addEventListener('keydown',e=>{
  if(e.key==='Enter'){doLogin(e);}
});
</script>
</body>
</html>
"""


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
    --codebuddy:#6ad7ff; --you:#ffd479; --sys:#6fb3ff; --err:#ff8b8b; --ok:#7fd1b9;
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
  .tag-claude{color:var(--claude)} .tag-flask{color:var(--flask)} .tag-codebuddy{color:var(--codebuddy)}
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
  /* 最后一条对话高亮 */
  .ln.last{background:rgba(74,108,247,.12);border-left:3px solid var(--accent);
           padding:4px 6px;margin:2px 0;border-radius:4px}
  /* busy 大字横幅 */
  .busy-banner{position:sticky;top:0;z-index:20;background:linear-gradient(135deg,#4a6cf7,#7a3df2);
       color:#fff;text-align:center;padding:10px;font-size:18px;font-weight:700;
       letter-spacing:1px;box-shadow:0 2px 10px rgba(74,108,247,.4);
       animation:pulse 1.2s ease-in-out infinite}
  .busy-banner .dot{display:inline-block;animation:bounce 1s infinite}
  @keyframes pulse{0%,100%{opacity:.85}50%{opacity:1}}
  @keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
  .btn.interrupt{background:#c0392b;flex:0 0 auto;width:auto;padding:10px 14px}
  .btn.interrupt:active{transform:scale(.97)}
  /* 文件上传 */
  .upload-row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
  .upload-row label{flex:0 0 auto;padding:10px 14px;border:1px dashed var(--line);
       border-radius:8px;color:var(--dim);font-size:13px;cursor:pointer;background:var(--panel2)}
  .upload-row .chip{background:rgba(127,209,185,.15);color:var(--flask);border:1px solid var(--flask);
       border-radius:12px;padding:4px 10px;font-size:12px;display:flex;align-items:center;gap:6px}
  .upload-row .chip .x{cursor:pointer;color:var(--err);font-weight:700}
  /* 被踢全屏遮罩 */
  .mask{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:200;
       display:flex;align-items:center;justify-content:center;padding:24px}
  .mask .modal{background:var(--panel);border:1px solid var(--line);border-radius:14px;
       padding:28px 22px;max-width:340px;text-align:center;width:100%}
  .mask h2{margin:0 0 10px;font-size:18px;color:var(--err)}
  .mask p{margin:0 0 18px;color:var(--dim);font-size:14px}
  .mask button{width:100%;padding:12px;border:0;border-radius:9px;background:var(--accent);
       color:#fff;font-size:15px;font-weight:600;cursor:pointer}
</style>
</head>
<body>
<header>
  <h1>🎮 FlaskAPP 手机控制台</h1>
  <div class="ip">电脑IP: {{ lan_ip }} · 控制台:{{ console_port }} · 游戏:{{ game_port }}</div>
  <button id="startall" class="btn-startall" onclick="startAll()">⚡ 一键启动 Claude + CodeBuddy + Flask</button>
  <div class="tabs">
    <button id="tab-console" class="active" onclick="showTab('console')">控制台</button>
    <button id="tab-claude" onclick="showTab('claude')">Claude</button>
    <button id="tab-codebuddy" onclick="showTab('codebuddy')">CodeBuddy</button>
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
      <h3>CodeBuddy</h3>
      <div class="row">
        <span id="st-codebuddy" class="state off">● 已停止</span>
        <button class="btn start" onclick="act('start','codebuddy')">启动</button>
        <button class="btn stop" onclick="act('stop','codebuddy')">停止</button>
        <button class="btn restart" onclick="act('restart','codebuddy')">重启</button>
      </div>
      <div class="hint">CodeBuddy 工作目录 = 项目根目录 FlaskAPP</div>
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
        <button class="btn interrupt" id="btn-interrupt" onclick="interruptAgent('claude')">✋ 打断</button>
      </div>
      <div class="row" style="margin-top:6px;align-items:center;flex-wrap:wrap">
        <span class="hint" style="margin:0">API配置:</span>
        <span id="claude-cfg-label" class="hint" style="margin:0;color:var(--flase,#7fd1b9)">-</span>
        <select id="claude-cfg-select" onchange="switchClaudeConfig()" style="font-size:14px;padding:2px 4px"></select>
      </div>
      <div class="hint">切换 API 配置(讯飞/云知声)后,下一条指令即生效;当前正在执行的指令仍用旧配置。</div>
      <div class="hint">启用后,在下方输入框发指令。每条指令以无人值守模式执行(--dangerously-skip-permissions),Claude 会直接读改代码/跑命令,多条指令共享同一会话保持记忆。点"打断"可中止当前指令(等同按 Esc)。</div>
    </div>
    <div class="card">
      <h3>对话 / 指令</h3>
      <!-- busy 大字横幅:仅处理中显示 -->
      <div id="busy-banner" class="busy-banner hidden">
        <span class="dot">⚙️</span> 正在处理命令,请稍候…
      </div>
      <div class="term" id="log-claude"></div>
      <!-- 已载入的文件上下文(可多个) -->
      <div class="upload-row" id="upload-row-claude">
        <label>📎 附文件<input type="file" id="file-input" accept=".txt,.md,.markdown" multiple hidden onchange="onFilesPicked(this,'claude')"></label>
        <span class="hint" id="upload-hint-claude" style="margin:0">可附 .txt/.md 作为上下文</span>
      </div>
      <div class="inputbar">
        <textarea id="msg-claude" placeholder="例:把登录页标题改成‘三国理财’,然后重启 Flask"></textarea>
        <button onclick="send('claude')">发送</button>
      </div>
      <div class="hint">回车=换行,需点发送按钮提交(Ctrl+Enter 也可发送)。附带的文件内容会拼在指令前一起发给 Claude。</div>
    </div>
  </section>

  <!-- CodeBuddy 交互 -->
  <section id="sec-codebuddy" class="hidden">
    <div class="card">
      <h3>CodeBuddy <span id="st-codebuddy2" class="state off" style="font-size:12px">● 已停止</span></h3>
      <div class="row">
        <button class="btn start" onclick="act('start','codebuddy')">启用CodeBuddy</button>
        <button class="btn stop" onclick="act('stop','codebuddy')">停止</button>
        <button class="btn interrupt" id="btn-interrupt-cb" onclick="interruptAgent('codebuddy')">✋ 打断</button>
      </div>
      <div class="hint">启用后,在下方输入框发指令。每条指令以无人值守模式执行(--dangerously-skip-permissions,即无需手动点 yes 授权),CodeBuddy 会直接读改代码/跑命令,多条指令共享同一会话保持记忆。点"打断"可中止当前指令(等同按 Esc)。</div>
    </div>
    <div class="card">
      <h3>对话 / 指令</h3>
      <!-- busy 大字横幅:仅处理中显示 -->
      <div id="busy-banner-codebuddy" class="busy-banner hidden">
        <span class="dot">⚙️</span> 正在处理命令,请稍候…
      </div>
      <div class="term" id="log-codebuddy"></div>
      <!-- 已载入的文件上下文(可多个) -->
      <div class="upload-row" id="upload-row-codebuddy">
        <label>📎 附文件<input type="file" id="file-input-codebuddy" accept=".txt,.md,.markdown" multiple hidden onchange="onFilesPicked(this,'codebuddy')"></label>
        <span class="hint" id="upload-hint-codebuddy" style="margin:0">可附 .txt/.md 作为上下文</span>
      </div>
      <div class="inputbar">
        <textarea id="msg-codebuddy" placeholder="例:把登录页标题改成‘三国理财’,然后重启 Flask"></textarea>
        <button onclick="send('codebuddy')">发送</button>
      </div>
      <div class="hint">回车=换行,需点发送按钮提交(Ctrl+Enter 也可发送)。附带的文件内容会拼在指令前一起发给 CodeBuddy。</div>
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
let _kickedShown = false;          // 被踢遮罩只弹一次
let _fileBlocks = {claude:[], codebuddy:[]};  // 已载入的文件上下文块(按 agent 隔离,发送时拼在指令前)

function showTab(t){
  document.querySelectorAll('[id^="sec-"]').forEach(e=>e.classList.add('hidden'));
  document.getElementById('sec-'+t).classList.remove('hidden');
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

// 统一 POST:401 = 未登录/被踢 → 弹遮罩
async function postJSON(url, body){
  const opt = {method:'POST'};
  if(body!==undefined){ opt.body=body; }
  const r = await fetch(url, opt);
  if(r.status===401){ onKicked(); throw new Error('unauthorized'); }
  return r.json();
}

// 被踢下线:全屏遮罩
function onKicked(){
  if(_kickedShown) return;
  _kickedShown = true;
  const m=document.createElement('div'); m.className='mask'; m.id='kicked-mask';
  m.innerHTML='<div class="modal"><h2>⚠️ 已下线</h2>'+
    '<p>该账号已在其他窗口登录,当前窗口已被强制下线(只支持单窗口登录)。</p>'+
    '<button onclick="location.href=\'/login\'">返回登录</button></div>';
  document.body.appendChild(m);
  try{ if(window._es) window._es.close(); }catch(e){}
}

async function act(action,key){
  try{ const j = await postJSON('/api/'+action+'/'+key); flash(j.msg||''); }catch(e){}
  refreshStatus();
}
// Claude API 配置切换
async function loadClaudeConfig(){
  try{
    const r = await fetch('/api/claude_config');
    if(r.status===401){ onKicked(); return; }
    const j = await r.json();
    const sel = document.getElementById('claude-cfg-select');
    const lbl = document.getElementById('claude-cfg-label');
    if(!sel) return;
    sel.innerHTML = '';
    (j.options||[]).forEach(o=>{
      const opt = document.createElement('option');
      opt.value = o.name; opt.textContent = `${o.label} (${o.model})`;
      if(o.active) opt.selected = true;
      sel.appendChild(opt);
    });
    const cur = (j.options||[]).find(o=>o.active);
    if(lbl && cur) lbl.textContent = `${cur.label} · ${cur.model}`;
  }catch(e){}
}
async function switchClaudeConfig(){
  const sel = document.getElementById('claude-cfg-select');
  if(!sel) return;
  const name = sel.value;
  if(!confirm('确定切换 Claude API 配置到: '+name+'?\n(下一条指令生效,当前指令仍用旧配置)')){ loadClaudeConfig(); return; }
  try{
    const j = await postJSON('/api/claude_config/'+name);
    flash(j.msg||'');
  }catch(e){}
  loadClaudeConfig();
  refreshStatus();
}
async function startAll(){
  const btn=document.getElementById('startall');
  if(!btn) return;
  btn.classList.add('busy'); btn.textContent='⚡ 启动中…';
  try{
    const j = await postJSON('/api/startall');
    flash(j.msg||'');
    setTimeout(refreshStatus, 600);
    setTimeout(refreshStatus, 2000);
  }catch(e){}
  finally{
    setTimeout(()=>{btn.classList.remove('busy');btn.textContent='⚡ 一键启动 Claude + CodeBuddy + Flask';},1200);
  }
}
async function send(key){
  const ta = document.getElementById('msg-'+key);
  let text = ta.value;
  if(!text.trim()) return;
  // 拼入已载入的文件上下文(放在用户指令前,按 agent 隔离)
  if(_fileBlocks[key] && _fileBlocks[key].length){
    text = _fileBlocks[key].join('') + '\n' + text;
  }
  try{
    await postJSON('/api/send/'+key, text);
    // 发送成功后清空文件上下文(已随这条指令一起发出)
    if(_fileBlocks[key] && _fileBlocks[key].length){ _fileBlocks[key]=[]; renderUploadChips(key); }
  }catch(e){}
  ta.value='';
}
async function interruptAgent(key){
  try{
    const j = await postJSON('/api/interrupt/'+key);
    flash(j.msg||'已打断');
  }catch(e){}
  setTimeout(refreshStatus, 300);
}
// Ctrl/Cmd+Enter 发送
document.getElementById('msg-claude').addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){send('claude');}
});
document.getElementById('msg-codebuddy').addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){send('codebuddy');}
});

// 文件上传:逐个上传,服务端返回上下文块,前端累积(按 agent 隔离)
async function onFilesPicked(input, agent){
  const files = Array.from(input.files);
  input.value='';   // 允许再次选同名文件
  for(const f of files){
    const fd = new FormData();
    fd.append('file', f);
    try{
      const r = await fetch('/api/upload',{method:'POST',body:fd});
      if(r.status===401){ onKicked(); return; }
      const j = await r.json();
      if(j.ok){
        _fileBlocks[agent].push(j.block);
        flash(j.msg);
      } else {
        flash(j.msg||'上传失败');
      }
    }catch(e){ flash('上传错误:'+e); }
  }
  renderUploadChips(agent);
}
function renderUploadChips(agent){
  const row = document.getElementById('upload-row-'+agent);
  if(!row) return;
  // 清掉旧 chip,保留 label 和 hint
  row.querySelectorAll('.chip').forEach(c=>c.remove());
  const hint = document.getElementById('upload-hint-'+agent);
  const blocks = _fileBlocks[agent] || [];
  if(blocks.length===0){
    if(hint){ hint.textContent='可附 .txt/.md 作为上下文'; hint.style.display=''; }
    return;
  }
  if(hint) hint.style.display='none';
  // 每个 chip 代表一个已载入的文件块,点 × 移除
  blocks.forEach((b,i)=>{
    // 从块里提取文件名(块格式:【上传文件:xxx】)
    const m = b.match(/【上传文件:(.+?)】/);
    const name = m ? m[1] : ('文件'+(i+1));
    const chip = document.createElement('span');
    chip.className='chip';
    chip.innerHTML = '📎 '+esc(name)+' <span class="x" onclick="removeFile(\''+agent+'\','+i+')">×</span>';
    row.appendChild(chip);
  });
}
function removeFile(agent, i){
  _fileBlocks[agent].splice(i,1);
  renderUploadChips(agent);
}

// 追加日志:last 标记最后一条(下次追加时移除上一条的 last)
function appendLog(termId, ts, tag, line){
  const box = document.getElementById(termId);
  if(!box) return;
  // 移除上一条的高亮(claude / codebuddy 对话区做高亮区分)
  if(termId==='log-claude' || termId==='log-codebuddy'){
    const prev = box.querySelector('.ln.last');
    if(prev) prev.classList.remove('last');
  }
  const div = document.createElement('div');
  div.className='ln' + ((termId==='log-claude'||termId==='log-codebuddy')?' last':'');
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
  fetch('/api/status').then(r=>{
    if(r.status===401){ onKicked(); throw new Error('ok'); }
    return r.json();
  }).then(j=>{
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
    // busy 横幅:各 agent 运行且处理中时,显示对应横幅
    const claude = j.procs.find(p=>p.key==='claude');
    const banner = document.getElementById('busy-banner');
    if(banner){
      banner.classList.toggle('hidden', !(claude && claude.running && claude.busy));
    }
    const codebuddy = j.procs.find(p=>p.key==='codebuddy');
    const bannerCb = document.getElementById('busy-banner-codebuddy');
    if(bannerCb){
      bannerCb.classList.toggle('hidden', !(codebuddy && codebuddy.running && codebuddy.busy));
    }
    // Claude 当前 API 配置显示
    if(j.claude_config){
      const lbl = document.getElementById('claude-cfg-label');
      if(lbl){
        // 优先用下拉框里该项的 label·model 文案,找不到再回退到旧的写死映射
        const opt = document.querySelector('#claude-cfg-select option[value="' + j.claude_config + '"]');
        const map = {xfyun:'讯飞(xf-yun) · astron-code-latest', unisound:'云知声(unisound) · glm-5.2'};
        lbl.textContent = (opt ? opt.textContent : (map[j.claude_config] || j.claude_config));
      }
      const sel = document.getElementById('claude-cfg-select');
      if(sel && !sel.matches(':focus')) sel.value = j.claude_config;
    }
  }).catch(()=>{});
}

// SSE 日志流(cookie 鉴权,EventSource 自动带同源 cookie)
function connectSSE(){
  const es = new EventSource('/api/logs');
  window._es = es;
  es.addEventListener('hello', ()=>{});
  es.onmessage = function(ev){
    try{
      const d = JSON.parse(ev.data);
      appendLog('log-all', d.ts, d.tag, d.line);
      if(d.tag==='claude'||d.tag==='you'||d.tag==='system'||d.tag==='error')
        appendLog('log-claude', d.ts, d.tag, d.line);
      if(d.tag==='codebuddy'||d.tag==='you'||d.tag==='system'||d.tag==='error')
        appendLog('log-codebuddy', d.ts, d.tag, d.line);
      if(d.tag==='flask'||d.tag==='system'||d.tag==='error')
        appendLog('log-flask', d.ts, d.tag, d.line);
    }catch(e){}
  };
  es.onerror = ()=>{
    try{ es.close(); }catch(e){}
    if(_kickedShown) return;   // 已被踢就不重连
    setTimeout(connectSSE, 1500);
  };
}
refreshStatus();
setInterval(refreshStatus, 3000);
loadClaudeConfig();
connectSSE();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    # Windows GBK 控制台不支持 emoji,这里用纯 ASCII 提示
    print("=" * 60)
    print("[Mobile Console] started")
    print(f"   Local:   http://127.0.0.1:{CONSOLE_PORT}")
    print(f"   Phone:   http://{LAN_IP}:{CONSOLE_PORT}")
    print(f"   Game:    http://{LAN_IP}:{GAME_PORT}     (start Flask first in console)")
    print(f"   Auth:    admin / {CONSOLE_PASSWORD}")
    if not os.environ.get("PUBLIC_IP"):
        print("   (LAN IP. On a public server, set PUBLIC_IP env var for external access.)")
    print("=" * 60)
    # threaded=True 让 SSE 流不阻塞其它请求
    app.run(host=HOST, port=CONSOLE_PORT, debug=False, threaded=True)
