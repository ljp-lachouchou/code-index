"""
Indexer — 遍历文件 + 调度 Parser + 写 graph.json

主要职责：
1. 扫描目标目录，按扩展名分发给对应 Parser
2. 并行（可选）或串行解析每个文件
3. 将所有 SymbolNode / CallEdge 合并到 IndexGraph
4. 序列化 graph.json 到 .index/ 目录
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, TaskProgressColumn, TimeElapsedColumn,
)

from .model import IndexGraph, IndexStats, SymbolNode, CallEdge
from ..parsers.registry import ParserRegistry, get_registry

console = Console()

# 默认忽略的目录
DEFAULT_IGNORE_DIRS = {
    ".git", ".svn", ".hg",
    "build", "dist", "out",
    ".gradle", ".idea", ".vscode",
    "node_modules", ".npm",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".index",           # CodeIndex 自身的索引目录
}

# 默认忽略的文件模式
DEFAULT_IGNORE_PATTERNS = {
    "*.generated.kt",
    "*.pb.kt",          # protobuf 生成
    "*BuildConfig*",    # Android 构建生成
    "R.java",           # Android 资源文件
}


class Indexer:
    """全量/增量代码索引构建器。

    Usage:
        indexer = Indexer(repo_root="/path/to/repo")
        graph = indexer.build()
        graph.save(Path("/path/to/repo/.index/graph.json"))
    """

    def __init__(
        self,
        repo_root: str,
        langs: Optional[list[str]] = None,    # None = 全部语言
        ignore_dirs: Optional[set[str]] = None,
        workers: int = 0,                      # 0 = CPU 核数
        registry: Optional[ParserRegistry] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.langs = langs                     # 过滤语言，None 表示不过滤
        self.ignore_dirs = (ignore_dirs or set()) | DEFAULT_IGNORE_DIRS
        self.workers = workers or os.cpu_count() or 4
        self.registry = registry or get_registry()

        # 确定支持的扩展名集合
        if langs:
            # 只保留指定语言的扩展名
            self._valid_exts = set()
            for lang in langs:
                parser = self.registry.get_parser_for_lang(lang)
                if parser:
                    self._valid_exts.update(parser.extensions)
        else:
            self._valid_exts = set(self.registry.supported_extensions())

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def build(
        self,
        project_name: str = "",
        show_progress: bool = True,
    ) -> IndexGraph:
        """全量构建索引。

        Returns:
            填充完毕的 IndexGraph（未保存到磁盘，由调用者决定）
        """
        start_time = time.perf_counter()

        graph = IndexGraph(
            version="1.0",
            project=project_name or self.repo_root.name,
            indexed_at=datetime.now(timezone.utc).isoformat(),
            root_path=str(self.repo_root),
        )

        # 1. 扫描文件
        files = self._scan_files()
        if show_progress:
            console.print(f"[cyan]Scanning files...[/cyan]  {len(files)} files found")

        if not files:
            console.print("[yellow]Warning: no supported files found.[/yellow]")
            return graph

        # 2. 解析文件（并行）
        all_symbols: list[SymbolNode] = []
        all_edges: list[CallEdge] = []

        files_by_lang: dict[str, int] = {}
        symbols_by_lang: dict[str, int] = {}

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Parsing...", total=len(files))
                for file_path, syms, edges in self._parse_files(files):
                    all_symbols.extend(syms)
                    all_edges.extend(edges)

                    ext = Path(file_path).suffix.lstrip(".")
                    lang_name = self.registry._ext_to_lang.get(ext, "unknown")
                    files_by_lang[lang_name] = files_by_lang.get(lang_name, 0) + 1
                    symbols_by_lang[lang_name] = symbols_by_lang.get(lang_name, 0) + len(syms)

                    progress.advance(task)
        else:
            for file_path, syms, edges in self._parse_files(files):
                all_symbols.extend(syms)
                all_edges.extend(edges)
                ext = Path(file_path).suffix.lstrip(".")
                lang_name = self.registry._ext_to_lang.get(ext, "unknown")
                files_by_lang[lang_name] = files_by_lang.get(lang_name, 0) + 1
                symbols_by_lang[lang_name] = symbols_by_lang.get(lang_name, 0) + len(syms)

        # 3. 合并到 IndexGraph
        if show_progress:
            console.print(f"[cyan]Building graph...[/cyan]  {len(all_symbols)} symbols, {len(all_edges)} edges")

        for sym in all_symbols:
            graph.add_symbol(sym)
        for edge in all_edges:
            graph.add_edge(edge)

        # 4. 更新统计
        elapsed = time.perf_counter() - start_time
        graph.stats = IndexStats(
            total_files=len(files),
            total_symbols=len(all_symbols),
            total_edges=len(all_edges),
            resolved_edges=sum(1 for e in all_edges if e.resolved),
            elapsed_seconds=elapsed,
            files_by_lang=files_by_lang,
            symbols_by_lang=symbols_by_lang,
        )

        if show_progress:
            self._print_summary(graph)

        return graph

    def build_and_save(
        self,
        index_dir: Optional[Path] = None,
        project_name: str = "",
        show_progress: bool = True,
    ) -> tuple[IndexGraph, Path]:
        """构建并保存索引。

        Returns:
            (graph, saved_path)
        """
        graph = self.build(project_name=project_name, show_progress=show_progress)

        out_dir = index_dir or (self.repo_root / ".index")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "graph.json"
        graph.save(out_path)

        # 写 manifest（增量索引用）
        self._write_manifest(graph, out_dir)

        if show_progress:
            console.print(f"[green]Saved to[/green] {out_path}")

        return graph, out_path

    # ── 文件扫描 ─────────────────────────────────────────────────────────────

    def _scan_files(self) -> list[str]:
        """递归扫描 repo_root，返回所有支持的文件路径（绝对路径）。"""
        result = []
        for root, dirs, files in os.walk(self.repo_root):
            # 就地修改 dirs 列表以跳过忽略的目录（os.walk 会遵循）
            dirs[:] = [
                d for d in dirs
                if d not in self.ignore_dirs and not d.startswith(".")
            ]

            for filename in files:
                ext = Path(filename).suffix.lstrip(".")
                if ext not in self._valid_exts:
                    continue
                if self._should_ignore_file(filename):
                    continue
                result.append(os.path.join(root, filename))

        return sorted(result)  # 排序保证确定性

    def _should_ignore_file(self, filename: str) -> bool:
        """检查文件名是否匹配忽略模式。"""
        import fnmatch
        for pattern in DEFAULT_IGNORE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    # ── 文件解析 ─────────────────────────────────────────────────────────────

    def _parse_files(
        self,
        files: list[str],
    ):
        """逐文件解析（串行，避免多进程序列化 Parser 对象的复杂性）。

        Yields:
            (file_path, symbols, edges)
        """
        repo_root_str = str(self.repo_root)

        for file_path in files:
            parser = self.registry.get_parser(file_path)
            if parser is None:
                continue
            try:
                symbols, edges = parser.parse_file(file_path, repo_root_str)
                yield file_path, symbols, edges
            except Exception as e:
                console.print(f"[red]Error parsing {file_path}: {e}[/red]")
                yield file_path, [], []

    # ── 增量合并 ─────────────────────────────────────────────────────────────

    def merge_into(
        self,
        graph: IndexGraph,
        dirty_files: list[str],
        deleted_files: list[str],
    ) -> int:
        """增量更新：将 dirty_files 重新解析后合并到已有 graph。

        Returns:
            重新解析的文件数
        """
        repo_root_str = str(self.repo_root)

        # 移除已删除文件的符号
        for f in deleted_files:
            rel = str(Path(f).relative_to(self.repo_root))
            graph.remove_file(rel)

        # 移除 dirty 文件的旧符号（然后重新解析）
        for f in dirty_files:
            rel = str(Path(f).relative_to(self.repo_root))
            graph.remove_file(rel)

        # 重新解析 dirty 文件
        count = 0
        for file_path, syms, edges in self._parse_files(dirty_files):
            for sym in syms:
                graph.add_symbol(sym)
            for edge in edges:
                graph.add_edge(edge)
            count += 1

        return count

    # ── Manifest（增量索引状态文件）────────────────────────────────────────

    def _write_manifest(self, graph: IndexGraph, index_dir: Path) -> None:
        """写 manifest.json，记录每个文件的 mtime 和 size。"""
        import json

        manifest = {}
        for rel_path in graph._by_file:
            abs_path = self.repo_root / rel_path
            try:
                stat = abs_path.stat()
                manifest[rel_path] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            except FileNotFoundError:
                pass

        manifest_path = index_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # ── 输出 ─────────────────────────────────────────────────────────────────

    def _print_summary(self, graph: IndexGraph) -> None:
        stats = graph.stats
        console.print("\n[bold green]Index complete![/bold green]")
        console.print(f"  Files:   {stats.total_files:,}")
        console.print(f"  Symbols: {stats.total_symbols:,}")
        console.print(f"  Edges:   {stats.total_edges:,}")
        console.print(f"  Time:    {stats.elapsed_seconds:.1f}s")

        if stats.files_by_lang:
            console.print("\n[dim]Languages:[/dim]")
            for lang, count in sorted(stats.files_by_lang.items()):
                sym_count = stats.symbols_by_lang.get(lang, 0)
                console.print(f"  {lang:12s} {count:5,} files | {sym_count:6,} symbols")
