"""
BaseParser — 所有语言解析器的公共抽象接口

## 扩展新语言的步骤
1. 继承 BaseParser
2. 实现 language_name / extensions / lang_enum 属性
3. 编写 parsers/<lang>/queries/symbols.scm 和 calls.scm
4. 实现 _node_to_symbol() 和 _node_to_edge()
5. 在 parsers/registry.py 中注册

通用流程由基类完成：
  读文件 → tree-sitter parse → 执行 query → 映射节点
"""

from __future__ import annotations

import bisect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..core.model import SymbolNode, CallEdge, Language as Lang, SymbolKind


class ScopeIndex:
    """根据行号快速定位当前所在的符号作用域（最小包含作用域）。

    用于 _run_call_query 中确定调用发生在哪个函数/方法内部（caller）。
    """

    def __init__(self, symbols: list[SymbolNode]):
        # 只保留有意义的"容器"符号（类、函数、方法）
        self._scopes: list[SymbolNode] = sorted(
            [
                s for s in symbols
                if s.kind in (
                    SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.FUNCTION,
                    SymbolKind.METHOD, SymbolKind.OBJECT, SymbolKind.COMPONENT,
                    SymbolKind.COMPANION, SymbolKind.EXTENSION,
                )
            ],
            key=lambda s: (s.line, s.end_line),
        )
        self._start_lines = [s.line for s in self._scopes]

    def find_scope(self, row: int) -> Optional[SymbolNode]:
        """找到包含 row 行（0-based）的最小符号作用域。"""
        line_1based = row + 1  # tree-sitter 行号是 0-based，SymbolNode 用 1-based

        # 找到所有 start_line <= line_1based 的候选
        idx = bisect.bisect_right(self._start_lines, line_1based) - 1
        best: Optional[SymbolNode] = None

        # 从后向前，找 end_line >= line_1based 且 span 最小的
        for i in range(idx, -1, -1):
            scope = self._scopes[i]
            if scope.line <= line_1based <= scope.end_line:
                # 优先选 span 最小的（即最内层）
                if best is None or (scope.end_line - scope.line) < (best.end_line - best.line):
                    best = scope
            if scope.end_line < line_1based:
                break
        return best


