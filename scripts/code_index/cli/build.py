"""CLI 命令：code-index build"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click


@click.command("build")
@click.option(
    "--root", "-r",
    default=".",
    show_default=True,
    help="仓库根目录（默认当前目录）",
)
@click.option(
    "--lang", "-l",
    multiple=True,
    help="只索引指定语言（可多次指定）：kotlin, java, swift, objc, typescript",
)
@click.option(
    "--full", "-f",
    is_flag=True,
    default=False,
    help="强制全量重建（忽略增量缓存）",
)
@click.option(
    "--index-dir",
    default=None,
    help="索引保存目录（默认 <root>/.index）",
)
@click.option(
    "--no-vfs",
    is_flag=True,
    default=False,
    help="跳过 VFS 静态文件生成",
)
@click.option(
    "--no-resolve",
    is_flag=True,
    default=False,
    help="跳过跨文件符号解析（加快构建速度）",
)
def build_cmd(
    root: str,
    lang: tuple[str],
    full: bool,
    index_dir: Optional[str],
    no_vfs: bool,
    no_resolve: bool,
) -> None:
    """构建（或增量更新）代码索引。

    \b
    Examples:
      code-index build                     # 全量（或增量）构建
      code-index build --lang kotlin       # 只索引 Kotlin/Java
      code-index build --full              # 强制全量重建
    """
    from rich.console import Console
    from ..core.incremental import IncrementalIndexer
    from ..core.resolver import Resolver
    from ..core.vfs_generator import VfsGenerator
    from ..parsers.registry import get_registry

    console = Console()

    repo_root = Path(root).resolve()
    if not repo_root.is_dir():
        console.print(f"[red]Error: {repo_root} is not a directory[/red]")
        raise SystemExit(1)

    idx_dir = Path(index_dir) if index_dir else None
    langs = list(lang) if lang else None

    # 构建前预检：检查请求的语言是否有 grammar 可用
    registry = get_registry()
    available = set(registry.available_parsers())
    requested_langs = langs or list(registry.supported_languages())
    missing_grammars = [l for l in requested_langs if l not in available]
    if missing_grammars:
        console.print(
            f"[yellow]Warning: 以下语言的 grammar 未编译，这些语言的文件将被跳过：[/yellow] "
            f"[bold]{', '.join(missing_grammars)}[/bold]"
        )
        console.print(
            f"[yellow]  请运行: [bold]cd scripts && make grammars[/bold]  "
            f"（或单独编译：make grammars-typescript）[/yellow]"
        )

    inc = IncrementalIndexer(
        repo_root=str(repo_root),
        index_dir=idx_dir,
        langs=langs,
    )

    graph, changed = inc.update(force_full=full, show_progress=True)

    # 跨文件符号解析
    if not no_resolve and changed > 0:
        console.print("[cyan]Resolving cross-file references...[/cyan]", end=" ")
        resolver = Resolver(graph)
        resolved = resolver.resolve_all()
        console.print(f"[green]{resolved} edges resolved[/green]")

        # 保存解析后的图
        idx_path = (idx_dir or (repo_root / ".index")) / "graph.json"
        graph.save(idx_path)

    # 生成 VFS 静态文件
    if not no_vfs:
        vfs_root = (idx_dir or (repo_root / ".index")) / "vfs"
        console.print("[cyan]Generating VFS...[/cyan]", end=" ")
        vfs_gen = VfsGenerator()
        vfs_gen.generate(graph, vfs_root)
        console.print("[green]done[/green]")
