"""CLI 命令：code-index status"""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.command("status")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text", show_default=True, help="输出格式")
@click.option("--root", "-r", default=".", show_default=True, help="仓库根目录")
def status_cmd(fmt, root):
    """显示索引状态（文件数、符号数、解析率等）。

    \b
    Examples:
      code-index status
      code-index status --format json
    """
    from ..core.incremental import IncrementalIndexer

    repo_root = Path(root).resolve()
    inc = IncrementalIndexer(repo_root=str(repo_root))
    info = inc.status()

    if fmt == "json":
        click.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return

    # 文本格式
    status_label = info.get("status", "unknown")
    color = "green" if status_label == "ok" else ("yellow" if status_label == "stale" else "red")

    click.echo(f"\ncode-index status  [{repo_root}]\n")
    click.echo(f"  Status       : {status_label}")

    if "error" in info:
        click.echo(f"  Error        : {info['error']}")
        return

    click.echo(f"  Indexed at   : {info.get('indexed_at', 'n/a')}")
    click.echo(f"  Version      : {info.get('version', 'n/a')}")
    click.echo(f"  Files        : {info.get('total_files', 0)}")
    click.echo(f"  Symbols      : {info.get('total_symbols', 0)}")
    click.echo(f"  Edges        : {info.get('total_edges', 0)}")

    resolved = info.get("resolved_edges", 0)
    total_edges = info.get("total_edges", 0)
    if total_edges:
        pct = resolved / total_edges * 100
        click.echo(f"  Resolved     : {resolved}/{total_edges} ({pct:.1f}%)")

    dirty = info.get("dirty_files", 0)
    deleted = info.get("deleted_files", 0)
    if dirty or deleted:
        click.echo(f"\n  [!] Index may be stale:")
        if dirty:
            click.echo(f"      modified files : {dirty}")
        if deleted:
            click.echo(f"      deleted files  : {deleted}")
        click.echo("\n  Run `code-index build` to refresh.\n")
    else:
        click.echo(f"\n  Index is up to date.\n")
