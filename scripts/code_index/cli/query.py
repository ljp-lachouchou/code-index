"""CLI 命令：code-index query"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click


def _load_graph(root: str):
    """加载 IndexGraph，失败时友好提示。"""
    from ..core.model import IndexGraph
    graph_path = Path(root).resolve() / ".index" / "graph.json"
    if not graph_path.exists():
        click.echo(
            f"[ERROR] 索引不存在：{graph_path}\n"
            "请先运行: code-index build",
            err=True,
        )
        raise SystemExit(1)
    return IndexGraph.load(graph_path)


def _render(results_dicts: list[dict], elapsed_ms: float, fmt: str,
            pattern: str, engine=None):
    """统一渲染 query 结果（直连和 daemon 共用）。"""
    if fmt == "json":
        click.echo(json.dumps(
            {"elapsed_ms": round(elapsed_ms, 2), "results": results_dicts},
            ensure_ascii=False, indent=2,
        ))
    else:
        if not results_dicts:
            click.echo(f"(no results for '{pattern}')  \033[2m[{elapsed_ms:.1f}ms]\033[0m")
            return
        click.echo(f"Found {len(results_dicts)} symbol(s) for '{pattern}':\n")
        if engine:
            from ..core.model import SymbolNode
            syms = [SymbolNode.from_dict(d) for d in results_dicts]
            click.echo(engine.format_symbols_text(syms))
        else:
            for d in results_dicts:
                click.echo(f"  [{d.get('kind','?')}] {d.get('id','')}  "
                           f"{d.get('file','')}:{d.get('line','')}")
        click.echo(f"\n\033[2m⏱ {elapsed_ms:.1f}ms\033[0m")


@click.command("query")
@click.argument("pattern")
@click.option("--kind", "-k", default=None,
              help="过滤类型：class|interface|function|method|object|enum|protocol|component")
@click.option("--lang", "-l", default=None,
              help="过滤语言：kotlin|java|swift|objc|typescript")
@click.option("--limit", "-n", default=50, show_default=True, help="最多返回条数")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", show_default=True, help="输出格式")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
@click.option("--no-daemon", is_flag=True, default=False, hidden=True,
              help="强制直连模式，跳过 daemon")
def query_cmd(pattern, kind, lang, limit, fmt, root, no_daemon):
    """查找符号定义。

    \b
    PATTERN 支持：
      精确      deleteComment
      前缀      delete*
      通配      *Comment, del?te
      全限定后缀 .v2.CommentVO
    """
    resolved_root = str(Path(root).resolve())

    # ── 尝试走 daemon 快速路径 ──────────────────────────────────────────────
    if not no_daemon and sys.platform != "win32":
        from .daemon import ensure_daemon, _call_daemon
        sock = ensure_daemon(resolved_root)
        if sock is not None:
            t0 = time.perf_counter()
            resp = _call_daemon(sock, {
                "cmd": "query",
                "args": {"pattern": pattern, "kind": kind,
                         "language": lang, "limit": limit},
            })
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if resp.get("ok"):
                _render(resp["data"], elapsed_ms, fmt, pattern)
                return

    # ── 直连回退（daemon 不可用 / --no-daemon）──────────────────────────────
    from ..core.query_engine import QueryEngine
    graph = _load_graph(resolved_root)
    engine = QueryEngine(graph)

    t0 = time.perf_counter()
    results = engine.find(pattern, kind=kind, language=lang, limit=limit)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    _render([s.to_dict() for s in results], elapsed_ms, fmt, pattern, engine)
