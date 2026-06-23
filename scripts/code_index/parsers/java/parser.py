"""
JavaParser — Java 文件解析器

与 KotlinParser 共享大部分逻辑，只是语法树节点类型不同。
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


class JavaParser(BaseParser):
    """Java 语言解析器。"""

    @property
    def language_name(self) -> str:
        return "java"

    @property
    def extensions(self) -> list[str]:
        return ["java"]

    @property
    def lang_enum(self) -> Lang:
        return Lang.JAVA

    # ── 符号映射 ──────────────────────────────────────────────────────────────

    def _node_to_symbol(
        self,
        captures: dict,
        source: bytes,
        file_path: str,
        parent_context: Optional[SymbolNode],
    ) -> Optional[SymbolNode]:
        anchor = captures.get("symbol")
        if anchor is None:
            return None

        node_type = anchor.type
        name_node = captures.get("name")
        if name_node is None:
            return None

        name = self.text_of(name_node, source)
        kind = self._infer_kind(node_type, anchor, source)
        if kind is None:
            return None

        package = self._extract_package(source)

        if parent_context:
            qualified_id = f"{parent_context.id}.{name}"
        elif package:
            qualified_id = f"{package}.{name}"
        else:
            stem = Path(file_path).stem
            qualified_id = f"{stem}.{name}"

        # Java 可见性从 modifiers 子节点提取
        visibility, is_abstract = self._extract_modifiers(anchor, source)

        # 构建签名
        signature = self._build_signature(name, captures, source, kind)

        start = anchor.start_point
        end = anchor.end_point

        return SymbolNode(
            id=qualified_id,
            name=name,
            kind=kind,
            language=Lang.JAVA,
            file=file_path,
            line=start[0] + 1,
            column=start[1],
            end_line=end[0] + 1,
            visibility=visibility,
            is_abstract=is_abstract,
            signature=signature,
            parent_id=parent_context.id if parent_context else "",
            module=package,
        )

    def _node_to_edge(
        self,
        captures: dict,
        source: bytes,
        current_scope: Optional[SymbolNode],
    ) -> Optional[CallEdge]:
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

    def _infer_kind(self, node_type: str, anchor_node, source: bytes) -> Optional[SymbolKind]:
        kind_map = {
            "class_declaration": SymbolKind.CLASS,
            "interface_declaration": SymbolKind.INTERFACE,
            "enum_declaration": SymbolKind.ENUM,
            "annotation_type_declaration": SymbolKind.INTERFACE,
            "method_declaration": SymbolKind.METHOD,
            "constructor_declaration": SymbolKind.CONSTRUCTOR,
        }
        return kind_map.get(node_type)

    def _extract_package(self, source: bytes) -> str:
        try:
            header = source[:4096].decode("utf-8", errors="replace")
        except Exception:
            return ""
        m = re.search(r"^\s*package\s+([\w.]+)\s*;", header, re.MULTILINE)
        return m.group(1) if m else ""

    def _extract_modifiers(self, anchor_node, source: bytes) -> tuple[str, bool]:
        """从 anchor 节点的 modifiers 子节点提取可见性。"""
        mods_text = ""
        for child in anchor_node.children:
            if child.type == "modifiers":
                mods_text = self.text_of(child, source)
                break

        tokens = set(mods_text.split())
        visibility = "package"  # Java 默认 package-private
        for vis in ("private", "protected", "public"):
            if vis in tokens:
                visibility = vis
                break

        is_abstract = "abstract" in tokens
        return visibility, is_abstract

    def _build_signature(
        self,
        name: str,
        captures: dict,
        source: bytes,
        kind: SymbolKind,
    ) -> str:
        if kind in (SymbolKind.METHOD, SymbolKind.CONSTRUCTOR):
            params_node = captures.get("params")
            return_node = captures.get("return_type")
            params_text = self.text_of(params_node, source) if params_node else "()"
            return_text = f"{self.text_of(return_node, source)} " if return_node else ""
            return f"{return_text}{name}{params_text}"
        if kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
            return f"{kind.value} {name}"
        return name

    def _should_skip_callee(self, name: str) -> bool:
        SKIP = {
            "toString", "equals", "hashCode", "getClass", "notify",
            "notifyAll", "wait", "clone", "finalize",
            "println", "print", "printf", "format",
            "get", "set", "put", "add", "remove", "contains", "size",
            "length", "isEmpty", "isNotEmpty",
        }
        if name in SKIP:
            return True
        if len(name) <= 2 and name[0].islower():
            return True
        return False
