"""
VfsGenerator — 从 IndexGraph 生成 .index/vfs/ 静态文件目录

纯函数式设计：给定同一个 graph → 确定性地生成相同文件。
生成内容是人类可读的文本，Agent 直接 cat 即可，无需额外工具。

目录结构：
  .index/vfs/
    by-name/<symbol_name>       # 符号名 → 定义位置
    by-file/<escaped_path>      # 文件路径 → 文件内所有符号
    by-kind/<kind>              # 类型 → 所有该类型符号
    callers/<symbol_name>       # 符号名 → 所有调用者
    callees/<symbol_name>       # 符号名 → 所有被调用者
    impls/<symbol_name>         # 接口名 → 所有实现类
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .model import IndexGraph, SymbolNode, SymbolKind

# 文件内每条符号摘要的分割线
DIVIDER = "─" * 72


class VfsGenerator:
    """从 IndexGraph 生成 .index/vfs/ 静态文件目录。"""

    def generate(self, graph: IndexGraph, vfs_root: Path) -> None:
        """生成所有 VFS 静态文件。"""
        vfs_root.mkdir(parents=True, exist_ok=True)

        self._gen_by_name(graph, vfs_root / "by-name")
        self._gen_by_file(graph, vfs_root / "by-file")
        self._gen_by_kind(graph, vfs_root / "by-kind")
        self._gen_callers(graph, vfs_root / "callers")
        self._gen_callees(graph, vfs_root / "callees")
        self._gen_impls(graph, vfs_root / "impls")

    # ── by-name ──────────────────────────────────────────────────────────────

    def _gen_by_name(self, graph: IndexGraph, out: Path) -> None:
        """
        by-name/<name>：符号短名 → 所有同名符号定义。

        macOS 文件系统默认大小写不敏感（APFS case-insensitive），因此
        "deleteComment" 和 "DeleteComment" 会指向同一个文件，后写入的会
        覆盖先写入的。

        修复策略：按 lower-case 文件名分组，将所有大小写变体（"deleteComment"
        和 "DeleteComment"）的符号合并写入同一个文件，并在 header 中列出
        所有实际名称，避免信息丢失。
        """
        out.mkdir(exist_ok=True)

        # 按 lower-case 文件名分组：{safe_lower_name → [(original_name, [SymbolNode])]}
        groups: dict[str, list[tuple[str, list[SymbolNode]]]] = {}
        for name, ids in graph._by_name.items():
            syms = [graph.symbols[i] for i in ids if i in graph.symbols]
            if not syms:
                continue
            key = self._safe_filename(name).lower()
            groups.setdefault(key, []).append((name, syms))

        for safe_lower_name, name_syms_pairs in groups.items():
            # 有冲突（多个大小写变体）时，在 header 中列出所有名称
            all_names = sorted({n for n, _ in name_syms_pairs})
            all_syms = [s for _, syms in name_syms_pairs for s in syms]
            # 按文件位置排序，方便阅读
            all_syms.sort(key=lambda s: (s.file, s.line))

            if len(all_names) == 1:
                header = f"Definitions of '{all_names[0]}' ({len(all_syms)})"
            else:
                # 大小写冲突时注明合并的名称
                merged = " / ".join(f"'{n}'" for n in all_names)
                header = f"Definitions of {merged} [{len(all_syms)} total, case-merged]"

            content = self._format_symbol_list(header=header, symbols=all_syms)
            (out / safe_lower_name).write_text(content, encoding="utf-8")

    # ── by-file ──────────────────────────────────────────────────────────────

    def _gen_by_file(self, graph: IndexGraph, out: Path) -> None:
        """by-file/<escaped_path>：文件路径 → 文件内所有符号大纲。"""
        out.mkdir(exist_ok=True)
        for file_path, ids in graph._by_file.items():
            syms = [graph.symbols[i] for i in ids if i in graph.symbols]
            if not syms:
                continue
            # 按行号排序
            syms = sorted(syms, key=lambda s: s.line)
            content = self._format_outline(file_path, syms)
            # 文件路径 → 安全文件名（/ → __)
            safe_name = self._safe_filename(file_path)
            (out / safe_name).write_text(content, encoding="utf-8")

    # ── by-kind ──────────────────────────────────────────────────────────────

    def _gen_by_kind(self, graph: IndexGraph, out: Path) -> None:
        """by-kind/<kind>：类型 → 所有该类型符号。"""
        out.mkdir(exist_ok=True)
        for kind_value, ids in graph._by_kind.items():
            syms = [graph.symbols[i] for i in ids if i in graph.symbols]
            if not syms:
                continue
            syms = sorted(syms, key=lambda s: s.name)
            content = self._format_symbol_list(
                header=f"{kind_value.upper()} symbols ({len(syms)})",
                symbols=syms,
            )
            (out / kind_value).write_text(content, encoding="utf-8")

    # ── callers ──────────────────────────────────────────────────────────────

    def _gen_callers(self, graph: IndexGraph, out: Path) -> None:
        """
        callers/<name>：符号短名 → 所有调用者。

        同名符号（多个模块都有 deleteComment）合并到同一文件。
        按 lower-case 文件名分组，避免 macOS 大小写不敏感文件系统冲突。
        """
        out.mkdir(exist_ok=True)
        # 先按 lower-case 文件名聚合 content
        merged: dict[str, str] = {}
        for symbol in sorted(graph.symbols.values(), key=lambda s: s.id):
            caller_ids = graph.callers_of(symbol.id)
            if not caller_ids:
                continue
            caller_syms = [graph.symbols[cid] for cid in caller_ids if cid in graph.symbols]
            if not caller_syms:
                continue
            chunk = self._format_callers(symbol, caller_syms)
            key = self._safe_filename(symbol.name).lower()
            merged[key] = (merged[key] + "\n\n" + chunk) if key in merged else chunk
        for key, content in merged.items():
            (out / key).write_text(content, encoding="utf-8")

    # ── callees ──────────────────────────────────────────────────────────────

    def _gen_callees(self, graph: IndexGraph, out: Path) -> None:
        """
        callees/<name>：符号短名 → 所有被调用的函数。

        同上，按 lower-case 文件名分组合并。
        """
        out.mkdir(exist_ok=True)
        merged: dict[str, str] = {}
        for symbol in sorted(graph.symbols.values(), key=lambda s: s.id):
            callee_ids = graph.callees_of(symbol.id)
            if not callee_ids:
                continue
            callee_syms = [graph.symbols[cid] for cid in callee_ids if cid in graph.symbols]
            if not callee_syms:
                continue
            chunk = self._format_callees(symbol, callee_syms)
            key = self._safe_filename(symbol.name).lower()
            merged[key] = (merged[key] + "\n\n" + chunk) if key in merged else chunk
        for key, content in merged.items():
            (out / key).write_text(content, encoding="utf-8")

    # ── impls ────────────────────────────────────────────────────────────────

    def _gen_impls(self, graph: IndexGraph, out: Path) -> None:
        """
        impls/<name>：接口/抽象类 → 所有实现/子类。

        同上，按 lower-case 文件名分组合并。
        """
        out.mkdir(exist_ok=True)
        merged: dict[str, str] = {}
        for symbol in sorted(graph.symbols.values(), key=lambda s: s.id):
            impl_ids = graph.impls_of(symbol.id)
            if not impl_ids:
                continue
            impl_syms = [graph.symbols[iid] for iid in impl_ids if iid in graph.symbols]
            if not impl_syms:
                continue
            chunk = self._format_impls(symbol, impl_syms)
            key = self._safe_filename(symbol.name).lower()
            merged[key] = (merged[key] + "\n\n" + chunk) if key in merged else chunk
        for key, content in merged.items():
            (out / key).write_text(content, encoding="utf-8")

    # ── 格式化方法 ───────────────────────────────────────────────────────────

    def _format_symbol_list(self, header: str, symbols: list[SymbolNode]) -> str:
        lines = [header, DIVIDER]
        for sym in symbols:
            lines.append(self._symbol_entry(sym))
            lines.append("")
        return "\n".join(lines)

    def _format_outline(self, file_path: str, symbols: list[SymbolNode]) -> str:
        lines = [
            f"# {file_path}",
            f"# {len(symbols)} symbols",
            DIVIDER,
            "",
        ]
        for sym in symbols:
            indent = "    " if sym.parent_id else ""
            vis = f"[{sym.visibility}] " if sym.visibility != "public" else ""
            kind_str = sym.kind.value.upper()
            sig = f"  # {sym.signature}" if sym.signature else ""
            lines.append(
                f"{indent}L{sym.line:4d}  {vis}{kind_str} {sym.name}{sig}"
            )
        return "\n".join(lines)

    def _format_callers(
        self,
        target: SymbolNode,
        callers: list[SymbolNode],
    ) -> str:
        lines = [
            f"Callers of {target.id} ({len(callers)})",
            DIVIDER,
        ]
        for caller in sorted(callers, key=lambda s: s.id):
            lines.append(self._symbol_entry(caller))
            lines.append("")
        return "\n".join(lines)

    def _format_callees(
        self,
        target: SymbolNode,
        callees: list[SymbolNode],
    ) -> str:
        lines = [
            f"Callees of {target.id} ({len(callees)})",
            DIVIDER,
        ]
        for callee in sorted(callees, key=lambda s: s.id):
            lines.append(self._symbol_entry(callee))
            lines.append("")
        return "\n".join(lines)

    def _format_impls(
        self,
        iface: SymbolNode,
        impls: list[SymbolNode],
    ) -> str:
        lines = [
            f"Implementations of {iface.id} ({len(impls)})",
            DIVIDER,
        ]
        for impl in sorted(impls, key=lambda s: s.id):
            lines.append(self._symbol_entry(impl))
            lines.append("")
        return "\n".join(lines)

    def _symbol_entry(self, sym: SymbolNode) -> str:
        """单个符号的多行格式化条目。"""
        lines = [sym.id]
        lines.append(f"  File: {sym.file}:{sym.line}")
        lines.append(
            f"  Kind: {sym.kind.value.upper()} | Lang: {sym.language.value.upper()} "
            f"| Visibility: {sym.visibility}"
        )
        if sym.signature:
            lines.append(f"  Sig:  {sym.signature}")
        return "\n".join(lines)

    # ── 工具方法 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将符号名/路径转换为文件系统安全的文件名。"""
        # 替换路径分隔符和其他特殊字符
        return (
            name
            .replace("/", "__")
            .replace("\\", "__")
            .replace(":", "_")
            .replace("*", "_star_")
            .replace("?", "_q_")
            .replace("<", "_lt_")
            .replace(">", "_gt_")
            .replace('"', "_")
            .replace("|", "_")
        )
