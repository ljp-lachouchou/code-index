"""CLI 命令：code-index outline"""

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


@click.command("outline")
@click.argument("file_path")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", show_default=True, help="输出格式")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
def outline_cmd(file_path, fmt, root):
    """展示指定文件的符号大纲（类、方法、函数等）。

    \b
    FILE_PATH 支持模糊路径（如 CommentService.kt 或 service/Comment）。

    \b
    Examples:
      code-index outline src/main/CommentService.kt
      code-index outline CommentService.kt
    """
    from ..core.query_engine import QueryEngine
    graph = _load_graph(root)
    engine = QueryEngine(graph)

    t0 = time.perf_counter()
    results = engine.file_outline(file_path)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not results:
        click.echo(f"(no symbols found for path: '{file_path}')  \033[2m[{elapsed_ms:.1f}ms]\033[0m")
        return

    if fmt == "json":
        click.echo(json.dumps(
            {"elapsed_ms": round(elapsed_ms, 2), "symbols": [s.to_dict() for s in results]},
            ensure_ascii=False, indent=2,
        ))
    else:
        # 找出实际匹配到的文件路径
        matched_file = results[0].file if results else file_path
        click.echo(f"Outline of {matched_file}  ({len(results)} symbols)\n")
        click.echo(engine.format_outline_text(results))
        click.echo(f"\n\033[2m⏱ {elapsed_ms:.1f}ms\033[0m")
