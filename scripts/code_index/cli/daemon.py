"""
Daemon 模式：code-index serve / code-index stop

架构：
  ┌─────────────────────────────────────────────────────────────┐
  │  daemon 进程（长驻后台）                                      │
  │  • 启动时加载 IndexGraph 到内存                               │
  │  • 监听 Unix socket  ~/.cache/code-index/<hash>.sock         │
  │  • 接收 JSON-RPC 风格请求，执行查询，返回 JSON               │
  └─────────────────────────────────────────────────────────────┘
         ↑ socket
  ┌─────────────┐
  │ 薄客户端     │  每次 CLI 调用：连接 → 发请求 → 收结果 → 退出
  │ （本文件）   │  如果 socket 不存在则自动 fork 启动 daemon
  └─────────────┘

通信协议（newline-delimited JSON）：
  请求：{"cmd": "query", "args": {...}}  + "\n"
  响应：{"ok": true,  "data": ...}       + "\n"
      或 {"ok": false, "error": "..."}   + "\n"

支持的 cmd：
  query       → engine.find(pattern, kind, language, limit)
  callers     → engine.find_callers(sym_id, limit)
  callees     → engine.find_callees(sym_id, limit)
  outline     → engine.file_outline(file_path)
  impls       → engine.find_implementations(sym_id, limit)
  find_one    → engine.find(symbol, limit=5)   （供 callers/callees/impls 用）
  ping        → 保活探测
  stop        → 优雅关闭 daemon
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import socketserver
import sys
import time
from pathlib import Path


# ── socket 路径 ───────────────────────────────────────────────────────────────

def _sock_path(root: str) -> Path:
    """根据仓库根目录路径生成唯一 socket 文件路径。"""
    h = hashlib.md5(str(Path(root).resolve()).encode()).hexdigest()[:12]
    cache_dir = Path.home() / ".cache" / "code-index"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{h}.sock"


def _pid_path(root: str) -> Path:
    sock = _sock_path(root)
    return sock.with_suffix(".pid")


# ── 服务端 ────────────────────────────────────────────────────────────────────

class _Handler(socketserver.StreamRequestHandler):
    """处理单条连接（每条连接处理一个 JSON 请求然后关闭）。"""

    def handle(self):
        try:
            raw = self.rfile.readline()
            if not raw:
                return
            req = json.loads(raw.decode())
            resp = self.server._dispatch(req)
        except Exception as e:
            resp = {"ok": False, "error": str(e)}
        self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode())


class _DaemonServer(socketserver.UnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, sock_path: str, engine, graph):
        self._engine = engine
        self._graph = graph
        self._running = True
        super().__init__(sock_path, _Handler)

    def _dispatch(self, req: dict) -> dict:
        cmd = req.get("cmd", "")
        args = req.get("args", {})

        if cmd == "ping":
            return {"ok": True, "data": "pong"}

        if cmd == "stop":
            self._running = False
            return {"ok": True, "data": "stopping"}

        t0 = time.perf_counter()

        try:
            if cmd == "find_one":
                results = self._engine.find(args["symbol"], limit=5)
                data = [s.to_dict() for s in results]

            elif cmd == "query":
                results = self._engine.find(
                    args["pattern"],
                    kind=args.get("kind"),
                    language=args.get("language"),
                    limit=args.get("limit", 50),
                )
                data = [s.to_dict() for s in results]

            elif cmd == "callers":
                results = self._engine.find_callers(args["sym_id"], limit=args.get("limit", 50))
                data = [s.to_dict() for s in results]

            elif cmd == "callees":
                results = self._engine.find_callees(args["sym_id"], limit=args.get("limit", 50))
                data = [s.to_dict() for s in results]

            elif cmd == "outline":
                results = self._engine.file_outline(args["file_path"])
                data = [s.to_dict() for s in results]

            elif cmd == "impls":
                results = self._engine.find_implementations(args["sym_id"], limit=args.get("limit", 50))
                data = [s.to_dict() for s in results]

            else:
                return {"ok": False, "error": f"unknown cmd: {cmd}"}

        except Exception as e:
            return {"ok": False, "error": str(e)}

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"ok": True, "data": data, "elapsed_ms": elapsed_ms}

    def serve_until_stop(self):
        self.socket.settimeout(1.0)
        while self._running:
            try:
                self.handle_request()
            except socket.timeout:
                pass


def _run_daemon(root: str):
    """真正在后台运行的 daemon 进程入口（被 fork 后调用）。"""
    from ..core.model import IndexGraph
    from ..core.query_engine import QueryEngine

    sock_path = _sock_path(root)
    pid_path = _pid_path(root)

    # 写 PID 文件
    pid_path.write_text(str(os.getpid()))

    # 加载索引
    graph_path = Path(root).resolve() / ".index" / "graph.json"
    if not graph_path.exists():
        sys.exit(1)

    graph = IndexGraph.load(graph_path)
    engine = QueryEngine(graph)

    # 清理旧 socket
    if sock_path.exists():
        sock_path.unlink()

    def _on_signal(sig, frame):
        server._running = False

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    server = _DaemonServer(str(sock_path), engine, graph)
    try:
        server.serve_until_stop()
    finally:
        server.server_close()
        if sock_path.exists():
            sock_path.unlink()
        if pid_path.exists():
            pid_path.unlink()


# ── 客户端 ────────────────────────────────────────────────────────────────────

def _is_daemon_alive(sock_path: Path) -> bool:
    """检查 daemon 是否存活（发 ping 探测）。"""
    if not sock_path.exists():
        return False
    try:
        resp = _call_daemon(sock_path, {"cmd": "ping"}, timeout=1.0)
        return resp.get("ok") is True
    except Exception:
        return False


def _call_daemon(sock_path: Path, req: dict, timeout: float = 5.0) -> dict:
    """向 daemon 发送一个请求并返回响应。"""
    data = (json.dumps(req, ensure_ascii=False) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall(data)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode())


def _start_daemon(root: str) -> bool:
    """fork 启动 daemon，等待 socket 就绪，最多等 3 秒。返回是否成功。"""
    sock_path = _sock_path(root)

    pid = os.fork()
    if pid == 0:
        # 子进程：成为独立的 daemon
        os.setsid()
        # 重定向标准 IO
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        os.close(devnull)
        # 再 fork 一次让 init 收养（防止僵尸）
        if os.fork() > 0:
            os._exit(0)
        _run_daemon(root)
        os._exit(0)

    os.waitpid(pid, 0)  # 等第一个子进程退出

    # 轮询等待 socket 就绪
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if _is_daemon_alive(sock_path):
            return True
        time.sleep(0.05)
    return False


def ensure_daemon(root: str) -> Path | None:
    """确保 daemon 存活，返回 socket 路径；失败返回 None（回退到直连模式）。"""
    if sys.platform == "win32":
        return None  # Windows 不支持 Unix socket + fork
    sock_path = _sock_path(root)
    if _is_daemon_alive(sock_path):
        return sock_path
    if _start_daemon(root):
        return sock_path
    return None


# ── CLI 命令 ──────────────────────────────────────────────────────────────────

import click  # noqa: E402（click 在此处导入是必要的）


@click.command("serve")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
@click.option("--foreground", "-f", is_flag=True, default=False,
              help="前台运行（不 fork，便于调试）")
def serve_cmd(root, foreground):
    """启动后台 daemon，加速后续查询命令（无需每次重新加载索引）。

    \b
    首次查询时会自动启动 daemon，也可手动提前启动：
      code-index serve
      code-index serve --foreground   # 前台调试模式

    daemon 使用 Unix socket 通信，socket 文件位于：
      ~/.cache/code-index/<hash>.sock
    """
    resolved = str(Path(root).resolve())
    graph_path = Path(resolved) / ".index" / "graph.json"
    if not graph_path.exists():
        click.echo(f"[ERROR] 索引不存在：{graph_path}\n请先运行: code-index build", err=True)
        raise SystemExit(1)

    sock_path = _sock_path(resolved)

    if foreground:
        click.echo(f"Starting daemon (foreground) for {resolved}")
        click.echo(f"Socket: {sock_path}")
        _run_daemon(resolved)
    else:
        if _is_daemon_alive(sock_path):
            click.echo(f"Daemon already running  (socket: {sock_path})")
            return
        click.echo(f"Starting daemon for {resolved} ...", nl=False)
        ok = _start_daemon(resolved)
        if ok:
            click.echo(f" OK  (socket: {sock_path})")
        else:
            click.echo(" FAILED (check index exists)")
            raise SystemExit(1)


@click.command("stop")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
def stop_cmd(root):
    """停止后台 daemon。"""
    resolved = str(Path(root).resolve())
    sock_path = _sock_path(resolved)

    if not _is_daemon_alive(sock_path):
        click.echo("No daemon running.")
        return

    try:
        _call_daemon(sock_path, {"cmd": "stop"})
        click.echo("Daemon stopped.")
    except Exception as e:
        click.echo(f"Error stopping daemon: {e}", err=True)
        raise SystemExit(1)
