"""
CodeIndex 核心数据模型

SymbolNode  — 代码中的符号（类/函数/方法/属性等）
CallEdge    — 符号之间的调用/继承/实现关系
IndexGraph  — 整个项目的符号图（含反向索引）
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# 枚举定义
# ─────────────────────────────────────────────────────────────────────────────

class Language(str, Enum):
    KOTLIN = "kotlin"
    JAVA = "java"
    SWIFT = "swift"
    OBJC = "objc"
    TYPESCRIPT = "typescript"


class SymbolKind(str, Enum):
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    OBJECT = "object"          # Kotlin object / singleton
    ENUM = "enum"
    ENUM_ENTRY = "enum_entry"
    PROTOCOL = "protocol"      # Swift protocol
    EXTENSION = "extension"    # Kotlin/Swift extension
    COMPONENT = "component"    # React Native functional component
    CONSTRUCTOR = "constructor"
    COMPANION = "companion"    # Kotlin companion object
    TYPE_ALIAS = "type_alias"  # Kotlin typealias / TS type


class EdgeKind(str, Enum):
    CALL = "call"               # 函数/方法调用
    EXTENDS = "extends"         # 类继承
    IMPLEMENTS = "implements"   # 接口实现
    OVERRIDES = "overrides"     # 方法重写
    USES = "uses"               # 属性/变量使用
    CONSTRUCTS = "constructs"   # 构造函数调用
    IMPORT = "import"           # import 依赖


# ─────────────────────────────────────────────────────────────────────────────
# SymbolNode
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SymbolNode:
    """代码中的一个符号（类、函数、方法、属性等）。

    id 是全限定名，作为全局唯一主键。
    name 是短名，用于模糊/前缀查询。
    """

    # ── 唯一标识 ────────────────────────────────────────────────────────────
    id: str               # 全限定名（唯一主键）
    name: str             # 短名（用于模糊查询）

    # ── 分类 ────────────────────────────────────────────────────────────────
    kind: SymbolKind
    language: Language

    # ── 位置 ────────────────────────────────────────────────────────────────
    file: str             # 相对仓库根的路径
    line: int             # 起始行（1-based）
    column: int           # 起始列（0-based）
    end_line: int         # 结束行（1-based）

    # ── 元数据 ──────────────────────────────────────────────────────────────
    visibility: str = "public"      # public | private | internal | open | protected
    is_abstract: bool = False
    signature: str = ""             # 完整签名，如 "fun deleteComment(id: String): Unit"
    parent_id: str = ""             # 所属类的 ID（方法/属性的容器类）
    module: str = ""                # 所属包/模块名

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["language"] = self.language.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolNode":
        d = dict(d)
        d["kind"] = SymbolKind(d["kind"])
        d["language"] = Language(d["language"])
        return cls(**d)

    def location_str(self) -> str:
        """返回人类可读的位置字符串，如 'src/Foo.kt:42'"""
        return f"{self.file}:{self.line}"

    def summary_line(self) -> str:
        """返回单行摘要，用于 VFS 文件和 CLI 输出"""
        vis = f"{self.visibility} " if self.visibility != "public" else ""
        parent = f" (in {self.parent_id.split('.')[-1]})" if self.parent_id else ""
        return (
            f"{vis}{self.kind.value.upper()} {self.id}{parent}\n"
            f"  File: {self.file}:{self.line}\n"
            f"  Lang: {self.language.value.upper()}"
            + (f" | Sig: {self.signature}" if self.signature else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# CallEdge
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CallEdge:
    """两个符号之间的关系边（调用、继承、实现等）。"""

    caller_id: str        # 调用者符号 ID
    callee_name: str      # 被调用者短名（解析前的原始名称）
    file: str             # 调用发生的文件
    line: int             # 调用发生的行号
    kind: EdgeKind = EdgeKind.CALL

    callee_id: str = ""   # 被调用者 ID（跨文件解析后填入，可为空）
    resolved: bool = False  # callee_id 是否已解析到确定符号

    # 调用点的参数签名提示（如参数个数），用于支持方法重载的精确匹配
    callee_signature_hint: str = ""

    # id 由 caller_id + callee_name + file + line 的 hash 生成
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            raw = f"{self.caller_id}:{self.callee_name}:{self.file}:{self.line}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CallEdge":
        d = dict(d)
        d["kind"] = EdgeKind(d["kind"])
        # 兼容旧数据：callee_signature_hint 可能不存在
        if "callee_signature_hint" not in d:
            d["callee_signature_hint"] = ""
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# IndexStats
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IndexStats:
    total_files: int = 0
    total_symbols: int = 0
    total_edges: int = 0
    resolved_edges: int = 0
    elapsed_seconds: float = 0.0
    files_by_lang: dict = field(default_factory=dict)
    symbols_by_lang: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "IndexStats":
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# IndexGraph
# ─────────────────────────────────────────────────────────────────────────────

class IndexGraph:
    """整个项目的符号图。

    主数据：
      symbols: dict[str, SymbolNode]  — id → node
      edges:   list[CallEdge]

    反向索引（内存中维护，用于快速查询）：
      _callers: callee_id  → [caller_id]
      _callees: caller_id  → [callee_id]
      _by_name: name       → [id]（同名符号）
      _by_file: file       → [id]
      _by_kind: kind       → [id]
      _impls:   iface_id   → [impl_id]  （实现关系）
    """

    def __init__(
        self,
        version: str = "1.0",
        project: str = "",
        indexed_at: str = "",
        root_path: str = "",
        stats: Optional[IndexStats] = None,
    ):
        self.version = version
        self.project = project
        self.indexed_at = indexed_at
        self.root_path = root_path
        self.stats: IndexStats = stats or IndexStats()

        # 主数据
        self.symbols: dict[str, SymbolNode] = {}
        self.edges: list[CallEdge] = []

        # 反向索引
        self._callers: dict[str, list[str]] = {}   # callee_id → [caller_id]
        self._callees: dict[str, list[str]] = {}   # caller_id → [callee_id]
        self._by_name: dict[str, list[str]] = {}   # name → [id]
        self._by_file: dict[str, list[str]] = {}   # file → [id]
        self._by_kind: dict[str, list[str]] = {}   # kind.value → [id]
        self._impls: dict[str, list[str]] = {}     # iface_id → [impl_id]

    # ── 数据添加 ─────────────────────────────────────────────────────────────

    def add_symbol(self, sym: SymbolNode) -> None:
        """添加符号并更新所有反向索引。"""
        self.symbols[sym.id] = sym

        # by_name
        self._by_name.setdefault(sym.name, [])
        if sym.id not in self._by_name[sym.name]:
            self._by_name[sym.name].append(sym.id)

        # by_file
        self._by_file.setdefault(sym.file, [])
        if sym.id not in self._by_file[sym.file]:
            self._by_file[sym.file].append(sym.id)

        # by_kind
        kind_key = sym.kind.value
        self._by_kind.setdefault(kind_key, [])
        if sym.id not in self._by_kind[kind_key]:
            self._by_kind[kind_key].append(sym.id)

    def add_edge(self, edge: CallEdge) -> None:
        """添加边并更新调用图反向索引。"""
        self.edges.append(edge)

        # 调用图（正向：caller → callee）
        self._callees.setdefault(edge.caller_id, [])
        if edge.callee_id and edge.callee_id not in self._callees[edge.caller_id]:
            self._callees[edge.caller_id].append(edge.callee_id)

        # 调用图（反向：callee → caller）
        if edge.callee_id:
            self._callers.setdefault(edge.callee_id, [])
            if edge.caller_id not in self._callers[edge.callee_id]:
                self._callers[edge.callee_id].append(edge.caller_id)

        # 实现关系
        if edge.kind in (EdgeKind.IMPLEMENTS, EdgeKind.EXTENDS):
            if edge.callee_id:
                self._impls.setdefault(edge.callee_id, [])
                if edge.caller_id not in self._impls[edge.callee_id]:
                    self._impls[edge.callee_id].append(edge.caller_id)

    def remove_file(self, file_path: str) -> None:
        """从索引中移除某个文件的所有符号和边（增量更新时使用）。"""
        sym_ids = self._by_file.pop(file_path, [])
        for sid in sym_ids:
            sym = self.symbols.pop(sid, None)
            if sym is None:
                continue
            # 清理 by_name
            if sym.name in self._by_name:
                try:
                    self._by_name[sym.name].remove(sid)
                except ValueError:
                    pass
            # 清理 by_kind
            kind_key = sym.kind.value
            if kind_key in self._by_kind:
                try:
                    self._by_kind[kind_key].remove(sid)
                except ValueError:
                    pass

        # 清理 edges（含 callee/caller 反向索引）
        surviving_edges = []
        for edge in self.edges:
            if edge.file == file_path or edge.caller_id in sym_ids:
                # 清理反向索引
                if edge.callee_id and edge.callee_id in self._callers:
                    try:
                        self._callers[edge.callee_id].remove(edge.caller_id)
                    except ValueError:
                        pass
                if edge.caller_id in self._callees:
                    self._callees.pop(edge.caller_id, None)
            else:
                surviving_edges.append(edge)
        self.edges = surviving_edges

    # ── 查询方法 ─────────────────────────────────────────────────────────────

    def callers_of(self, symbol_id: str) -> list[str]:
        """返回所有调用了 symbol_id 的 caller_id 列表。"""
        return list(self._callers.get(symbol_id, []))

    def callees_of(self, symbol_id: str) -> list[str]:
        """返回 symbol_id 调用的所有 callee_id 列表。"""
        return list(self._callees.get(symbol_id, []))

    def impls_of(self, symbol_id: str) -> list[str]:
        """返回接口/抽象类 symbol_id 的所有实现/子类 ID 列表。"""
        return list(self._impls.get(symbol_id, []))

    def symbols_in_file(self, file_path: str) -> list[SymbolNode]:
        """返回文件中所有符号，按行号排序。"""
        ids = self._by_file.get(file_path, [])
        syms = [self.symbols[i] for i in ids if i in self.symbols]
        return sorted(syms, key=lambda s: s.line)

    def symbols_by_kind(self, kind: SymbolKind) -> list[SymbolNode]:
        """返回指定类型的所有符号。"""
        ids = self._by_kind.get(kind.value, [])
        return [self.symbols[i] for i in ids if i in self.symbols]

    def find_by_name(self, name: str) -> list[SymbolNode]:
        """精确短名匹配。"""
        ids = self._by_name.get(name, [])
        return [self.symbols[i] for i in ids if i in self.symbols]

    # ── 序列化 ───────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "project": self.project,
            "indexed_at": self.indexed_at,
            "root_path": self.root_path,
            "stats": self.stats.to_dict(),
            "symbols": {k: v.to_dict() for k, v in self.symbols.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    def save(self, path: Path) -> None:
        """将图序列化为 JSON 文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "IndexGraph":
        """从字典构建图（含重建反向索引）。"""
        graph = cls(
            version=data.get("version", "1.0"),
            project=data.get("project", ""),
            indexed_at=data.get("indexed_at", ""),
            root_path=data.get("root_path", ""),
            stats=IndexStats.from_dict(data.get("stats", {})),
        )

        # 加载符号（同时重建反向索引）
        symbols_data = data.get("symbols", {})
        if isinstance(symbols_data, dict):
            for sym_dict in symbols_data.values():
                graph.add_symbol(SymbolNode.from_dict(sym_dict))
        else:
            for sym_dict in symbols_data:
                graph.add_symbol(SymbolNode.from_dict(sym_dict))

        # 加载边（同时重建调用图）
        for edge_dict in data.get("edges", []):
            graph.add_edge(CallEdge.from_dict(edge_dict))

        return graph

    @classmethod
    def load(cls, path: Path) -> "IndexGraph":
        """从 JSON 文件加载图（含重建反向索引）。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def rebuild_indexes(self) -> None:
        """从已有的 symbols / edges 重建所有反向索引（用于合并后修复）。"""
        self._callers.clear()
        self._callees.clear()
        self._by_name.clear()
        self._by_file.clear()
        self._by_kind.clear()
        self._impls.clear()

        for sym in self.symbols.values():
            # 直接操作，避免重复 add_symbol 逻辑
            self._by_name.setdefault(sym.name, [])
            if sym.id not in self._by_name[sym.name]:
                self._by_name[sym.name].append(sym.id)
            self._by_file.setdefault(sym.file, [])
            if sym.id not in self._by_file[sym.file]:
                self._by_file[sym.file].append(sym.id)
            kind_key = sym.kind.value
            self._by_kind.setdefault(kind_key, [])
            if sym.id not in self._by_kind[kind_key]:
                self._by_kind[kind_key].append(sym.id)

        for edge in self.edges:
            if edge.callee_id:
                self._callees.setdefault(edge.caller_id, [])
                if edge.callee_id not in self._callees[edge.caller_id]:
                    self._callees[edge.caller_id].append(edge.callee_id)
                self._callers.setdefault(edge.callee_id, [])
                if edge.caller_id not in self._callers[edge.callee_id]:
                    self._callers[edge.callee_id].append(edge.caller_id)
            if edge.kind in (EdgeKind.IMPLEMENTS, EdgeKind.EXTENDS) and edge.callee_id:
                self._impls.setdefault(edge.callee_id, [])
                if edge.caller_id not in self._impls[edge.callee_id]:
                    self._impls[edge.callee_id].append(edge.caller_id)

    def __repr__(self) -> str:
        return (
            f"IndexGraph(project={self.project!r}, "
            f"symbols={len(self.symbols)}, "
            f"edges={len(self.edges)})"
        )
