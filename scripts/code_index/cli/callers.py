"""CLI 命令：code-index callers"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click


def _load_graph(root: str):
    from ..core.model import IndexGraph
    graph_path = Path(root).resolve() / ".index" / "graph.json"
    if not graph_path.exists():
        click.echo(
            f"[ERROR] 索引不存在：{graph_path}\n请先运行: code-index build",
            err=True,
        )
        raise SystemExit(1)
    return IndexGraph.load(graph_path)


@click.command("callers")
@click.argument("symbol")
@click.option("--limit", "-n", default=50, show_default=True, help="最多返回条数")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", show_default=True, help="输出格式")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
@click.option("--no-daemon", is_flag=True, default=False, hidden=True)
def callers_cmd(symbol, limit, fmt, root, no_daemon):
    """查找调用指定符号的所有调用者。

    \b
    SYMBOL 支持精确 ID 或短名（模糊匹配第一个结果）。

    \b
    Examples:
      code-index callers deleteComment
      code-index callers com.example.CommentService.deleteComment
    """
    resolved_root = str(Path(root).resolve())

    # ── daemon 快速路径 ────────────────────────────────────────────────────────
    if not no_daemon and sys.platform != "win32":
        from .daemon import ensure_daemon, _call_daemon
        from ..core.model import SymbolNode
        sock = ensure_daemon(resolved_root)
        if sock is not None:
            # step1: find_one
            r1 = _call_daemon(sock, {"cmd": "find_one", "args": {"symbol": symbol}})
            if r1.get("ok") and r1["data"]:
                sym_dict = r1["data"][0]
                sym_id = sym_dict["id"]
                # step2: callers
                t0 = time.perf_counter()
                r2 = _call_daemon(sock, {"cmd": "callers",
                                         "args": {"sym_id": sym_id, "limit": limit}})
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if r2.get("ok"):
                    data = r2["data"]
                    if fmt == "json":
                        click.echo(json.dumps(
                            {"elapsed_ms": round(elapsed_ms, 2),
                             "symbol": sym_dict, "callers": data},
                            ensure_ascii=False, indent=2,
                        ))
                    else:
                        click.echo(f"Callers of [{sym_dict['kind']}] {sym_id}:\n")
                        if not data:
                            click.echo(f"  (no callers found)  \033[2m[{elapsed_ms:.1f}ms]\033[0m")
                        else:
                            from ..core.query_engine import QueryEngine
                            syms = [SymbolNode.from_dict(d) for d in data]
                            _graph = _load_graph(resolved_root)
                            click.echo(QueryEngine(_graph).format_callers_text(syms))
                            click.echo(f"\n\033[2m⏱ {elapsed_ms:.1f}ms\033[0m")
                    return
            elif not r1.get("ok") or not r1.get("data"):
                click.echo(f"(symbol not found: '{symbol}')", err=True)
                raise SystemExit(1)

    # ── 直连回退 ──────────────────────────────────────────────────────────────
    from ..core.query_engine import QueryEngine
    graph = _load_graph(resolved_root)
    engine = QueryEngine(graph)

    candidates = engine.find(symbol, limit=5)
    if not candidates:
        click.echo(f"(symbol not found: '{symbol}')", err=True)
        raise SystemExit(1)

    sym = candidates[0]

    t0 = time.perf_counter()
    results = engine.find_callers(sym.id, limit=limit)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if fmt == "json":
        output = {
            "elapsed_ms": round(elapsed_ms, 2),
            "symbol": sym.to_dict(),
            "callers": [s.to_dict() for s in results],
        }
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Callers of [{sym.kind.value}] {sym.id}:\n")
        if not results:
            click.echo(f"  (no callers found)  \033[2m[{elapsed_ms:.1f}ms]\033[0m")
        else:
            click.echo(engine.format_callers_text(results))
            click.echo(f"\n\033[2m⏱ {elapsed_ms:.1f}ms\033[0m")
