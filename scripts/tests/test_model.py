"""
测试 core/model.py 中的数据模型：
  - SymbolNode 的构造、序列化/反序列化、工具方法
  - CallEdge 的构造与序列化
  - IndexGraph 的符号注册、反向索引、查询、序列化
"""
from __future__ import annotations

import json
import pytest

from code_index.core.model import (
    Language,
    SymbolKind,
    EdgeKind,
    SymbolNode,
    CallEdge,
    IndexGraph,
)


# ─────────────────────────────────────────────────────────────────────────────
# 辅助工厂函数
# ─────────────────────────────────────────────────────────────────────────────

def make_symbol(
    sym_id: str = "com.example.Foo",
    name: str = "Foo",
    kind: SymbolKind = SymbolKind.CLASS,
    language: Language = Language.KOTLIN,
    file: str = "src/Foo.kt",
    line: int = 10,
    end_line: int = 50,
    parent_id: str = "",
) -> SymbolNode:
    return SymbolNode(
        id=sym_id,
        name=name,
        kind=kind,
        language=language,
        file=file,
        line=line,
        column=0,
        end_line=end_line,
        visibility="public",
        is_abstract=False,
        signature=f"class {name}",
        parent_id=parent_id,
        module="com.example",
    )


def make_edge(
    caller_id: str,
    callee_name: str,
    callee_id: str = "",
    file: str = "src/Foo.kt",
    line: int = 20,
    kind: EdgeKind = EdgeKind.CALL,
) -> CallEdge:
    return CallEdge(
        caller_id=caller_id,
        callee_name=callee_name,
        file=file,
        line=line,
        kind=kind,
        callee_id=callee_id,
        resolved=bool(callee_id),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SymbolNode 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestSymbolNode:
    def test_basic_construction(self):
        sym = make_symbol()
        assert sym.id == "com.example.Foo"
        assert sym.name == "Foo"
        assert sym.kind == SymbolKind.CLASS
        assert sym.language == Language.KOTLIN
        assert sym.file == "src/Foo.kt"
        assert sym.line == 10
        assert sym.end_line == 50
        assert sym.visibility == "public"
        assert not sym.is_abstract

    def test_to_dict_contains_string_enums(self):
        sym = make_symbol()
        d = sym.to_dict()
        assert d["kind"] == "class"
        assert d["language"] == "kotlin"
        assert d["id"] == "com.example.Foo"

    def test_from_dict_roundtrip(self):
        sym = make_symbol()
        d = sym.to_dict()
        restored = SymbolNode.from_dict(d)
        assert restored.id == sym.id
        assert restored.name == sym.name
        assert restored.kind == sym.kind
        assert restored.language == sym.language
        assert restored.line == sym.line

    def test_location_str(self):
        sym = make_symbol(line=42)
        assert sym.location_str() == "src/Foo.kt:42"

    def test_summary_line_contains_kind_and_id(self):
        sym = make_symbol()
        s = sym.summary_line()
        assert "CLASS" in s
        assert "com.example.Foo" in s
        assert "src/Foo.kt" in s

    def test_summary_line_with_signature(self):
        sym = make_symbol()
        sym.signature = "class Foo : BaseClass()"
        s = sym.summary_line()
        assert "class Foo : BaseClass()" in s

    def test_private_symbol_visibility_in_summary(self):
        sym = make_symbol()
        sym.visibility = "private"
        s = sym.summary_line()
        assert "private" in s

    def test_json_serializable(self):
        sym = make_symbol()
        d = sym.to_dict()
        # should not raise
        json_str = json.dumps(d)
        assert "com.example.Foo" in json_str


# ─────────────────────────────────────────────────────────────────────────────
# CallEdge 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestCallEdge:
    def test_basic_construction(self):
        edge = make_edge("com.example.Foo.bar", "baz")
        assert edge.caller_id == "com.example.Foo.bar"
        assert edge.callee_name == "baz"
        assert edge.callee_id == ""
        assert not edge.resolved

    def test_resolved_edge(self):
        edge = make_edge(
            "com.example.Foo.bar",
            "baz",
            callee_id="com.example.Baz.baz",
        )
        assert edge.resolved
        assert edge.callee_id == "com.example.Baz.baz"

    def test_to_dict_roundtrip(self):
        edge = make_edge(
            "com.example.Foo.bar",
            "baz",
            callee_id="com.example.Baz.baz",
            kind=EdgeKind.IMPLEMENTS,
        )
        d = edge.to_dict()
        assert d["kind"] == "implements"
        restored = CallEdge.from_dict(d)
        assert restored.kind == EdgeKind.IMPLEMENTS
        assert restored.caller_id == edge.caller_id

    def test_id_auto_generated(self):
        edge1 = make_edge("caller.A", "foo", file="a.kt", line=10)
        edge2 = make_edge("caller.A", "foo", file="a.kt", line=10)
        # 相同内容的 edge id 应相同（确定性）
        assert edge1.id == edge2.id

    def test_id_differs_for_different_edges(self):
        edge1 = make_edge("caller.A", "foo", file="a.kt", line=10)
        edge2 = make_edge("caller.B", "bar", file="b.kt", line=20)
        assert edge1.id != edge2.id


# ─────────────────────────────────────────────────────────────────────────────
# IndexGraph 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestIndexGraph:
    def _build_graph(self) -> IndexGraph:
        """构建含几个符号和调用边的测试图。"""
        g = IndexGraph()

        # 符号
        iface = make_symbol(
            "com.example.IRepo",
            "IRepo",
            SymbolKind.INTERFACE,
        )
        cls_a = make_symbol(
            "com.example.RepoImpl",
            "RepoImpl",
            SymbolKind.CLASS,
        )
        method_save = make_symbol(
            "com.example.RepoImpl.save",
            "save",
            SymbolKind.METHOD,
            parent_id="com.example.RepoImpl",
        )
        method_find = make_symbol(
            "com.example.RepoImpl.find",
            "find",
            SymbolKind.METHOD,
            parent_id="com.example.RepoImpl",
        )

        for s in [iface, cls_a, method_save, method_find]:
            g.add_symbol(s)

        # 调用边
        call_edge = make_edge(
            caller_id="com.example.RepoImpl.save",
            callee_name="find",
            callee_id="com.example.RepoImpl.find",
        )
        impl_edge = make_edge(
            caller_id="com.example.RepoImpl",
            callee_name="IRepo",
            callee_id="com.example.IRepo",
            kind=EdgeKind.IMPLEMENTS,
        )
        g.add_edge(call_edge)
        g.add_edge(impl_edge)

        return g

    def test_symbol_count(self):
        g = self._build_graph()
        assert len(g.symbols) == 4

    def test_find_by_name_exact(self):
        g = self._build_graph()
        results = g.find_by_name("RepoImpl")
        assert len(results) == 1
        assert results[0].id == "com.example.RepoImpl"

    def test_find_by_name_method(self):
        g = self._build_graph()
        results = g.find_by_name("save")
        assert len(results) == 1
        assert results[0].kind == SymbolKind.METHOD

    def test_callers_of(self):
        g = self._build_graph()
        # find 被 save 调用 → callers_of(find) 应包含 save
        callers = g.callers_of("com.example.RepoImpl.find")
        assert "com.example.RepoImpl.save" in callers

    def test_callees_of(self):
        g = self._build_graph()
        callees = g.callees_of("com.example.RepoImpl.save")
        assert "com.example.RepoImpl.find" in callees

    def test_impls_of(self):
        g = self._build_graph()
        impls = g.impls_of("com.example.IRepo")
        assert "com.example.RepoImpl" in impls

    def test_symbols_in_file(self):
        g = self._build_graph()
        syms = g.symbols_in_file("src/Foo.kt")
        # 所有测试符号都在 src/Foo.kt
        assert len(syms) == 4
        # 按行号排序
        lines = [s.line for s in syms]
        assert lines == sorted(lines)

    def test_symbols_by_kind(self):
        g = self._build_graph()
        methods = g.symbols_by_kind(SymbolKind.METHOD)
        assert len(methods) == 2
        names = {m.name for m in methods}
        assert names == {"save", "find"}

    def test_remove_file(self):
        g = self._build_graph()
        g.remove_file("src/Foo.kt")
        assert len(g.symbols) == 0

    def test_to_dict_and_from_dict(self):
        g = self._build_graph()
        d = g.to_dict()
        assert "symbols" in d
        assert "edges" in d
        assert len(d["symbols"]) == 4

        g2 = IndexGraph.from_dict(d)
        assert len(g2.symbols) == 4
        assert len(g2.edges) == 2
        # 反向索引应重建
        callers = g2.callers_of("com.example.RepoImpl.find")
        assert "com.example.RepoImpl.save" in callers

    def test_save_and_load(self, tmp_path):
        g = self._build_graph()
        path = tmp_path / "graph.json"
        g.save(path)
        assert path.exists()

        g2 = IndexGraph.load(path)
        assert len(g2.symbols) == len(g.symbols)
        assert len(g2.edges) == len(g.edges)

    def test_repr(self):
        g = self._build_graph()
        r = repr(g)
        assert "IndexGraph" in r
        assert "symbols=4" in r
