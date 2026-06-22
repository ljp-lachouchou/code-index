"""
ObjCParser — Objective-C 文件解析器

基于 tree-sitter-objc (mattmassicotte/tree-sitter-objc) grammar，
提取符号（@interface/@implementation/方法/Protocol）和调用关系。

iOS/macOS ObjC 项目适用，同时支持 .m / .h / .mm 文件。
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


class ObjCParser(BaseParser):
    """Objective-C 语言解析器。

    全限定 ID 策略：
      - 类/Protocol：ClassName
      - 实例方法：ClassName.-methodName
      - 类方法：ClassName.+methodName
      - 无包/模块概念，用类名前缀（首个大写字母序列）作为模块近似
    """

    @property
    def language_name(self) -> str:
        return "objc"

    @property
    def extensions(self) -> list[str]:
        return ["m", "mm", "h"]

    @property
    def lang_enum(self) -> Lang:
        return Lang.OBJC

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
        if name_node is None:
            return None

        raw_name = self.text_of(name_node, source).strip()
        if not raw_name:
            return None

        # ObjC 方法选择器可能包含冒号：initWithFrame:style:
        # 规范化：去掉末尾多余空白
        name = raw_name

        # ── 推导模块前缀（ObjC 惯例：类名大写字母前缀，如 NS / UI / RN）──────
        module = self._infer_prefix(name)

        # ── 构建全限定 ID ────────────────────────────────────────────────────
        if parent_context:
            # 区分实例方法（-）和类方法（+）
            method_prefix = self._method_prefix(node_type)
            qualified_id = f"{parent_context.id}.{method_prefix}{name}"
        else:
            qualified_id = name  # 顶层类/Protocol 直接用类名

        # ── 位置信息 ─────────────────────────────────────────────────────────
        start = anchor.start_point
        end = anchor.end_point

        # ── 可见性（ObjC 无关键字可见性，但 .h 文件通常是公开声明）───────────
        visibility = "public" if file_path.endswith(".h") else "internal"

        # ── 签名 ─────────────────────────────────────────────────────────────
        signature = self._build_signature(anchor, name, kind, node_type, source)

        return SymbolNode(
            id=qualified_id,
            name=name,
            kind=kind,
            language=Lang.OBJC,
            file=file_path,
            line=start[0] + 1,
            column=start[1],
            end_line=end[0] + 1,
            visibility=visibility,
            is_abstract=False,
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

        callee_name = self.text_of(callee_node, source).strip()

        if self._should_skip_callee(callee_name):
            return None

        caller_id = current_scope.id if current_scope else ""
        if not caller_id:
            return None

        edge_kind = EdgeKind.EXTENDS if is_extends else EdgeKind.CALL

        return CallEdge(
            caller_id=caller_id,
            callee_name=callee_name,
            callee_id="",
            kind=edge_kind,
            file=current_scope.file if current_scope else "",
            line=anchor.start_point[0] + 1,
            resolved=False,
        )

    # ── 私有辅助方法 ─────────────────────────────────────────────────────────

    def _infer_kind(self, node_type: str) -> Optional[SymbolKind]:
        """根据 ObjC 节点类型推断 SymbolKind。"""
        kind_map = {
            # 类声明/实现
            "class_interface":            SymbolKind.CLASS,
            "class_implementation":       SymbolKind.CLASS,
            # 分类
            "category_interface":         SymbolKind.EXTENSION,
            "category_implementation":    SymbolKind.EXTENSION,
            # 协议
            "protocol_declaration":       SymbolKind.PROTOCOL,
            # 方法声明（.h 中）
            "instance_method_declaration": SymbolKind.METHOD,
            "class_method_declaration":    SymbolKind.METHOD,
            # 方法定义（.m 中）
            "instance_method_definition":  SymbolKind.METHOD,
            "class_method_definition":     SymbolKind.METHOD,
        }
        return kind_map.get(node_type)

    def _method_prefix(self, node_type: str) -> str:
        """返回方法前缀：实例方法用 '-'，类方法用 '+'。"""
        if node_type in ("class_method_declaration", "class_method_definition"):
            return "+"
        return "-"

    def _infer_prefix(self, class_name: str) -> str:
        """提取 ObjC 类名前缀作为模块标识。

        例：
          UIViewController → UI
          NSString → NS
          RCTView → RCT
          MyCustomView → My
        """
        m = re.match(r"^([A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*)", class_name)
        if m:
            prefix = m.group(0)
            # 如果只提取到一个字母，不作为前缀
            return prefix if len(prefix) >= 2 else ""
        return ""

    def _build_signature(
        self,
        node,
        name: str,
        kind: SymbolKind,
        node_type: str,
        source: bytes,
    ) -> str:
        """构建可读签名。"""
        if kind == SymbolKind.METHOD:
            prefix = "-" if "instance" in node_type else "+"
            return f"{prefix}({name})"
        if kind == SymbolKind.CLASS:
            return f"@interface {name}" if "interface" in node_type else f"@implementation {name}"
        if kind == SymbolKind.PROTOCOL:
            return f"@protocol {name}"
        if kind == SymbolKind.EXTENSION:
            return f"@interface {name} (Category)"
        return name

    def _should_skip_callee(self, name: str) -> bool:
        """过滤 ObjC 内置/常见方法名。"""
        SKIP = {
            # 基础消息
            "alloc", "init", "new", "copy", "mutableCopy",
            "retain", "release", "autorelease", "dealloc",
            # 通用方法
            "description", "debugDescription", "hash", "isEqual",
            "respondsToSelector", "performSelector",
            "setValue", "valueForKey", "setValue",
            # 字符串
            "stringWithFormat", "initWithFormat",
            # 集合
            "arrayWithObjects", "dictionaryWithObjectsAndKeys",
            "objectAtIndex", "objectForKey", "addObject",
            # NSObject
            "class", "superclass", "isKindOfClass", "isMemberOfClass",
            # 常见 Runtime
            "methodSignatureForSelector", "forwardInvocation",
        }
        if name in SKIP:
            return True
        # 单字母局部变量 / 空字符串
        if len(name) <= 1:
            return True
        return False
