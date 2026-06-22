"""
QueryEngine — 符号查询引擎

支持四种查询模式：
- 精确：    "deleteComment"       → 精确短名匹配
- 前缀：    "delete*"             → 前缀匹配（Trie 思路）
- 通配：    "*Comment"、"del?te"  → fnmatch 匹配
- 全限定：  ".v2.CommentVO"       → qualified name 后缀匹配
"""

from __future__ import annotations

import fnmatch
from typing import Optional

from .model import IndexGraph, SymbolNode, SymbolKind, Language


class QueryEngine:
    """基于 IndexGraph 的符号查询引擎。"""

    def __init__(self, graph: IndexGraph):
        self.graph = graph

    # ── 主查询接口 ────────────────────────────────────────────────────────────

    def find(
        self,
        pattern: str,
        kind: Optional[str] = None,          # SymbolKind.value 或 None
        language: Optional[str] = None,      # Language.value 或 None
        limit: int = 50,
    ) -> list[SymbolNode]:
        """统一查询入口，自动识别查询模式。

        Args:
            pattern:  查询模式（精确/前缀/通配/全限定）
            kind:     过滤符号类型，如 "class" / "method"
            language: 过滤语言，如 "kotlin" / "java"
            limit:    返回结果上限

        Returns:
            匹配的 SymbolNode 列表（按名称排序）
        """
        if not pattern:
            return []

        # 自动识别查询模式
        if pattern.startswith("."):
            # 全限定名后缀匹配：".v2.CommentVO"
            results = self._qualified_suffix_search(pattern[1:])
        elif "*" in pattern or "?" in pattern:
            # 通配符匹配
            results = self._glob_search(pattern)
        elif pattern in self.graph._by_name:
            # 精确短名匹配（优先，最快）
            results = self.graph.find_by_name(pattern)
        else:
            # 前缀匹配（找不到精确匹配时的回退）
            results = self._prefix_search(pattern)

        # 后置过滤
        if kind:
            try:
                kind_enum = SymbolKind(kind)
                results = [r for r in results if r.kind == kind_enum]
            except ValueError:
                pass  # 无效的 kind 值，忽略过滤

        if language:
            try:
                lang_enum = Language(language)
                results = [r for r in results if r.language == lang_enum]
            except ValueError:
                pass

        return sorted(results, key=lambda s: (s.name, s.id))[:limit]

    # ── 调用关系查询 ──────────────────────────────────────────────────────────

    def find_callers(
        self,
        symbol_id: str,
        limit: int = 100,
    ) -> list[SymbolNode]:
        """查找调用了目标符号（by ID）的所有调用者 SymbolNode 列表。"""
        caller_ids = self.graph.callers_of(symbol_id)
        results = []
        for cid in caller_ids:
            caller = self.graph.symbols.get(cid)
            if caller:
                results.append(caller)
        return results[:limit]

    def find_callees(
        self,
        symbol_id: str,
        limit: int = 100,
    ) -> list[SymbolNode]:
        """查找目标符号（by ID）调用的所有被调用者 SymbolNode 列表（已解析的）。"""
        callee_ids = self.graph.callees_of(symbol_id)
        results = []
        for cid in callee_ids:
            callee = self.graph.symbols.get(cid)
            if callee:
                results.append(callee)
        return results[:limit]

    def find_implementations(
        self,
        symbol_id: str,
        limit: int = 100,
    ) -> list[SymbolNode]:
        """查找接口/抽象类（by ID）的所有实现/子类 SymbolNode 列表。"""
        impl_ids = self.graph.impls_of(symbol_id)
        results = []
        for iid in impl_ids:
            impl = self.graph.symbols.get(iid)
            if impl:
                results.append(impl)
        return results[:limit]

    def file_outline(self, file_path: str) -> list[SymbolNode]:
        """返回文件的符号大纲（按行号排序）。"""
        # 支持相对路径和部分路径匹配
        if file_path in self.graph._by_file:
            return self.graph.symbols_in_file(file_path)

        # 模糊路径匹配：file_path 是路径的后缀部分
        for known_path in self.graph._by_file:
            if known_path.endswith(file_path) or known_path == file_path:
                return self.graph.symbols_in_file(known_path)

        # fnmatch 路径匹配
        matches = [
            p for p in self.graph._by_file
            if fnmatch.fnmatch(p, f"*{file_path}*")
        ]
        if matches:
            return self.graph.symbols_in_file(matches[0])

        return []

    # ── 内部搜索策略 ─────────────────────────────────────────────────────────

    def _prefix_search(self, prefix: str) -> list[SymbolNode]:
        """前缀匹配：返回所有 name 以 prefix 开头的符号。"""
        results = []
        prefix_lower = prefix.lower()
        for name, ids in self.graph._by_name.items():
            if name.lower().startswith(prefix_lower):
                results.extend(
                    self.graph.symbols[i] for i in ids if i in self.graph.symbols
                )
        return results

    def _glob_search(self, pattern: str) -> list[SymbolNode]:
        """通配符匹配（fnmatch）：支持 * 和 ?。"""
        results = []
        pattern_lower = pattern.lower()
        for name, ids in self.graph._by_name.items():
            if fnmatch.fnmatch(name.lower(), pattern_lower):
                results.extend(
                    self.graph.symbols[i] for i in ids if i in self.graph.symbols
                )
        return results

    def _qualified_suffix_search(self, suffix: str) -> list[SymbolNode]:
        """全限定名后缀匹配：".v2.CommentVO" 匹配任何以 v2.CommentVO 结尾的 ID。"""
        results = []
        suffix_lower = suffix.lower()
        for sym_id, sym in self.graph.symbols.items():
            if sym_id.lower().endswith(suffix_lower):
                results.append(sym)
        return results

    # ── 格式化输出（供 CLI 直接使用）─────────────────────────────────────────

    def format_symbols_text(
        self,
        symbols: list[SymbolNode],
        show_signature: bool = True,
    ) -> str:
        """将符号列表格式化为人类可读文本。"""
        if not symbols:
            return "(no results)"

        lines = []
        for sym in symbols:
            lines.append(f"{sym.id}")
            lines.append(f"  File: {sym.file}:{sym.line}")
            kind_str = sym.kind.value.upper()
            lang_str = sym.language.value.upper()
            lines.append(f"  Kind: {kind_str} | Lang: {lang_str} | Vis: {sym.visibility}")
            if show_signature and sym.signature:
                lines.append(f"  Sig:  {sym.signature}")
            lines.append("")
        return "\n".join(lines)

    def format_callers_text(
        self,
        symbols: list[SymbolNode],
    ) -> str:
        """格式化调用者/被调用者符号列表。"""
        if not symbols:
            return "(none)"

        lines = []
        for sym in symbols:
            kind_str = sym.kind.value.upper()
            lines.append(f"[{kind_str}] {sym.id}")
            lines.append(f"  File: {sym.file}:{sym.line}")
            if sym.signature:
                lines.append(f"  Sig:  {sym.signature}")
            lines.append("")
        return "\n".join(lines)

    def format_impls_text(
        self,
        symbols: list[SymbolNode],
    ) -> str:
        """格式化实现类列表。"""
        if not symbols:
            return "(no implementations found)"

        lines = []
        for sym in symbols:
            kind_str = sym.kind.value.upper()
            lines.append(f"[{kind_str}] {sym.id}")
            lines.append(f"  File: {sym.file}:{sym.line}")
            lines.append("")
        return "\n".join(lines)

    def format_outline_text(
        self,
        symbols: list[SymbolNode],
    ) -> str:
        """格式化文件大纲（带层级缩进）。"""
        if not symbols:
            return "(no symbols)"

        lines = []
        # 建立 id → symbol 映射（用于确定是否是顶层符号）
        sym_ids = {s.id for s in symbols}

        for sym in symbols:
            # 如果有 parent_id 且 parent 在当前文件内，缩进显示
            indent = "    " if (sym.parent_id and sym.parent_id in sym_ids) else ""
            kind_str = sym.kind.value
            loc = f"L{sym.line}"
            if sym.signature:
                lines.append(f"{indent}{loc:>6}  [{kind_str}] {sym.signature}")
            else:
                lines.append(f"{indent}{loc:>6}  [{kind_str}] {sym.name}")
        return "\n".join(lines)
