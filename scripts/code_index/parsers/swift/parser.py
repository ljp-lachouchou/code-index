"""
SwiftParser — Swift 文件解析器

基于 tree-sitter-swift (alex-pinkus/tree-sitter-swift) grammar，
提取符号（类/结构体/协议/扩展/函数/枚举等）和调用关系。

iOS/macOS/Swift Package 项目适用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..base import BaseParser
from ...core.model import (
    SymbolNode, CallEdge,
    Language as Lang, SymbolKind, EdgeKind,
)


class SwiftParser(BaseParser):
    """Swift 语言解析器。

    全限定 ID 策略：
      - 模块名 = 文件所在的直接父目录名（粗略近似 Swift 模块）
      - 格式：ModuleName.TypeName.methodName
    """

    @property
    def language_name(self) -> str:
        return "swift"

    @property
    def extensions(self) -> list[str]:
        return ["swift"]

    @property
    def lang_enum(self) -> Lang:
        return Lang.SWIFT

    # ── 符号映射 ──────────────────────────────────────────────────────────────

    def _node_to_symbol(
        self,
        captures: dict,
        source: bytes,
        file_path: str,
        parent_context: Optional[SymbolNode],
    ) -> Optional[SymbolNode]:
        """将 tree-sitter 捕获的节点映射到 SymbolNode。"""
        anchor = captures.get("symbol")
        if anchor is None:
            return None

        node_type = anchor.type
        name_node = captures.get("name")

        # ── 推断符号类型 ──────────────────────────────────────────────────────
        kind = self._infer_kind(node_type)
        if kind is None:
            return None

        # ── 确定短名 ──────────────────────────────────────────────────────────
        if name_node:
            name = self.text_of(name_node, source)
        elif node_type == "init_declaration":
            name = "init"
        else:
            return None  # 无名符号跳过

        # ── 推导模块名（用父目录名近似）────────────────────────────────────────
        module = self._infer_module(file_path)

        # ── 构建全限定 ID ────────────────────────────────────────────────────
        if parent_context:
            qualified_id = f"{parent_context.id}.{name}"
        elif module:
            qualified_id = f"{module}.{name}"
        else:
            stem = Path(file_path).stem
            qualified_id = f"{stem}.{name}"

        # ── 位置信息（tree-sitter 行号 0-based → 1-based）────────────────────
        start = anchor.start_point
        end = anchor.end_point

        # ── 推断可见性 ────────────────────────────────────────────────────────
        visibility = self._infer_visibility(anchor, source)

        # ── 构建签名 ─────────────────────────────────────────────────────────
        signature = self._build_signature(anchor, name, kind, source)

        return SymbolNode(
            id=qualified_id,
            name=name,
            kind=kind,
            language=Lang.SWIFT,
            file=file_path,
            line=start[0] + 1,
            column=start[1],
            end_line=end[0] + 1,
            visibility=visibility,
            is_abstract=False,  # Swift 没有 abstract 关键字
            signature=signature,
            parent_id=parent_context.id if parent_context else "",
            module=module,
        )

    def _node_to_edge(
        self,
        captures: dict,
        source: bytes,
        current_scope: Optional[SymbolNode],
    ) -> Optional[CallEdge]:
        """将 tree-sitter 捕获的节点映射到 CallEdge。"""
        is_extends = "extends" in captures
        anchor = captures.get("call") or captures.get("extends")
        callee_node = captures.get("callee")

        if anchor is None or callee_node is None:
            return None

        callee_name = self.text_of(callee_node, source)

        if self._should_skip_callee(callee_name):
            return None

        caller_id = current_scope.id if current_scope else ""
        if not caller_id:
            return None

        edge_kind = EdgeKind.EXTENDS if is_extends else EdgeKind.CALL

        signature_hint = self._extract_call_signature_hint(captures, source)

        return CallEdge(
            caller_id=caller_id,
            callee_name=callee_name,
            callee_id="",
            kind=edge_kind,
            file=current_scope.file if current_scope else "",
            line=anchor.start_point[0] + 1,
            resolved=False,
            callee_signature_hint=signature_hint,
        )

    # ── 私有辅助方法 ─────────────────────────────────────────────────────────

    def _infer_kind(self, node_type: str) -> Optional[SymbolKind]:
        """根据节点类型推断 SymbolKind。"""
        kind_map = {
            "class_declaration":     SymbolKind.CLASS,
            "struct_declaration":    SymbolKind.CLASS,    # struct 也视为 CLASS
            "protocol_declaration":  SymbolKind.PROTOCOL,
            "actor_declaration":     SymbolKind.CLASS,    # actor 视为 CLASS
            "extension_declaration": SymbolKind.EXTENSION,
            "enum_declaration":      SymbolKind.ENUM,
            "function_declaration":  SymbolKind.FUNCTION,
            "init_declaration":      SymbolKind.CONSTRUCTOR,
            "typealias_declaration": SymbolKind.TYPE_ALIAS,
        }
        return kind_map.get(node_type)

    def _infer_module(self, file_path: str) -> str:
        """用文件的直接父目录名作为模块名（粗略近似）。

        例：Sources/MyApp/Views/ContentView.swift → MyApp
        如果父目录是 Sources/Tests/... 则取第二层目录。
        """
        parts = Path(file_path).parts
        # 找 Sources 或 Tests 后的第一个目录段
        for i, part in enumerate(parts):
            if part.lower() in ("sources", "tests", "src"):
                if i + 1 < len(parts) - 1:
                    return parts[i + 1]
        # 回退：取倒数第二个目录
        if len(parts) >= 2:
            return parts[-2]
        return Path(file_path).stem

    def _infer_visibility(self, node, source: bytes) -> str:
        """从节点前面的修饰符文本中推断可见性。

        tree-sitter-swift 把修饰符（public/private/internal/open/fileprivate）
        作为节点的前驱子节点。这里简单扫描节点文本开头。
        """
        # 取节点前 100 个字节的文本做简单匹配
        snippet = source[max(0, node.start_byte - 80):node.start_byte].decode(
            "utf-8", errors="replace"
        )
        for vis in ("private", "fileprivate", "internal", "open", "public"):
            if re.search(rf"\b{vis}\b", snippet):
                return vis
        return "internal"  # Swift 默认可见性

    def _build_signature(self, node, name: str, kind: SymbolKind, source: bytes) -> str:
        """构建可读签名（简短版本）。"""
        if kind == SymbolKind.FUNCTION:
            # 提取 func 关键字到第一个 { 之前的文本
            raw = self.text_of(node, source)
            brace_idx = raw.find("{")
            if brace_idx > 0:
                sig = raw[:brace_idx].strip()
                # 截断过长的签名
                if len(sig) > 120:
                    sig = sig[:120] + "..."
                return sig
            return f"func {name}()"
        if kind == SymbolKind.CONSTRUCTOR:
            return "init()"
        if kind in (SymbolKind.CLASS, SymbolKind.PROTOCOL, SymbolKind.ENUM,
                    SymbolKind.EXTENSION):
            return f"{kind.value} {name}"
        return name

    def _should_skip_callee(self, name: str) -> bool:
        """过滤 Swift 标准库和常见内置函数。"""
        SKIP = {
            # Swift 标准库
            "print", "debugPrint", "fatalError", "precondition",
            "assert", "assertionFailure", "preconditionFailure",
            # 集合初始化
            "Array", "Dictionary", "Set", "String", "Int", "Double",
            "Float", "Bool", "Optional",
            # 高阶函数（通常是对集合的操作）
            "map", "flatMap", "compactMap", "filter", "reduce",
            "forEach", "sorted", "first", "last", "contains",
            # 字符串格式化
            "format",
            # GCD / 异步
            "async", "await", "Task", "withTaskGroup",
            # SwiftUI/UIKit 基础
            "body", "makeBody", "updateUIView", "makeUIView",
        }
        if name in SKIP:
            return True
        # 单字母局部变量
        if len(name) == 1 and name.islower():
            return True
        return False