class BaseParser(ABC):
    """所有语言解析器的公共接口。

    子类只需实现：
      - language_name  → tree-sitter grammar 名称
      - extensions     → 文件扩展名列表
      - lang_enum      → Language 枚举值
      - _node_to_symbol() → 将捕获节点映射到 SymbolNode
      - _node_to_edge()   → 将捕获节点映射到 CallEdge

    基类负责：
      - 加载 grammar 和 query 脚本
      - 执行 tree-sitter parse + query
      - 构建 ScopeIndex
    """

    def __init__(self, grammar_path: str):
        """
        Args:
            grammar_path: 编译好的 grammar 共享库路径（.so / .dylib）
        """
        try:
            from tree_sitter import Language, Parser
        except ImportError as e:
            raise ImportError(
                "tree-sitter 未安装，请运行: pip install tree-sitter==0.21.*"
            ) from e

        # 语言名称：tree-sitter grammar 中的名称（如 'tsx'、'typescript'）
        # 子类可通过覆盖 language_name 来选择不同的 grammar（如 tsx 是 typescript 的超集）
        self._ts_language = Language(grammar_path, self.language_name)
        self._parser = Parser()
        self._parser.set_language(self._ts_language)

        # 预编译 query，避免每次 parse 都重新编译（显著提升批量解析性能）
        symbol_query_src = self._load_query("symbols.scm")
        call_query_src = self._load_query("calls.scm")
        self._symbol_query = self._ts_language.query(symbol_query_src)
        self._call_query = self._ts_language.query(call_query_src)

    # ── 子类必须实现 ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def language_name(self) -> str:
        """tree-sitter grammar 名称，如 'kotlin' / 'swift' / 'typescript' / 'tsx'"""

    @property
    def query_dir_name(self) -> str:
        """queries/ 目录名称，默认与 language_name 相同。

        当 grammar 名称（如 'tsx'）与 query 目录名称（如 'typescript'）
        不一致时，子类可以覆盖此属性。
        """
        return self.language_name

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """处理的文件扩展名（不含点），如 ['kt', 'kts']"""

    @property
    @abstractmethod
    def lang_enum(self) -> Lang:
        """对应的 Language 枚举值"""

    @abstractmethod
    def _node_to_symbol(
        self,
        captures: dict,
        source: bytes,
        file_path: str,
        parent_context: Optional[SymbolNode],
    ) -> Optional[SymbolNode]:
        """
        将 tree-sitter 捕获的节点组映射到 SymbolNode。

        Args:
            captures:       query.captures() 返回的捕获字典（capture_name → node）
            source:         文件的原始字节内容
            file_path:      相对仓库根的文件路径
            parent_context: 当前符号的父符号（类内方法时为类节点），可为 None

        Returns:
            SymbolNode 或 None（跳过此捕获）
        """

    @abstractmethod
    def _node_to_edge(
        self,
        captures: dict,
        source: bytes,
        current_scope: Optional[SymbolNode],
    ) -> Optional[CallEdge]:
        """
        将 tree-sitter 捕获的节点组映射到 CallEdge。

        Args:
            captures:      query.captures() 返回的捕获字典
            source:        文件的原始字节内容
            current_scope: 调用发生所在的符号作用域（即 caller）

        Returns:
            CallEdge 或 None（跳过）
        """

    # ── 基类提供通用流程 ──────────────────────────────────────────────────────

    def parse_file(
        self,
        file_path: str,
        repo_root: str,
    ) -> tuple[list[SymbolNode], list[CallEdge]]:
        """完整解析流程（所有语言共用）：

        1. 读取源文件（bytes）
        2. tree-sitter parse → AST
        3. 执行 symbol query → 提取所有符号
        4. 执行 call query → 提取所有调用关系
        5. 返回 (symbols, edges)
        """
        source = Path(file_path).read_bytes()
        tree = self._parser.parse(source)
        rel_path = str(Path(file_path).relative_to(repo_root))

        symbols = self._run_symbol_query(tree, source, rel_path)
        edges = self._run_call_query(tree, source, symbols, rel_path)
        return symbols, edges

    def _run_symbol_query(
        self,
        tree,
        source: bytes,
        file_path: str,
    ) -> list[SymbolNode]:
        """执行 symbols.scm query 并将捕获映射到 SymbolNode 列表。"""
        captures = self._symbol_query.captures(tree.root_node)
        results: list[SymbolNode] = []
        seen_ids: set[str] = set()

        # captures 是 list of (capture_name, node)
        # 将同一个 @symbol 节点的所有捕获组合在一起
        groups = self._group_captures(captures)

        for group in groups:
            sym = self._node_to_symbol(
                captures=group,
                source=source,
                file_path=file_path,
                parent_context=None,
            )
            if sym and sym.id not in seen_ids:
                results.append(sym)
                seen_ids.add(sym.id)

        return results

    def _run_call_query(
        self,
        tree,
        source: bytes,
        symbols: list[SymbolNode],
        file_path: str,
    ) -> list[CallEdge]:
        """执行 calls.scm query 并将捕获映射到 CallEdge 列表。"""
        captures = self._call_query.captures(tree.root_node)
        scope_index = ScopeIndex(symbols)
        results: list[CallEdge] = []

        groups = self._group_captures(captures)
        for group in groups:
            # 确定调用发生的行号（用于 scope 查找）
            anchor_node = group.get("call") or group.get("extends") or group.get("impls")
            if anchor_node is None:
                continue
            row = anchor_node.start_point[0]  # 0-based
            scope = scope_index.find_scope(row)

            edge = self._node_to_edge(
                captures=group,
                source=source,
                current_scope=scope,
            )
            if edge:
                results.append(edge)

        return results

    def _group_captures(self, captures) -> list[dict]:
        """
        将 tree-sitter captures 按锚点节点分组。

        tree-sitter 0.21 的 captures() 返回 list[(name, node)]，
        每个独立的 @symbol / @call 对应一组捕获。

        策略：以 'symbol' / 'call' / 'extends' / 'impls' 等
        "锚点捕获"为组分隔符，把同一 AST 节点附近的其他捕获聚合到同一个 dict。
        """
        ANCHOR_NAMES = {"symbol", "call", "extends", "impls", "class", "func", "iface"}
        groups: list[dict] = []
        current: dict = {}

        for item in captures:
            # tree-sitter 0.21 captures() 返回 list[(node, name)]
            # 旧版（0.20）返回 list[(name, node)，做兼容处理
            if isinstance(item[0], str):
                name, node = item  # 旧版
            else:
                node, name = item  # 0.21+
            if name in ANCHOR_NAMES:
                if current:
                    groups.append(current)
                current = {name: node}
            else:
                current[name] = node

        if current:
            groups.append(current)

        return groups

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def text_of(self, node, source: bytes) -> str:
        """从源码字节中提取节点文本（UTF-8 解码）。"""
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _load_query(self, filename: str) -> str:
        """加载 queries/ 目录下的 .scm 文件内容。"""
        queries_dir = Path(__file__).parent / self.query_dir_name / "queries"
        scm_path = queries_dir / filename
        if not scm_path.exists():
            raise FileNotFoundError(
                f"tree-sitter query 脚本不存在: {scm_path}\n"
                f"请确认 parsers/{self.query_dir_name}/queries/{filename} 已创建。"
            )
        return scm_path.read_text(encoding="utf-8")

    def can_handle(self, file_path: str) -> bool:
        """判断此解析器是否能处理指定文件。"""
        ext = Path(file_path).suffix.lstrip(".")
        return ext in self.extensions

    # ── 签名提示提取（供所有子 Parser 复用）────────────────────────────────────

    def _extract_call_signature_hint(
        self,
        captures: dict,
        source: bytes,
    ) -> str:
        """从调用表达式的 captures 中提取参数个数作为签名提示。

        返回参数个数的字符串形式（如 "2"），用于 Resolver 区分重载方法。
        子类可以通过 calls.scm 中的 @arguments 捕获来提供参数节点。
        """
        args_node = captures.get("arguments")
        if args_node is None:
            return ""

        args_text = self.text_of(args_node, source)
        if not args_text or args_text == "()" or args_text == "":
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

        # 按逗号分割，但要处理嵌套情况（如 lambda、函数调用、泛型等）
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
