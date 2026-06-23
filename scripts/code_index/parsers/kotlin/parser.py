"""
KotlinParser — Kotlin/KTS 文件解析器

基于 tree-sitter-kotlin grammar，
提取符号（类/接口/函数/object/enum 等）和调用关系。
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


class KotlinParser(BaseParser):
    """Kotlin/KTS 语言解析器。"""

    @property
    def language_name(self) -> str:
        return "kotlin"

    @property
    def extensions(self) -> list[str]:
        return ["kt", "kts"]

    @property
    def lang_enum(self) -> Lang:
        return Lang.KOTLIN

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
        kind = self._infer_kind(node_type, captures, source)
        if kind is None:
            return None

        # ── 确定短名 ──────────────────────────────────────────────────────────
        if name_node:
            name = self.text_of(name_node, source)
        elif node_type == "companion_object":
            name = "Companion"
        else:
            return None  # 无名符号跳过

        # ── 提取包名（用于构建全限定 ID）────────────────────────────────────
        package = self._extract_package(source)

        # ── 构建全限定 ID ────────────────────────────────────────────────────
        if parent_context:
            qualified_id = f"{parent_context.id}.{name}"
        elif package:
            qualified_id = f"{package}.{name}"
        else:
            # 回退：用文件路径推导（去掉 .kt 后缀，路径分隔符替换为点）
            stem = Path(file_path).stem
            qualified_id = f"{stem}.{name}"

        # ── 提取修饰符 ───────────────────────────────────────────────────────
        modifiers_node = captures.get("modifiers")
        visibility, is_abstract = self._extract_modifiers(modifiers_node, source)

        # ── 构建签名 ─────────────────────────────────────────────────────────
        signature = self._build_signature(anchor, name, captures, source, kind)

        # ── 位置信息（tree-sitter 行号 0-based → 1-based）────────────────────
        start = anchor.start_point  # (row, col)
        end = anchor.end_point

        return SymbolNode(
            id=qualified_id,
            name=name,
            kind=kind,
            language=Lang.KOTLIN,
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
        """将 tree-sitter 捕获的节点映射到 CallEdge。"""
        # 确定锚点：call 或 extends
        is_extends = "extends" in captures
        anchor = captures.get("call") or captures.get("extends")
        callee_node = captures.get("callee")

        if anchor is None or callee_node is None:
            return None

        callee_name = self.text_of(callee_node, source)

        # 过滤掉常见的非用户符号（关键字、标准库等）
        if self._should_skip_callee(callee_name):
            return None

        # 如果没有所在作用域，仍然记录（caller_id 为空）
        caller_id = current_scope.id if current_scope else ""
        if not caller_id:
            return None  # 无法确定调用者，跳过

        edge_kind = EdgeKind.EXTENDS if is_extends else EdgeKind.CALL

        # 提取调用点的参数个数作为签名提示（用于支持方法重载解析）
        callee_signature_hint = self._extract_call_signature_hint(captures, source)

        return CallEdge(
            caller_id=caller_id,
            callee_name=callee_name,
            callee_id="",       # 待 Resolver 阶段填入
            kind=edge_kind,
            file=current_scope.file if current_scope else "",
            line=anchor.start_point[0] + 1,
            resolved=False,
            callee_signature_hint=callee_signature_hint,
        )

    def _extract_call_signature_hint(
        self,
        captures: dict,
        source: bytes,
    ) -> str:
        """从调用表达式中提取参数个数作为签名提示。

        返回参数个数的字符串形式（如 "2"），用于 Resolver 区分重载方法。
        """
        # 尝试获取 arguments 节点（tree-sitter 中 call_expression 的 arguments）
        args_node = captures.get("arguments")
        if args_node is None:
            return ""

        # 统计参数个数（简单统计逗号分隔的子节点）
        args_text = self.text_of(args_node, source)
        if not args_text or args_text == "()":
            return "0"

        # 去除括号
        inner = args_text.strip()
        if inner.startswith("("):
            inner = inner[1:]
        if inner.endswith(")"):
            inner = inner[:-1]

        inner = inner.strip()
        if not inner:
            return "0"

        # 按逗号分割，但要处理嵌套情况（如 lambda、函数调用等）
        # 简单处理：按顶层逗号分割
        count = 1
        depth = 0
        for char in inner:
            if char in "({[<":
                depth += 1
            elif char in ")}]>":
                depth -= 1
            elif char == "," and depth == 0:
                count += 1

        return str(count)

    # ── 私有辅助方法 ─────────────────────────────────────────────────────────

    def _infer_kind(self, node_type: str, captures: dict, source: bytes) -> Optional[SymbolKind]:
        """根据 tree-sitter 节点类型推断 SymbolKind。"""
        kind_map = {
            "class_declaration": SymbolKind.CLASS,
            "interface_declaration": SymbolKind.INTERFACE,
            "object_declaration": SymbolKind.OBJECT,
            "companion_object": SymbolKind.COMPANION,
            "function_declaration": SymbolKind.FUNCTION,
            "enum_class": SymbolKind.ENUM,
            "enum_entry": SymbolKind.ENUM_ENTRY,
            "type_alias": SymbolKind.TYPE_ALIAS,
        }

        kind = kind_map.get(node_type)
        if kind is None:
            return None

        # 通过修饰符进一步区分 METHOD（类内函数）vs FUNCTION（顶层）
        if kind == SymbolKind.FUNCTION:
            modifiers_node = captures.get("modifiers")
            if modifiers_node:
                mods_text = self.text_of(modifiers_node, source)
                if "override" in mods_text:
                    kind = SymbolKind.METHOD

        return kind

    def _extract_package(self, source: bytes) -> str:
        """从文件开头提取 package 声明（最多扫描前 50 行）。"""
        try:
            header = source[:4096].decode("utf-8", errors="replace")
        except Exception:
            return ""

        # 简单正则匹配 package 声明
        m = re.search(r"^\s*package\s+([\w.]+)", header, re.MULTILINE)
        return m.group(1) if m else ""

    def _extract_modifiers(
        self,
        modifiers_node,
        source: bytes,
    ) -> tuple[str, bool]:
        """从 modifiers 节点提取可见性和是否抽象。"""
        if modifiers_node is None:
            return "public", False

        mods_text = self.text_of(modifiers_node, source)
        tokens = set(mods_text.split())

        visibility = "public"
        for vis in ("private", "protected", "internal", "open"):
            if vis in tokens:
                visibility = vis
                break

        is_abstract = "abstract" in tokens

        return visibility, is_abstract

    def _build_signature(
        self,
        anchor_node,
        name: str,
        captures: dict,
        source: bytes,
        kind: SymbolKind,
    ) -> str:
        """构建符号的可读签名字符串。"""
        if kind == SymbolKind.FUNCTION or kind == SymbolKind.METHOD:
            params_node = captures.get("params")
            return_node = captures.get("return_type")

            params_text = ""
            if params_node:
                params_text = self.text_of(params_node, source)

            return_text = ""
            if return_node:
                return_text = f": {self.text_of(return_node, source)}"

            return f"fun {name}{params_text}{return_text}"

        if kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
            return f"{kind.value} {name}"

        return name

    def _should_skip_callee(self, name: str) -> bool:
        """过滤不需要跟踪的被调用者（Kotlin 内置/标准库）。"""
        SKIP = {
            # Kotlin 内置函数
            "let", "run", "apply", "also", "with", "takeIf", "takeUnless",
            "println", "print", "TODO", "error", "check", "require",
            "arrayOf", "listOf", "mutableListOf", "mapOf", "mutableMapOf",
            "setOf", "mutableSetOf", "emptyList", "emptyMap",
            # 常见操作符函数
            "invoke", "get", "set", "equals", "hashCode", "toString",
            "compareTo", "plus", "minus", "times", "div", "rem",
            # 协程
            "launch", "async", "withContext", "delay", "collect", "emit",
            # 测试
            "assertEquals", "assertTrue", "assertFalse", "assertNull",
        }
        if name in SKIP:
            return True
        # 以小写开头且长度 <= 2 的通常是局部变量
        if len(name) <= 2 and name[0].islower():
            return True
        return False
