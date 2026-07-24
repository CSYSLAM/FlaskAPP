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
import signal
import base64
import select
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
# 日志持久化(模块级函数,供 ManagedProcess 和 AgentRunner 共用)
# ---------------------------------------------------------------------------
_log_lock = threading.Lock()  # 全局文件写入锁

def _append_log_file(log_prefix, tag, line):
    """通用日志持久化:追加到 logs/<log_prefix>-YYYY-MM-DD.log。
    tag: you / claude / codebuddy / flask / system / error,决定行首标签。失败不影响主流程。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fname = LOG_DIR / f"{log_prefix}-{time.strftime('%Y-%m-%d')}.log"
        ts = time.strftime("%H:%M:%S")
        label = {"you": "you", "claude": "claude", "codebuddy": "codebuddy",
                 "flask": "flask", "system": "sys", "error": "ERR"}.get(tag, tag)
        body = str(line).rstrip("\n")
        stamp = f"{ts} [{label}] "
        out = "".join(
            (stamp if i == 0 else " " * len(stamp)) + ln + "\n"
            for i, ln in enumerate(body.split("\n"))
        )
        with _log_lock:
            with open(fname, "a", encoding="utf-8") as f:
                f.write(out)
    except Exception:
        pass


def _parse_log_file(filepath, max_lines=200):
    """解析持久化日志文件,返回 [{ts, tag, line}, ...]。
    格式: HH:MM:SS [tag] content  (续行以空格开头,合并到上一条)"""
    import re
    result = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return result
    # 从末尾取 max_lines 行(最新的)
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    tag_map = {"you": "you", "claude": "claude", "codebuddy": "codebuddy",
               "flask": "flask", "sys": "system", "ERR": "error"}
    header_re = re.compile(r'^(\d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$')
    for raw in lines:
        raw = raw.rstrip("\n")
        m = header_re.match(raw)
        if m:
            ts, raw_tag, content = m.group(1), m.group(2), m.group(3)
            tag = tag_map.get(raw_tag, raw_tag)
            result.append({"ts": ts, "tag": tag, "line": content})
        elif result and raw.startswith(" "):
            # 续行:合并到上一条
            result[-1]["line"] += "\n" + raw.strip()
    return result


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
        # 持久化到日志文件
        _append_log_file(self.key, tag, line)

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
        _append_log_file(self.log_prefix, tag, line)

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
        cli_args = [cli_bin, "-p", "--output-format", "stream-json", "--verbose",
                    "--include-partial-messages"]
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

        self._push(f"▶ 调用: {self.binary} -p{' --continue' if self._has_session else ''} --output-format stream-json {self.skip_flag} \"<你的指令>\"", "system")
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            self._current_proc = proc   # 记录给 interrupt() 用
            # 写入 prompt 并关闭 stdin,claude 收到 EOF 后开始处理
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except Exception as e:
                self._push(f"⚠ 写入 stdin 失败: {e}", "error")
            # 逐行读 stream-json 输出,解析后实时推送
            MAX_LINE = 65536  # stream-json 单行可能很长(含工具调用详情)
            self._text_buf = ""  # 增量文本缓冲区,攒够后合并推送
            while True:
                # 进程可能已退出,但其启动的子进程(如 flask dev server)继承了 stdout
                # 管道 → 写端未关闭 → readline 永远读不到 EOF,会卡死在"正在处理命令"。
                # 因此用 select 兜底:进程退出后若无新数据即主动结束读取;否则按 1s 轮询。
                if proc.poll() is not None:
                    readable, _, _ = select.select([proc.stdout], [], [], 0.3)
                    if not readable:
                        break  # 进程已结束且无更多输出,直接结束读取
                else:
                    readable, _, _ = select.select([proc.stdout], [], [], 1.0)
                    if not readable:
                        continue
                line = proc.stdout.readline()
                if not line:
                    # readline 返回空:子进程可能仍持有管道,但进程已退出则不再有数据
                    if proc.poll() is not None:
                        break
                    continue
                line = line.rstrip("\n")
                if len(line) > MAX_LINE:
                    line = line[:MAX_LINE] + f" …[截断,本行原长{len(line)}字符]"
                if self._handle_stream_line(line):
                    # 收到 agent 终态 result,指令已结束,无需再等 EOF
                    break
            # 读取结束,flush剩余缓冲
            self._flush_text_buf()
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

    def _flush_text_buf(self):
        """将增量文本缓冲区的内容合并推送并清空。"""
        if self._text_buf:
            self._push(self._text_buf, self.key)
            self._text_buf = ""

    def _handle_stream_line(self, line):
        """解析 claude/codebuddy stream-json 输出的单行,提取关键信息推送。
        增量文本(delta)会攒到 _text_buf,遇到换行/非delta事件/缓冲超量时flush,
        避免每个碎片单独推送导致前端显示碎片化。
        返回 True 表示该条指令已结束(收到 agent 终态 result 消息),供读取循环判断是否提前结束。"""
        if not line:
            return False
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            # 非JSON行(旧版输出或错误信息),flush缓冲后原样推送
            self._flush_text_buf()
            self._push(line, self.key)
            return False

        msg_type = obj.get("type", "")

        if msg_type == "system":
            self._flush_text_buf()
            subtype = obj.get("subtype", "")
            if subtype == "init":
                model = obj.get("model", "?")
                self._push(f"⚙️ 模型: {model}", "system")
            elif subtype == "status":
                status = obj.get("status", "")
                if status == "requesting":
                    self._push("⏳ 请求中…", "system")
            # 其他system消息忽略

        elif msg_type == "stream_event":
            event = obj.get("event", {})
            event_type = event.get("type", "")
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    self._text_buf += text
                    # 遇到换行符或缓冲超过200字符时flush
                    if "\n" in text or len(self._text_buf) > 200:
                        self._flush_text_buf()
            elif event_type == "content_block_start":
                # 工具调用开始:flush文本,显示工具名
                self._flush_text_buf()
                cb = event.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tool_name = cb.get("name", "")
                    if tool_name:
                        self._push(f"🔧 调用工具: {tool_name}", "system")
            elif event_type == "content_block_stop":
                # 文本块结束,flush剩余文本
                self._flush_text_buf()
            # 其他stream_event忽略(message_delta/message_stop)

        elif msg_type == "assistant":
            # 完整assistant消息,已通过delta推送,忽略
            pass

        elif msg_type == "result":
            self._flush_text_buf()
            subtype = obj.get("subtype", "")
            duration = obj.get("duration_ms", 0)
            cost = obj.get("total_cost_usd", 0)
            if subtype == "success":
                info = f"✅ 完成"
                if duration:
                    info += f" · 耗时{duration/1000:.1f}s"
                if cost:
                    info += f" · ${cost:.4f}"
                self._push(info, "system")
                return True
            elif subtype == "error":
                error_msg = obj.get("error", {}) if isinstance(obj.get("error"), dict) else {}
                err_text = error_msg.get("message", str(obj.get("error", ""))) if error_msg else str(obj.get("error", ""))
                self._push(f"❌ 错误: {err_text}", "error")
                return True
            elif subtype == "cancelled":
                self._push("⚠️ 已取消", "system")
                return True
            # result里的result_text不再推送(已通过delta推送过)

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


def _kill_port_occupant(port=5000):
    """杀掉占用指定端口的进程 + 所有 gunicorn/flask 进程（无论谁启动的）。
    防止手动启动的 gunicorn 占着端口，导致手机控制台启动失败。"""
    if os.name == "nt":
        return  # Windows 暂不处理
    import subprocess as sp
    try:
        # 第1步：杀掉所有 gunicorn 和 flask 进程
        for proc_name in ("gunicorn", "flask"):
            try:
                result = sp.run(["pkill", "-9", "-f", proc_name],
                                capture_output=True, text=True, timeout=5)
            except Exception:
                pass
        # 第2步：杀掉占用 5000 端口的残留进程
        try:
            result = sp.run(["fuser", f"{port}/tcp"],
                            capture_output=True, text=True, timeout=5)
            pids = result.stdout.split()
            for pid_str in pids:
                try:
                    pid = int(pid_str.strip())
                    if pid != os.getpid():  # 不杀自己
                        os.kill(pid, signal.SIGKILL)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
        except Exception:
            pass
        import time
        time.sleep(1.5)  # 等端口释放
    except Exception:
        pass


def start_flask():
    """以 gunicorn 启动游戏（生产级 WSGI 服务器），绑 0.0.0.0:5000。

    用 gunicorn 替代 Flask 自带 dev server，解决移动端多连接/keep-alive 下
    "网页无法加载"的问题。单 worker × gthread 16 线程，保证世界BOSS等内存状态唯一。
    启动前先清理端口占用，防止手动启动的 gunicorn 导致 Address already in use。
    """
    _kill_port_occupant(5000)
    env = os.environ.copy()
    env["FLASK_ENV"] = "development"
    # 单 worker 多线程（不要 --preload）：
    # 世界BOSS/地面物品/劫匪等状态存进程内存(WorldBossService._bosses 等类级 dict)，
    # 多 worker 下各进程内存独立、击杀状态会分裂(玩家杀BOSS后请求落到别的worker还能再打)。
    # 单 worker(-w 1) 保证内存唯一，gthread 线程池扛并发；init_bosses() 在 create_app()
    # 内调用，worker 启动即初始化，与是否 --preload 无关。
    # 严禁 --preload：preload 会让 master 在加载期就打开 SQLite 连接，fork 后 worker
    # 继承同一文件描述符，两个进程共用一个 SQLite 连接 → 写操作(登录落库等)死锁卡死。
    # 2核机器上单worker×16线程 IO密集文本页 QPS~300+/s，远超 200-400人在线峰值(~100QPS)。
    # --timeout 60 兜底单请求卡死(会被杀重启)。
    cmd = [
        PYTHON, "-m", "gunicorn",
        "-w", "1",
        "-k", "gthread",
        "--threads", "16",
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
# 多窗口登录:同一账号允许多个有效 session 并存(不挤号),
# 仅在 /api/status 等接口暴露当前在线登录窗口数。
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
    "qwen": {
        "file": ".claude.env.qwen",
        "label": "阿里云(qwen)",
        "model": "qwen3.8-max-preview",
        "base": "token-plan.cn-beijing.maas.aliyuncs.com",
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


# 多窗口登录状态:保存所有有效 session token 的集合(不挤号)。
# 登录时生成新 token 加入集合;退出时移除。当前在线窗口数 = 集合大小。
import threading as _t
_session_lock = _t.Lock()
_ACTIVE_TOKENS = set()   # 当前所有有效登录 token,持有其中之一的 session 即算在线


def _new_login():
    """登录成功:生成新 token 加入有效集合(不影响其它已登录窗口)。"""
    token = secrets.token_urlsafe(24)
    with _session_lock:
        _ACTIVE_TOKENS.add(token)
    session.permanent = True
    session["token"] = token


def _is_current_session():
    """当前请求的 session 是否仍持有有效 token。"""
    tok = session.get("token")
    if not tok:
        return False
    with _session_lock:
        return tok in _ACTIVE_TOKENS


def _logout_current():
    """退出:从有效集合移除当前 token。"""
    tok = session.get("token")
    if tok:
        with _session_lock:
            _ACTIVE_TOKENS.discard(tok)
    session.clear()


def _active_login_count():
    """当前在线登录窗口数。"""
    with _session_lock:
        return len(_ACTIVE_TOKENS)


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
            return jsonify({"ok": False, "msg": "未登录或已下线"}), 401
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
    _logout_current()
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
        "login_count": _active_login_count(),
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
        "login_count": _active_login_count(),
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
    # 拦截特殊命令: /compact 或 /new → 重置会话,下一条指令不带 --continue
    # 效果:上下文过长时避免 400 input token limit,以新对话继续(项目记忆 ~/.claude 仍保留)
    if key in ("claude", "codebuddy"):
        cmd = text.strip().lower()
        if cmd in ("/compact", "/new"):
            was = "有会话" if p._has_session else "无会话"
            p._has_session = False
            p._push(f"▶ {cmd}: 已重置会话(之前{was},下一条指令开始新对话)", "system")
            return jsonify({"ok": True, "msg": "已重置会话"})
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


@app.route("/api/clear_history/<agent>", methods=["POST"])
def api_clear_history(agent):
    """清空指定 agent 的前端实时记录(DOM)和当天持久化日志文件。"""
    if agent not in ("claude", "codebuddy", "flask"):
        return jsonify({"ok": False, "msg": "未知agent"}), 400
    # 删除当天的持久化日志文件
    log_prefix = agent
    filepath = LOG_DIR / f"{log_prefix}-{time.strftime('%Y-%m-%d')}.log"
    try:
        if filepath.exists():
            filepath.unlink()
    except Exception as e:
        return jsonify({"ok": False, "msg": f"删除日志失败: {e}"}), 500
    # 清空内存队列中的现有消息
    p = PROCS.get(agent)
    if p:
        while True:
            try:
                p.log_q.get_nowait()
            except queue.Empty:
                break
    return jsonify({"ok": True, "msg": "已清空历史记录"})


@app.route("/api/new_session/<agent>", methods=["POST"])
def api_new_session(agent):
    """重置指定 agent 的会话(下一条指令不带 --continue,开始新对话)。
    上下文过长时避免 input token limit。项目记忆(~/.claude)仍保留。"""
    if agent not in ("claude", "codebuddy"):
        return jsonify({"ok": False, "msg": "仅支持 claude/codebuddy"}), 400
    p = PROCS.get(agent)
    if not p:
        return jsonify({"ok": False, "msg": "未知agent"}), 400
    was = "有会话" if p._has_session else "无会话"
    p._has_session = False
    p._push(f"▶ /new: 已重置会话(之前{was},下一条指令开始新对话)", "system")
    return jsonify({"ok": True, "msg": "已重置会话,下一条指令开始新对话"})


@app.route("/api/history/<agent>")
def api_history(agent):
    """返回指定 agent 当天的持久化日志(供页面加载/断连恢复时回放历史)。
    agent: claude / codebuddy / flask
    ?lines=N 限制返回条数(默认50,最大500)"""
    if agent not in ("claude", "codebuddy", "flask"):
        return jsonify({"ok": False, "msg": "未知agent"}), 400
    max_lines = min(int(request.args.get("lines", 50)), 500)
    # 确定日志文件路径
    log_prefix = agent  # claude/codebuddy/flask 与文件前缀一致
    filepath = LOG_DIR / f"{log_prefix}-{time.strftime('%Y-%m-%d')}.log"
    entries = _parse_log_file(filepath, max_lines)
    return jsonify(entries)


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
                    payload = json.dumps({"ts": ts, "tag": tag, "line": line, "proc": p.key}, ensure_ascii=False)
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
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>登录 · 手机控制台</title>
<style>
  :root{
    --bg0:#0b0d14; --bg1:#151a2a;
    --panel:rgba(24,28,40,.86); --line:rgba(255,255,255,.08);
    --txt:#eef1f8; --dim:#93a0b8; --accent:#5b7cfa; --accent2:#8b5cf6;
    --danger:#ff8b8b;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0;color:var(--txt);
    font:16px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    min-height:100vh;display:flex;align-items:center;justify-content:center;
    padding:24px 18px calc(24px + env(safe-area-inset-bottom));
    background:
      radial-gradient(900px 420px at 12% -10%, rgba(91,124,250,.35), transparent 55%),
      radial-gradient(700px 360px at 110% 10%, rgba(139,92,246,.28), transparent 50%),
      radial-gradient(600px 300px at 50% 120%, rgba(54,179,126,.12), transparent 55%),
      linear-gradient(160deg,var(--bg0),var(--bg1));
  }
  .box{
    width:100%;max-width:360px;padding:28px 22px 22px;
    background:var(--panel);border:1px solid var(--line);
    border-radius:18px;backdrop-filter:blur(16px);
    box-shadow:0 20px 50px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04);
  }
  .logo{
    width:54px;height:54px;border-radius:16px;margin:0 auto 14px;
    display:grid;place-items:center;font-size:26px;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    box-shadow:0 10px 24px rgba(91,124,250,.35);
  }
  h1{margin:0;font-size:20px;text-align:center;letter-spacing:.2px}
  .sub{color:var(--dim);font-size:13px;text-align:center;margin:6px 0 20px}
  label{display:block;font-size:12px;color:var(--dim);margin:0 0 6px 2px}
  input{
    width:100%;background:rgba(7,9,16,.72);border:1px solid var(--line);
    color:var(--txt);border-radius:12px;padding:13px 14px;font-size:16px;
    font-family:inherit;margin-bottom:14px;transition:border-color .15s,box-shadow .15s;
  }
  input:focus{outline:none;border-color:rgba(91,124,250,.7);box-shadow:0 0 0 3px rgba(91,124,250,.18)}
  button{
    width:100%;padding:13px;border:0;border-radius:12px;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    color:#fff;font-size:16px;font-weight:700;cursor:pointer;
    box-shadow:0 8px 20px rgba(91,124,250,.28);
  }
  button:active{transform:scale(.985)}
  button:disabled{opacity:.65}
  .err{color:var(--danger);font-size:13px;text-align:center;min-height:18px;margin-top:10px}
  .foot{margin-top:14px;text-align:center;color:var(--dim);font-size:11px}
</style>
</head>
<body>
  <form class="box" onsubmit="doLogin(event)">
    <div class="logo">🎮</div>
    <h1>手机控制台</h1>
    <div class="sub">Claude · CodeBuddy · Flask 远程运维</div>
    <label for="pw">访问密码</label>
    <input id="pw" type="password" autocomplete="current-password" autofocus placeholder="输入密码后登录">
    <button type="submit" id="btn">进入控制台</button>
    <div class="err" id="err"></div>
    <div class="foot">会话仅保存在本浏览器</div>
  </form>
<script>
async function doLogin(e){
  e.preventDefault();
  const err=document.getElementById('err');
  const btn=document.getElementById('btn');
  err.textContent='';
  const pw=document.getElementById('pw').value;
  btn.disabled=true; btn.textContent='登录中…';
  try{
    const r=await fetch('/api/login',{method:'POST',body:pw});
    const j=await r.json();
    if(j.ok){location.href='/';}
    else{err.textContent=j.msg||'登录失败'; btn.disabled=false; btn.textContent='进入控制台';}
  }catch(ex){err.textContent='网络错误:'+ex; btn.disabled=false; btn.textContent='进入控制台';}
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
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>手机控制台 · FlaskAPP</title>
<style>
  :root{
    --bg:#0a0c12; --panel:#171b25; --panel2:#1e2431; --line:#2a3142;
    --txt:#e9edf7; --dim:#8d97ad; --muted:#667085;
    --claude:#8b6cff; --codebuddy:#22b8ff; --flask:#2fce8a;
    --me:#4f74ff; --sys:#8d97ad; --err:#ef5b5b; --accent:#4f74ff; --accent2:#8b5cf6;
    --chat-bg:#0f121a; --bubble-bg:#222836; --bubble-txt:#e9edf7;
    --composer-bg:rgba(23,27,37,.92); --sys-pill-bg:rgba(255,255,255,.06); --sys-pill-txt:#9aa6bd;
    --err-pill-bg:rgba(239,91,91,.12); --err-pill-txt:#ff9b9b;
    --avatar-bg:#222836; --name-txt:#7d879b; --ts2-txt:#5b6478;
    --term-bg:#0c0e14; --term-txt:#d6dae2;
    --tag-claude:#c9b3ff; --tag-flask:#7fe3b0; --tag-codebuddy:#8fdcff;
    --tag-you:#ffd479; --tag-system:#9fc1ff; --tag-error:#ff9b9b; --ts:#5b6478;
    --upload-label-bg:#1e2431; --chip-bg:rgba(47,206,138,.12);
    --modal-bg:#171b25; --modal-txt:#e9edf7;
    --busy-bg:rgba(79,116,255,.14); --busy-txt:#9bb3ff;
    --tab-active-bg:#fff; --tab-active-txt:#4f74ff;
    --tab-bg:rgba(255,255,255,.1); --tab-txt:#fff;
    --card-shadow:0 8px 24px rgba(0,0,0,.22);
    --ok:#2fce8a; --warn:#f0b429; --danger:#ef5b5b;
    --header-grad:linear-gradient(135deg,#3f63f0 0%,#6d4df5 55%,#8b5cf6 100%);
    --glass:rgba(255,255,255,.08);
  }
  :root.light{
    --bg:#eef1f6; --panel:#ffffff; --panel2:#f4f6fa; --line:#e4e8f0;
    --txt:#1f2430; --dim:#7b8496; --muted:#9aa3b5;
    --chat-bg:#f3f5f9; --bubble-bg:#fff; --bubble-txt:#1f2430;
    --composer-bg:rgba(255,255,255,.94); --sys-pill-bg:rgba(0,0,0,.05); --sys-pill-txt:#7b8496;
    --err-pill-bg:#fde8e8; --err-pill-txt:#d8453b;
    --avatar-bg:#fff; --name-txt:#8a93a5; --ts2-txt:#b0b6c3;
    --term-bg:#1a1d26; --term-txt:#d6dae2;
    --tag-claude:#7c5cff; --tag-flask:#1fa86a; --tag-codebuddy:#0f9ad8;
    --tag-you:#a67c00; --tag-system:#6b7280; --tag-error:#d8453b; --ts:#8a93a5;
    --upload-label-bg:#f4f6fa; --chip-bg:rgba(47,206,138,.12);
    --modal-bg:#fff; --modal-txt:#1f2430;
    --busy-bg:rgba(79,116,255,.1); --busy-txt:#3f63f0;
    --tab-active-bg:#fff; --tab-active-txt:#3f63f0;
    --tab-bg:rgba(255,255,255,.14); --tab-txt:#fff;
    --card-shadow:0 6px 18px rgba(31,36,48,.06);
    --header-grad:linear-gradient(135deg,#4a6cf7 0%,#6d4df5 55%,#8b5cf6 100%);
    --glass:rgba(255,255,255,.18);
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0;background:var(--bg);color:var(--txt);
    font:15px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-text-size-adjust:100%;
    padding-bottom:calc(8px + env(safe-area-inset-bottom));
    transition:background .25s,color .25s;
  }
  header{
    position:sticky;top:0;z-index:20;color:#fff;
    background:var(--header-grad);
    padding:12px 14px 10px;
    box-shadow:0 8px 24px rgba(63,99,240,.25);
  }
  header .topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
  header .brand{min-width:0;flex:1}
  header h1{margin:0;font-size:17px;font-weight:750;letter-spacing:.2px}
  header .ip{font-size:12px;opacity:.9;margin-top:3px;word-break:break-all}
  header .meta-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .pill{
    display:inline-flex;align-items:center;gap:5px;
    background:var(--glass);border:1px solid rgba(255,255,255,.18);
    border-radius:999px;padding:3px 9px;font-size:11px;line-height:1.3;
  }
  .pill b{font-weight:700}
  .theme-toggle{
    flex:0 0 auto;background:rgba(255,255,255,.16);
    border:1px solid rgba(255,255,255,.28);color:#fff;border-radius:999px;
    padding:7px 11px;font-size:13px;cursor:pointer;backdrop-filter:blur(8px);
  }
  .theme-toggle:active{transform:scale(.96)}
  .btn-startall{
    width:100%;margin-top:10px;padding:12px 14px;border:0;border-radius:12px;
    background:rgba(255,255,255,.16);color:#fff;font-size:14.5px;font-weight:750;
    cursor:pointer;border:1px solid rgba(255,255,255,.22);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.12);
  }
  .btn-startall:active{transform:scale(.985)}
  .btn-startall.busy{opacity:.65;pointer-events:none}
  .tabs{display:flex;gap:6px;margin-top:10px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .tabs button{
    flex:1 0 auto;min-width:68px;padding:8px 10px;border:1px solid rgba(255,255,255,.22);
    background:var(--tab-bg);color:var(--tab-txt);border-radius:999px;
    font-size:13px;cursor:pointer;white-space:nowrap;
  }
  .tabs button.active{
    background:var(--tab-active-bg);color:var(--tab-active-txt);
    border-color:var(--tab-active-bg);font-weight:700;
    box-shadow:0 4px 12px rgba(0,0,0,.12);
  }
  main{padding:12px;max-width:820px;margin:0 auto}
  .card{
    background:var(--panel);border:1px solid var(--line);border-radius:16px;
    padding:14px;margin-bottom:12px;box-shadow:var(--card-shadow);
    transition:background .25s,border-color .25s;
  }
  .card h3{
    margin:0 0 10px;font-size:13px;color:var(--dim);font-weight:700;
    letter-spacing:.3px;display:flex;align-items:center;gap:8px;
  }
  .card h3 .dot-live{
    width:8px;height:8px;border-radius:50%;background:var(--muted);
    box-shadow:0 0 0 3px rgba(141,151,173,.12);
  }
  .card h3 .dot-live.on{background:var(--ok);box-shadow:0 0 0 3px rgba(47,206,138,.18)}
  .card h3 .dot-live.busy{background:var(--warn);box-shadow:0 0 0 3px rgba(240,180,41,.18);animation:pulse 1s infinite}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .btn{
    flex:1;min-width:72px;padding:10px 12px;border:0;border-radius:11px;
    font-size:13.5px;font-weight:700;cursor:pointer;color:#fff;
  }
  .btn.start{background:linear-gradient(135deg,#22b36b,#1f9d5d)}
  .btn.stop{background:linear-gradient(135deg,#ef5b5b,#d8453b)}
  .btn.restart{background:linear-gradient(135deg,#4f74ff,#3f63f0)}
  .btn.preview{
    background:linear-gradient(135deg,#4f74ff,#6d4df5);text-decoration:none;text-align:center;
    display:block;width:100%;padding:12px;border-radius:12px;font-weight:750;
  }
  .btn.interrupt{background:linear-gradient(135deg,#ef5b5b,#d8453b);flex:0 0 auto;width:auto;padding:10px 14px}
  .btn:active{transform:scale(.98)}
  .state{font-size:13px;font-weight:700}
  .state.on{color:var(--ok)}
  .state.off{color:var(--dim)}
  .pid{font-size:11px;color:var(--dim);margin-left:6px}
  .term{
    background:var(--term-bg);color:var(--term-txt);border:1px solid var(--line);border-radius:14px;
    height:46vh;min-height:260px;overflow-y:auto;padding:12px;
    font:12.5px/1.5 "SFMono-Regular",Consolas,Menlo,monospace;white-space:pre-wrap;word-break:break-word;
  }
  .term .ln{display:block}
  .tag-claude{color:var(--tag-claude)} .tag-flask{color:var(--tag-flask)} .tag-codebuddy{color:var(--tag-codebuddy)}
  .tag-you{color:var(--tag-you)} .tag-system{color:var(--tag-system)} .tag-error{color:var(--tag-error)}
  .ts{color:var(--ts);margin-right:6px}
  .chat{
    background:
      radial-gradient(420px 180px at 0% 0%, rgba(79,116,255,.08), transparent 60%),
      radial-gradient(360px 160px at 100% 100%, rgba(139,92,246,.07), transparent 55%),
      var(--chat-bg);
    border:1px solid var(--line);border-radius:14px;
    height:48vh;min-height:280px;overflow-y:auto;padding:12px 10px;
    transition:background .25s;
  }
  .bubble-row{display:flex;gap:8px;margin:12px 0;align-items:flex-start}
  .bubble-row.me{flex-direction:row-reverse}
  .avatar{
    width:36px;height:36px;border-radius:12px;flex:0 0 auto;
    display:flex;align-items:center;justify-content:center;font-size:16px;
    background:var(--avatar-bg);box-shadow:0 2px 8px rgba(0,0,0,.12);
  }
  .avatar.ai-claude{background:linear-gradient(135deg,#8b6cff,#6d4df5);color:#fff}
  .avatar.ai-codebuddy{background:linear-gradient(135deg,#22b8ff,#0f9ad8);color:#fff}
  .avatar.ai-flask{background:linear-gradient(135deg,#2fce8a,#1fa86a);color:#fff}
  .avatar.me{background:linear-gradient(135deg,#4f74ff,#3f63f0);color:#fff}
  .bubble-wrap{flex:1;max-width:78%;display:flex;flex-direction:column;min-width:0}
  .bubble-row.me .bubble-wrap{align-items:flex-end}
  .name{font-size:11px;color:var(--name-txt);margin:0 4px 3px}
  .bubble{
    background:var(--bubble-bg);color:var(--bubble-txt);border-radius:14px;border-top-left-radius:5px;
    padding:10px 12px;font-size:14.5px;line-height:1.55;white-space:pre-wrap;
    word-break:break-word;box-shadow:0 1px 2px rgba(0,0,0,.06);max-width:100%;
    border:1px solid rgba(0,0,0,.03);transition:background .25s,color .25s;
  }
  .bubble-row.me .bubble{
    background:linear-gradient(135deg,#4f74ff,#3f63f0);color:#fff;
    border-radius:14px;border-top-right-radius:5px;border:0;
  }
  .ts2{font-size:10px;color:var(--ts2-txt);margin:4px 4px 0}
  .bubble-row.me .ts2{text-align:right}
  .sys-row{display:flex;justify-content:center;margin:10px 0}
  .sys-pill{
    background:var(--sys-pill-bg);color:var(--sys-pill-txt);font-size:12px;padding:5px 11px;
    border-radius:999px;max-width:94%;text-align:center;white-space:pre-wrap;word-break:break-word;
    border:1px solid rgba(255,255,255,.04);transition:background .25s,color .25s;
  }
  .sys-pill .ts2{margin:0 6px 0 0}
  .sys-pill.error{background:var(--err-pill-bg);color:var(--err-pill-txt);border-color:rgba(239,91,91,.15)}
  .composer{
    position:sticky;bottom:0;z-index:5;background:var(--composer-bg);
    border-top:1px solid var(--line);border-radius:0 0 14px 14px;
    padding:10px 10px calc(10px + env(safe-area-inset-bottom));
    backdrop-filter:blur(12px);transition:background .25s;
  }
  .inputbar{display:flex;gap:8px;align-items:flex-end}
  .inputbar textarea{
    flex:1;background:var(--panel2);color:var(--txt);
    border:1px solid var(--line);border-radius:12px;padding:11px 12px;font-size:14px;
    resize:none;height:56px;font-family:inherit;transition:background .25s,border-color .15s;
  }
  .inputbar textarea:focus{outline:none;border-color:rgba(79,116,255,.55);box-shadow:0 0 0 3px rgba(79,116,255,.12)}
  .inputbar button{
    width:68px;background:linear-gradient(135deg,#4f74ff,#3f63f0);color:#fff;border:0;border-radius:12px;
    font-weight:750;cursor:pointer;height:56px;box-shadow:0 6px 14px rgba(79,116,255,.25);
  }
  .hint{font-size:12px;color:var(--dim);margin-top:8px;line-height:1.45}
  a.lnk{color:#4f74ff}
  .hidden{display:none!important}
  .busy-banner{
    display:flex;align-items:center;gap:8px;justify-content:center;
    background:var(--busy-bg);color:var(--busy-txt);font-size:13px;font-weight:700;
    padding:8px 12px;border-radius:12px;margin-bottom:10px;border:1px solid rgba(79,116,255,.12);
  }
  .busy-banner .dot{
    width:7px;height:7px;border-radius:50%;background:var(--busy-txt);
    display:inline-block;animation:bounce 1s infinite;
  }
  @keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-3px);opacity:1}}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
  .upload-row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
  .upload-row label{
    flex:0 0 auto;padding:9px 12px;border:1px dashed var(--line);
    border-radius:10px;color:var(--dim);font-size:13px;cursor:pointer;background:var(--upload-label-bg);
  }
  .upload-row .chip{
    background:var(--chip-bg);color:var(--flask);border:1px solid rgba(47,206,138,.35);
    border-radius:999px;padding:4px 10px;font-size:12px;display:flex;align-items:center;gap:6px;
  }
  .upload-row .chip .x{cursor:pointer;color:var(--err);font-weight:700}
  .mask{
    position:fixed;inset:0;background:rgba(8,10,16,.62);z-index:200;
    display:flex;align-items:center;justify-content:center;padding:24px;backdrop-filter:blur(6px);
  }
  .mask .modal{
    background:var(--modal-bg);border:1px solid var(--line);border-radius:18px;
    padding:28px 22px;max-width:360px;text-align:center;width:100%;
    box-shadow:0 20px 50px rgba(0,0,0,.28);
  }
  .mask h2{margin:0 0 10px;font-size:18px;color:var(--err)}
  .mask p{margin:0 0 18px;color:var(--dim);font-size:14px}
  .mask button{
    width:100%;padding:12px;border:0;border-radius:12px;
    background:linear-gradient(135deg,#4f74ff,#6d4df5);color:#fff;font-size:15px;font-weight:700;cursor:pointer;
  }
  select{
    background:var(--panel2);color:var(--txt);border:1px solid var(--line);
    border-radius:10px;padding:6px 8px;font-size:13px;max-width:100%;
  }
  #flash{
    position:fixed;left:50%;bottom:calc(18px + env(safe-area-inset-bottom));
    transform:translateX(-50%) translateY(12px);
    background:rgba(20,24,34,.92);color:#fff;text-align:center;
    padding:10px 16px;font-size:13px;z-index:99;border-radius:999px;
    border:1px solid rgba(255,255,255,.08);box-shadow:0 10px 30px rgba(0,0,0,.28);
    opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;max-width:90vw;
  }
  #flash.show{opacity:1;transform:translateX(-50%) translateY(0)}
  .svc-grid{display:grid;gap:10px}
  @media (min-width:720px){
    .svc-grid{grid-template-columns:1fr 1fr}
    .svc-grid .card.span2{grid-column:1 / -1}
  }
</style>
</head>
<body>
<header>
  <div class="topbar">
    <div class="brand">
      <h1>🎮 手机控制台</h1>
      <div class="ip">{{ lan_ip }} · 控制台 {{ console_port }} · 游戏 {{ game_port }}</div>
      <div class="meta-row">
        <span class="pill">在线 <b id="login-count">-</b> 窗口</span>
        <span class="pill">FlaskAPP 运维面板</span>
      </div>
    </div>
    <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()" aria-label="切换主题">🌙</button>
  </div>
  <button id="startall" class="btn-startall" onclick="startAll()">⚡ 一键启动 Claude + CodeBuddy + Flask</button>
  <div class="tabs">
    <button id="tab-console" class="active" onclick="showTab('console')">总览</button>
    <button id="tab-claude" onclick="showTab('claude')">Claude</button>
    <button id="tab-codebuddy" onclick="showTab('codebuddy')">CodeBuddy</button>
    <button id="tab-flask" onclick="showTab('flask')">Flask</button>
  </div>
</header>

<main>
  <!-- 控制台总览 -->
  <section id="sec-console">
    <div class="svc-grid">
    <div class="card">
      <h3><span class="dot-live" id="dot-claude"></span>Claude Code</h3>
      <div class="row">
        <span id="st-claude" class="state off">● 已停止</span>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="btn start" onclick="act('start','claude')">启动</button>
        <button class="btn stop" onclick="act('stop','claude')">停止</button>
        <button class="btn restart" onclick="act('restart','claude')">重启</button>
      </div>
      <div class="hint">工作目录 = FlaskAPP 项目根目录</div>
    </div>
    <div class="card">
      <h3><span class="dot-live" id="dot-codebuddy"></span>CodeBuddy</h3>
      <div class="row">
        <span id="st-codebuddy" class="state off">● 已停止</span>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="btn start" onclick="act('start','codebuddy')">启动</button>
        <button class="btn stop" onclick="act('stop','codebuddy')">停止</button>
        <button class="btn restart" onclick="act('restart','codebuddy')">重启</button>
      </div>
      <div class="hint">工作目录 = FlaskAPP 项目根目录</div>
    </div>
    <div class="card">
      <h3><span class="dot-live" id="dot-flask"></span>Flask 游戏</h3>
      <div class="row">
        <span id="st-flask" class="state off">● 已停止</span>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="btn start" onclick="act('start','flask')">启动</button>
        <button class="btn stop" onclick="act('stop','flask')">停止</button>
        <button class="btn restart" onclick="act('restart','flask')">重启</button>
      </div>
      <div class="row" style="margin-top:8px">
        <a class="btn preview" href="http://{{ lan_ip }}:{{ game_port }}" target="_blank">▶ 打开游戏页面</a>
      </div>
      <div class="hint">手机同网访问；需先启动 Flask</div>
    </div>
    <div class="card span2">
      <h3>实时日志 · 全部</h3>
      <div class="chat" id="log-all"></div>
    </div>
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
      <div class="row" style="margin-top:6px">
        <button class="btn restart" onclick="newSession('claude')">🔄 新对话</button>
        <button class="btn stop" onclick="clearHistory('claude')">🗑️ 清历史</button>
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
      <div class="chat" id="log-claude"></div>
      <div class="composer">
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
      <div class="row" style="margin-top:6px">
        <button class="btn restart" onclick="newSession('codebuddy')">🔄 新对话</button>
        <button class="btn stop" onclick="clearHistory('codebuddy')">🗑️ 清历史</button>
      </div>
      <div class="hint">启用后,在下方输入框发指令。每条指令以无人值守模式执行(--dangerously-skip-permissions,即无需手动点 yes 授权),CodeBuddy 会直接读改代码/跑命令,多条指令共享同一会话保持记忆。点"打断"可中止当前指令(等同按 Esc)。</div>
    </div>
    <div class="card">
      <h3>对话 / 指令</h3>
      <!-- busy 大字横幅:仅处理中显示 -->
      <div id="busy-banner-codebuddy" class="busy-banner hidden">
        <span class="dot">⚙️</span> 正在处理命令,请稍候…
      </div>
      <div class="chat" id="log-codebuddy"></div>
      <div class="composer">
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
let _unauthShown = false;          // 未登录遮罩只弹一次
let _fileBlocks = {claude:[], codebuddy:[]};  // 已载入的文件上下文块(按 agent 隔离,发送时拼在指令前)

// 主题切换:默认 dark,localStorage 记忆
function toggleTheme(){
  const root = document.documentElement;
  const isLight = root.classList.toggle('light');
  localStorage.setItem('console-theme', isLight ? 'light' : 'dark');
  document.getElementById('theme-toggle').textContent = isLight ? '☀️' : '🌙';
}
(function(){
  const saved = localStorage.getItem('console-theme');
  if(saved === 'light'){
    document.documentElement.classList.add('light');
    document.getElementById('theme-toggle').textContent = '☀️';
  }
})();

function showTab(t){
  document.querySelectorAll('[id^="sec-"]').forEach(e=>e.classList.add('hidden'));
  document.getElementById('sec-'+t).classList.remove('hidden');
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

// 统一 POST:401 = 未登录/已下线 → 弹遮罩
async function postJSON(url, body){
  const opt = {method:'POST'};
  if(body!==undefined){ opt.body=body; }
  const r = await fetch(url, opt);
  if(r.status===401){ onUnauthorized(); throw new Error('unauthorized'); }
  return r.json();
}

// 未登录/已下线:全屏遮罩(多窗口并存,不会再被踢,仅当本窗口登出/失效时提示)
function onUnauthorized(){
  if(_unauthShown) return;
  _unauthShown = true;
  const m=document.createElement('div'); m.className='mask'; m.id='unauth-mask';
  m.innerHTML='<div class="modal"><h2>🔒 未登录</h2>'+
    '<p>当前窗口登录已失效,请重新登录。</p>'+
    '<button onclick="location.href=\'/login\'">返回登录</button></div>';
  document.body.appendChild(m);
  try{ if(window._es) window._es.close(); }catch(e){}
}

async function act(action,key){
  try{ const j = await postJSON('/api/'+action+'/'+key); flash(j.msg||''); }catch(e){}
  refreshStatus();
}
// 新对话:重置会话(下一条指令不带--continue),上下文过长时用
async function newSession(key){
  if(!confirm('确定开启新对话？当前会话上下文将被重置(项目记忆仍保留)。')) return;
  try{
    const j = await postJSON('/api/new_session/'+key);
    flash(j.msg||'已重置');
  }catch(e){}
}
// 清历史:清空前端DOM + 持久化日志文件
async function clearHistory(key){
  if(!confirm('确定清空历史记录？将删除今天的日志文件,不可恢复。')) return;
  try{
    const j = await postJSON('/api/clear_history/'+key);
    if(j.ok){
      // 清空前端DOM
      const termId = key==='flask' ? 'log-flask' : 'log-'+key;
      const box = document.getElementById(termId);
      if(box) box.innerHTML = '';
      // 也清空log-all中对应agent的内容(简单做法:全部清空再重新加载其他agent)
      const allBox = document.getElementById('log-all');
      if(allBox) allBox.innerHTML = '';
      // 重新加载其他agent的历史
      ['claude','codebuddy','flask'].forEach(a=>{
        if(a !== key) loadHistory(a);
      });
    }
    flash(j.msg||'已清空');
  }catch(e){}
}
// Claude API 配置切换
async function loadClaudeConfig(){
  try{
    const r = await fetch('/api/claude_config');
    if(r.status===401){ onUnauthorized(); return; }
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
      if(r.status===401){ onUnauthorized(); return; }
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

// 聊天气泡渲染:AI 左(带头像)、我 右、系统/错误 居中提示
const AGENT_META = {
  claude:    {name:'Claude',     avatar:'🅒', side:'ai', cls:'ai-claude'},
  codebuddy: {name:'CodeBuddy',  avatar:'🅑', side:'ai', cls:'ai-codebuddy'},
  flask:     {name:'Flask',      avatar:'📜', side:'ai', cls:'ai-flask'},
  you:       {name:'我',         avatar:'🙂', side:'me', cls:'me'},
  system:    {name:'系统',       avatar:'',  side:'sys', err:false},
  error:     {name:'错误',       avatar:'',  side:'sys', err:true},
};
function renderMsg(termId, ts, tag, line, withMeta){
  const box = document.getElementById(termId);
  if(!box) return;
  const m = AGENT_META[tag] || AGENT_META.system;
  let row;
  if(m.side==='sys'){
    row = document.createElement('div'); row.className='sys-row';
    const pill = document.createElement('div');
    pill.className = 'sys-pill' + (m.err?' error':'');
    const t = document.createElement('span'); t.className='ts2'; t.textContent=ts;
    pill.appendChild(t);
    pill.appendChild(document.createTextNode(' ' + line));
    row.appendChild(pill);
  } else {
    row = document.createElement('div');
    row.className = 'bubble-row ' + (m.side==='me'?'me':'ai');
    const av = document.createElement('div'); av.className='avatar '+m.cls; av.textContent=m.avatar;
    const wrap = document.createElement('div'); wrap.className='bubble-wrap';
    const name = document.createElement('div'); name.className='name'; name.textContent=m.name;
    const bub = document.createElement('div'); bub.className='bubble'; bub.textContent=line;
    const t = document.createElement('div'); t.className='ts2'; t.textContent=ts;
    wrap.appendChild(name); wrap.appendChild(bub); wrap.appendChild(t);
    row.appendChild(av); row.appendChild(wrap);
  }
  if(withMeta){
    row.setAttribute('data-ts', ts);
    row.setAttribute('data-line', (line||'').substring(0,80));
  }
  box.appendChild(row);
  // 限长,防止爆内存
  while(box.children.length>800) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}
function appendLog(termId, ts, tag, line){ renderMsg(termId, ts, tag, line, false); }
function flash(msg){
  let n=document.getElementById('flash');
  if(!n){n=document.createElement('div');n.id='flash';document.body.appendChild(n);}
  n.textContent=msg; n.classList.add('show');
  clearTimeout(window._ft); window._ft=setTimeout(()=>{n.classList.remove('show');},1800);
}

function refreshStatus(){
  fetch('/api/status').then(r=>{
    if(r.status===401){ onUnauthorized(); throw new Error('ok'); }
    return r.json();
  }).then(j=>{
    const set=(id,p)=>{
      const e=document.getElementById(id); if(!e)return;
      e.className='state '+(p.running?'on':'off');
      let extra='';
      if((p.key==='claude' || p.key==='codebuddy') && p.running){
        if(p.busy) extra='<span class="pid">处理中…</span>';
        else if(p.queued) extra='<span class="pid">排队 '+p.queued+'</span>';
      } else if(p.pid){
        extra='<span class="pid">pid '+p.pid+'</span>';
      }
      e.innerHTML = p.running?('● 运行中'+extra):'● 已停止';
      const d=document.getElementById('dot-'+p.key);
      if(d){
        d.className='dot-live'+(p.running?(p.busy?' busy':' on'):'');
      }
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
        const map = {xfyun:'讯飞(xf-yun) · astron-code-latest', unisound:'云知声(unisound) · glm-5.2', qwen:'阿里云(qwen) · qwen3.8-max-preview'};
        lbl.textContent = (opt ? opt.textContent : (map[j.claude_config] || j.claude_config));
      }
      const sel = document.getElementById('claude-cfg-select');
      if(sel && !sel.matches(':focus')) sel.value = j.claude_config;
    }
    // 当前在线登录窗口数
    const lc = document.getElementById('login-count');
    if(lc && typeof j.login_count === 'number'){ lc.textContent = j.login_count; }
  }).catch(()=>{});
}

// SSE 日志流(cookie 鉴权,EventSource 自动带同源 cookie)
let _lastLogTs = {};  // 记录每个tag最后一条日志的时间戳,用于断连恢复
let _historyLoaded = false;  // 首次历史是否已加载

async function loadHistory(agent, afterTs){
  try{
    let url = '/api/history/' + agent + '?lines=50';
    const r = await fetch(url);
    if(r.status===401){ onUnauthorized(); return; }
    const lines = await r.json();
    const termId = agent==='flask' ? 'log-flask' : 'log-'+agent;
    for(const l of lines){
      if(afterTs && l.ts <= afterTs) continue;  // 只追加断连后的
      // 去重:检查DOM中是否已有相同时间戳+内容
      const box = document.getElementById(termId);
      if(box && box.querySelector('[data-ts="'+l.ts+'"][data-line="'+esc(l.line).substring(0,80)+'"]')) continue;
      appendLogWithMeta(termId, l.ts, l.tag, l.line);
      appendLogWithMeta('log-all', l.ts, l.tag, l.line);
    }
  }catch(e){}
}

function appendLogWithMeta(termId, ts, tag, line){ renderMsg(termId, ts, tag, line, true); }

function connectSSE(){
  const es = new EventSource('/api/logs');
  window._es = es;
  es.addEventListener('hello', ()=>{
    // 首次连接:加载历史
    if(!_historyLoaded){
      _historyLoaded = true;
      loadHistory('claude');
      loadHistory('codebuddy');
      loadHistory('flask');
    }
  });
  es.onmessage = function(ev){
    try{
      const d = JSON.parse(ev.data);
      appendLog('log-all', d.ts, d.tag, d.line);
      // 根据 proc 字段分发到对应 agent 日志区
      // proc: 'claude' / 'codebuddy' / 'flask' (由后端 _push 时写入)
      const proc = d.proc || d.tag;  // 兼容:无 proc 时用 tag 推断
      if(proc==='claude' || d.tag==='claude')
        appendLog('log-claude', d.ts, d.tag, d.line);
      if(proc==='codebuddy' || d.tag==='codebuddy')
        appendLog('log-codebuddy', d.ts, d.tag, d.line);
      if(proc==='flask' || d.tag==='flask')
        appendLog('log-flask', d.ts, d.tag, d.line);
      // you 消息:proc 已由后端标记,直接按 proc 分发
      // system/error 消息:proc 已由后端标记,直接按 proc 分发
      // 更新最后时间戳
      _lastLogTs[d.tag] = d.ts;
    }catch(e){}
  };
  es.onerror = ()=>{
    try{ es.close(); }catch(e){}
    if(_unauthShown) return;   // 未登录就不重连
    setTimeout(()=>{
      connectSSE();
      // 重连后补拉断连期间的历史
      const lastTs = _lastLogTs['claude'] || _lastLogTs['system'] || '';
      if(lastTs){
        loadHistory('claude', lastTs);
        loadHistory('codebuddy', lastTs);
        loadHistory('flask', lastTs);
      }
    }, 1500);
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
