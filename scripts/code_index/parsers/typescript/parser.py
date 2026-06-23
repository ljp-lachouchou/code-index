"""
TypeScriptParser — TypeScript / TSX 文件解析器

基于 tree-sitter-typescript grammar，提取符号和调用关系。
特别针对 React Native 项目做了优化：
  - 识别函数式 React 组件（返回 JSX 的箭头函数）
  - 将 JSX 元素的使用记录为 CALL 边（组件依赖关系）
  - type alias / interface 也作为一等符号提取
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

# React Native 核心组件（首字母大写，出现在 JSX 中直接当作组件引用）
_RN_CORE_COMPONENTS = {
    "View", "Text", "Image", "ScrollView", "FlatList", "SectionList",
    "TextInput", "TouchableOpacity", "TouchableHighlight", "TouchableNativeFeedback",
    "Pressable", "Button", "Switch", "Slider", "ActivityIndicator",
    "Modal", "SafeAreaView", "StatusBar", "KeyboardAvoidingView",
    "StyleSheet", "Platform", "Alert", "Animated",
    # React Navigation
    "Stack", "Tab", "Drawer",
    # 通用 React
    "Fragment", "Suspense",
}


class TypeScriptParser(BaseParser):
    """TypeScript / TSX 语言解析器（React Native 增强）。

    全限定 ID 策略：
      - 模块名 = 文件路径中 src/ 之后的第一个目录段
      - 格式：module.SymbolName
    """

    @property
    def language_name(self) -> str:
        # tree-sitter-typescript 仓库同时包含 typescript 和 tsx grammar。
        # tsx 是 typescript 的超集，包含所有 typescript 节点 + JSX 节点。
        # 使用 tsx 可以统一处理 .ts 和 .tsx 文件。
        return "tsx"

    @property
    def query_dir_name(self) -> str:
        # query 文件仍放在 typescript/ 目录下（tsx 与 typescript 共享 query）
        return "typescript"

    @property
    def extensions(self) -> list[str]:
        return ["ts", "tsx"]

    @property
    def lang_enum(self) -> Lang:
        return Lang.TYPESCRIPT

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

        if name_node is None:
            return None

        name = self.text_of(name_node, source)
        if not name:
            return None

        # ── 推断符号类型 ──────────────────────────────────────────────────────
        kind = self._infer_kind(node_type, name, anchor, source)
        if kind is None:
            return None

        # ── 推导模块名 ───────────────────────────────────────────────────────
        module = self._infer_module(file_path)

        # ── 构建全限定 ID ────────────────────────────────────────────────────
        if parent_context:
            qualified_id = f"{parent_context.id}.{name}"
        elif module:
            qualified_id = f"{module}.{name}"
        else:
            stem = Path(file_path).stem
            qualified_id = f"{stem}.{name}"

        # ── 位置信息 ─────────────────────────────────────────────────────────
        start = anchor.start_point
        end = anchor.end_point

        # ── 可见性（export 关键字检测）────────────────────────────────────────
        visibility = self._infer_visibility(anchor, source)

        # ── 签名 ─────────────────────────────────────────────────────────────
        signature = self._build_signature(anchor, name, kind, source)

        return SymbolNode(
            id=qualified_id,
            name=name,
            kind=kind,
            language=Lang.TYPESCRIPT,
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

        callee_name = self.text_of(callee_node, source)

        if self._should_skip_callee(callee_name):
            return None

        caller_id = current_scope.id if current_scope else ""
        if not caller_id:
            return None

        # 判断边类型
        if is_extends:
            edge_kind = EdgeKind.EXTENDS
        else:
            edge_kind = EdgeKind.CALL

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

    def _infer_kind(
        self,
        node_type: str,
        name: str,
        anchor_node,
        source: bytes,
    ) -> Optional[SymbolKind]:
        """根据节点类型和名称推断 SymbolKind。

        核心逻辑：
        1. 直接类型映射（class/interface/enum/type_alias）
        2. 函数声明：名称首字母大写 → COMPONENT，否则 FUNCTION
        3. 变量声明中的箭头函数：同上判断
        """
        # 直接映射
        simple_map = {
            "class_declaration":      SymbolKind.CLASS,
            "interface_declaration":  SymbolKind.INTERFACE,
            "enum_declaration":       SymbolKind.ENUM,
            "type_alias_declaration": SymbolKind.TYPE_ALIAS,
        }
        if node_type in simple_map:
            return simple_map[node_type]

        # 函数声明
        if node_type == "function_declaration":
            return self._classify_function(name, anchor_node, source)

        # 变量声明中的函数（箭头函数或函数表达式）
        if node_type == "variable_declarator":
            return self._classify_function(name, anchor_node, source)

        return None

    def _classify_function(self, name: str, node, source: bytes) -> SymbolKind:
        """判断一个函数是 React 组件还是普通函数。

        规则：
        1. 名称首字母大写 → COMPONENT
        2. 函数体内包含 JSX 语法（<View> / return ( <）→ COMPONENT
        3. 否则 → FUNCTION
        """
        # 名称首字母大写：React 组件命名惯例
        if name and name[0].isupper():
            return SymbolKind.COMPONENT

        # 检查函数体是否包含 JSX
        body_text = self.text_of(node, source)
        if self._has_jsx(body_text):
            return SymbolKind.COMPONENT

        return SymbolKind.FUNCTION

    def _has_jsx(self, text: str) -> bool:
        """简单检测文本中是否含有 JSX 语法。"""
        # 匹配 <View / <Text / <div / return ( <Component 等
        return bool(re.search(r"<[A-Z][A-Za-z]*[\s/>]|return\s*\(\s*<", text))

    def _infer_module(self, file_path: str) -> str:
        """从文件路径推导模块名。

        例：
          src/screens/HomeScreen.tsx → screens
          src/components/Button.tsx → components
          app/navigation/Navigator.ts → navigation
        """
        parts = Path(file_path).parts
        for i, part in enumerate(parts):
            if part.lower() in ("src", "app", "source", "lib"):
                if i + 1 < len(parts) - 1:
                    return parts[i + 1]
        # 回退：取文件名（不含扩展名）
        return Path(file_path).stem

    def _infer_visibility(self, node, source: bytes) -> str:
        """检测 export / export default 来判断可见性。"""
        snippet = source[max(0, node.start_byte - 60):node.start_byte].decode(
            "utf-8", errors="replace"
        )
        if "export" in snippet:
            return "public"
        return "internal"

    def _build_signature(self, node, name: str, kind: SymbolKind, source: bytes) -> str:
        """构建可读签名。"""
        if kind in (SymbolKind.FUNCTION, SymbolKind.COMPONENT):
            raw = self.text_of(node, source)
            # 找到第一个 { 或 => 之前的文本作为签名
            for marker in ("{", "=>"):
                idx = raw.find(marker)
                if idx > 0:
                    sig = raw[:idx].strip().rstrip("=").strip()
                    if len(sig) > 100:
                        sig = sig[:100] + "..."
                    return sig
            return f"function {name}()"
        if kind == SymbolKind.CLASS:
            return f"class {name}"
        if kind == SymbolKind.INTERFACE:
            return f"interface {name}"
        if kind == SymbolKind.ENUM:
            return f"enum {name}"
        if kind == SymbolKind.TYPE_ALIAS:
            return f"type {name}"
        return name

    def _should_skip_callee(self, name: str) -> bool:
        """过滤 TS/JS 内置和 React Native 核心组件引用。"""
        SKIP = {
            # JS 内置
            "console", "JSON", "Math", "Object", "Array", "Promise",
            "setTimeout", "setInterval", "clearTimeout", "clearInterval",
            "parseInt", "parseFloat", "isNaN", "isFinite",
            # React 基础
            "useState", "useEffect", "useCallback", "useMemo", "useRef",
            "useContext", "useReducer", "useLayoutEffect", "useImperativeHandle",
            "createContext", "forwardRef", "memo", "lazy",
            "createElement", "cloneElement", "Children",
            # 通用工具
            "require", "resolve", "reject", "then", "catch", "finally",
            "toString", "valueOf", "hasOwnProperty",
        }
        if name in SKIP:
            return True
        # React Native 核心组件：它们不是用户定义的，不追踪
        if name in _RN_CORE_COMPONENTS:
            return True
        # 单/双字母变量
        if len(name) <= 2 and name[0].islower():
            return True
        return False
