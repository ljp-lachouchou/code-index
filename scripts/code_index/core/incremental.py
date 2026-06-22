"""
IncrementalIndexer — 增量索引

通过比对 manifest.json 中记录的 mtime/size 与当前文件状态，
找出 dirty（新增或修改）和 deleted（已删除）文件，
只重新解析 dirty 文件。

预期性能（~4000 Kotlin 文件的仓库）：
  - 修改 5 个文件后增量更新：< 3s
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .model import IndexGraph
from .indexer import Indexer


@dataclass
class FileRecord:
    """manifest 中一个文件的状态记录。"""
    mtime: float
    size: int


class IncrementalIndexer:
    """增量索引管理器。

    Usage:
        inc = IncrementalIndexer(repo_root="/path/to/repo")
        graph, changed = inc.update()  # 自动判断全量/增量
    """

    def __init__(
        self,
        repo_root: str,
        index_dir: Optional[Path] = None,
        langs: Optional[list[str]] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.index_dir = index_dir or (self.repo_root / ".index")
        self.langs = langs

        self._graph_path = self.index_dir / "graph.json"
        self._manifest_path = self.index_dir / "manifest.json"

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def update(
        self,
        force_full: bool = False,
        show_progress: bool = True,
    ) -> tuple[IndexGraph, int]:
        """更新索引（自动判断全量/增量）。

        Args:
            force_full:    强制全量重建（忽略 manifest）
            show_progress: 是否显示进度

        Returns:
            (graph, changed_files_count)
        """
        if force_full or not self._graph_path.exists():
            return self._full_build(show_progress)

        return self._incremental_update(show_progress)

    def _full_build(self, show_progress: bool) -> tuple[IndexGraph, int]:
        """全量构建。"""
        indexer = Indexer(
            repo_root=str(self.repo_root),
            langs=self.langs,
        )
        graph, _ = indexer.build_and_save(
            index_dir=self.index_dir,
            show_progress=show_progress,
        )
        return graph, graph.stats.total_files

    def _incremental_update(self, show_progress: bool) -> tuple[IndexGraph, int]:
        """增量更新：只重新解析变化的文件。"""
        from rich.console import Console
        console = Console()

        # 1. 加载旧 graph
        graph = IndexGraph.load(self._graph_path)

        # 2. 读取 manifest
        manifest = self._load_manifest()

        # 3. 扫描当前文件（复用 Indexer 的扫描逻辑）
        indexer = Indexer(
            repo_root=str(self.repo_root),
            langs=self.langs,
        )
        current_files = indexer._scan_files()
        current_rel = [
            str(Path(f).relative_to(self.repo_root))
            for f in current_files
        ]

        # 4. 计算 diff
        dirty_rel, deleted_rel = self.compute_diff(manifest, current_rel)

        if not dirty_rel and not deleted_rel:
            if show_progress:
                console.print("[green]Index is up-to-date.[/green]")
            return graph, 0

        if show_progress:
            console.print(
                f"[cyan]Incremental update:[/cyan] "
                f"{len(dirty_rel)} changed, {len(deleted_rel)} deleted"
            )

        # 5. 转换回绝对路径
        dirty_abs = [str(self.repo_root / p) for p in dirty_rel]
        deleted_abs = [str(self.repo_root / p) for p in deleted_rel]

        # 6. 合并更新
        changed = indexer.merge_into(graph, dirty_abs, deleted_abs)

        # 7. 保存
        graph.save(self._graph_path)
        indexer._write_manifest(graph, self.index_dir)

        if show_progress:
            console.print(
                f"[green]Done:[/green] updated {changed} files, "
                f"graph now has {len(graph.symbols):,} symbols"
            )

        return graph, changed

    # ── Diff 计算 ────────────────────────────────────────────────────────────

    def compute_diff(
        self,
        manifest: dict[str, FileRecord],
        current_files: list[str],  # 相对路径
    ) -> tuple[list[str], list[str]]:
        """
        返回 (dirty_files, deleted_files)。
        dirty = 新增 + 内容变化（mtime 或 size 不同）。
        """
        manifest_set = set(manifest.keys())
        current_set = set(current_files)

        new_files = list(current_set - manifest_set)
        deleted_files = list(manifest_set - current_set)
        modified_files = [
            p for p in manifest_set & current_set
            if self._is_modified(p, manifest[p])
        ]

        return new_files + modified_files, deleted_files

    def _is_modified(self, rel_path: str, record: FileRecord) -> bool:
        """判断文件是否已修改（mtime 或 size 变化）。"""
        abs_path = self.repo_root / rel_path
        try:
            stat = abs_path.stat()
            return stat.st_mtime != record.mtime or stat.st_size != record.size
        except FileNotFoundError:
            return True

    # ── Manifest I/O ─────────────────────────────────────────────────────────

    def _load_manifest(self) -> dict[str, FileRecord]:
        """加载 manifest.json，返回 {rel_path: FileRecord}。"""
        if not self._manifest_path.exists():
            return {}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                path: FileRecord(mtime=rec["mtime"], size=rec["size"])
                for path, rec in data.items()
            }
        except Exception:
            return {}

    # ── 状态查询 ─────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """返回索引状态信息。"""
        if not self._graph_path.exists():
            return {"status": "not_indexed"}

        stat = self._graph_path.stat()
        graph = IndexGraph.load(self._graph_path)

        manifest = self._load_manifest()
        indexer = Indexer(repo_root=str(self.repo_root), langs=self.langs)
        current_files = indexer._scan_files()
        current_rel = [
            str(Path(f).relative_to(self.repo_root))
            for f in current_files
        ]
        dirty, deleted = self.compute_diff(manifest, current_rel)

        return {
            "status": "up-to-date" if not dirty and not deleted else "stale",
            "indexed_at": graph.indexed_at,
            "graph_mtime": stat.st_mtime,
            "total_files": graph.stats.total_files,
            "total_symbols": len(graph.symbols),
            "total_edges": len(graph.edges),
            "files_by_lang": graph.stats.files_by_lang,
            "dirty_count": len(dirty),
            "deleted_count": len(deleted),
        }
