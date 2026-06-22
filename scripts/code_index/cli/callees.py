"""CLI 命令：code-index callees"""

from __future__ import annotations

import json
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


@click.command("callees")
@click.argument("symbol")
@click.option("--limit", "-n", default=50, show_default=True, help="最多返回条数")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", show_default=True, help="输出格式")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
def callees_cmd(symbol, limit, fmt, root):
    """查找指定符号调用的所有被调用者。

    \b
    SYMBOL 支持精确 ID 或短名（模糊匹配第一个结果）。

    \b
    Examples:
      code-index callees deleteComment
      code-index callees com.example.CommentService.deleteComment
    """
    from ..core.query_engine import QueryEngine
    graph = _load_graph(root)
    engine = QueryEngine(graph)

    candidates = engine.find(symbol, limit=5)
    if not candidates:
        click.echo(f"(symbol not found: '{symbol}')", err=True)
        raise SystemExit(1)

    sym = candidates[0]

    t0 = time.perf_counter()
    results = engine.find_callees(sym.id, limit=limit)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if fmt == "json":
        output = {
            "elapsed_ms": round(elapsed_ms, 2),
            "symbol": sym.to_dict(),
            "callees": [s.to_dict() for s in results],
        }
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Callees of [{sym.kind.value}] {sym.id}:\n")
        if not results:
            click.echo(f"  (no callees found — try running build without --no-resolve)  \033[2m[{elapsed_ms:.1f}ms]\033[0m")
        else:
            click.echo(engine.format_callers_text(results))  # 复用相同格式
            click.echo(f"\n\033[2m⏱ {elapsed_ms:.1f}ms\033[0m")
