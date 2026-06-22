"""
测试 QueryEngine 的四种查询模式、调用链查询、大纲查询和格式化输出。
这些测试完全基于内存中的 IndexGraph，不依赖 tree-sitter 或真实文件系统。
"""
from __future__ import annotations

import pytest

from code_index.core.model import (
    Language,
    SymbolKind,
    EdgeKind,
    SymbolNode,
    CallEdge,
    IndexGraph,
)
from code_index.core.query_engine import QueryEngine


# ─────────────────────────────────────────────────────────────────────────────
# 工厂函数
# ─────────────────────────────────────────────────────────────────────────────

def _sym(
    sym_id: str,
    name: str,
    kind: SymbolKind = SymbolKind.CLASS,
    lang: Language = Language.KOTLIN,
    file: str = "src/Sample.kt",
    line: int = 1,
    end_line: int = 100,
    parent_id: str = "",
    signature: str = "",
) -> SymbolNode:
    return SymbolNode(
        id=sym_id,
        name=name,
        kind=kind,
        language=lang,
        file=file,
        line=line,
        column=0,
        end_line=end_line,
        visibility="public",
        is_abstract=False,
        signature=signature or name,
        parent_id=parent_id,
        module=sym_id.rsplit(".", 1)[0] if "." in sym_id else "",
    )


def _edge(
    caller_id: str,
    callee_name: str,
    callee_id: str = "",
    kind: EdgeKind = EdgeKind.CALL,
    file: str = "src/Sample.kt",
    line: int = 10,
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


@pytest.fixture
def graph() -> IndexGraph:
    """构建含有多种符号和调用关系的测试图。

    符号：
      com.example.ICommentRepo        (interface, kotlin)
      com.example.CommentService      (class, kotlin)
      com.example.CommentService.getComment  (method, kotlin)
      com.example.CommentService.deleteComment (method, kotlin)
      com.example.CommentService.generateId   (method, private, kotlin)
      com.example.UserService         (class, kotlin)
      com.example.UserService.findUser (method, kotlin)
      com.example.data.CommentVO      (class, kotlin)  ← 不同子包
      com.example.JavaHelper          (class, java)
    """
    g = IndexGraph()

    syms = [
        _sym("com.example.ICommentRepo", "ICommentRepo",
             SymbolKind.INTERFACE, file="src/ICommentRepo.kt", line=5),
        _sym("com.example.CommentService", "CommentService",
             SymbolKind.CLASS, file="src/CommentService.kt", line=10, end_line=80),
        _sym("com.example.CommentService.getComment", "getComment",
             SymbolKind.METHOD,
             file="src/CommentService.kt", line=20, end_line=25,
             parent_id="com.example.CommentService",
             signature="fun getComment(id: String): Comment?"),
        _sym("com.example.CommentService.deleteComment", "deleteComment",
             SymbolKind.METHOD,
             file="src/CommentService.kt", line=27, end_line=35,
             parent_id="com.example.CommentService",
             signature="fun deleteComment(id: String)"),
        _sym("com.example.CommentService.generateId", "generateId",
             SymbolKind.METHOD,
             file="src/CommentService.kt", line=37, end_line=40,
             parent_id="com.example.CommentService"),
        _sym("com.example.UserService", "UserService",
             SymbolKind.CLASS, file="src/UserService.kt", line=5),
        _sym("com.example.UserService.findUser", "findUser",
             SymbolKind.METHOD,
             file="src/UserService.kt", line=10,
             parent_id="com.example.UserService"),
        _sym("com.example.data.CommentVO", "CommentVO",
             SymbolKind.CLASS,
             file="src/data/CommentVO.kt", line=3),
        _sym("com.example.JavaHelper", "JavaHelper",
             SymbolKind.CLASS, lang=Language.JAVA,
             file="src/JavaHelper.java", line=5),
    ]
    for s in syms:
        g.add_symbol(s)

    edges = [
        # deleteComment 调用 generateId
        _edge("com.example.CommentService.deleteComment",
              "generateId",
              "com.example.CommentService.generateId"),
        # getComment 也调用 generateId
        _edge("com.example.CommentService.getComment",
              "generateId",
              "com.example.CommentService.generateId"),
        # CommentService 实现 ICommentRepo
        _edge("com.example.CommentService", "ICommentRepo",
              "com.example.ICommentRepo",
              kind=EdgeKind.IMPLEMENTS),
    ]
    for e in edges:
        g.add_edge(e)

    return g


@pytest.fixture
def engine(graph: IndexGraph) -> QueryEngine:
    return QueryEngine(graph)


# ─────────────────────────────────────────────────────────────────────────────
# 精确查询
# ─────────────────────────────────────────────────────────────────────────────

class TestExactFind:
    def test_exact_hit(self, engine):
        results = engine.find("CommentService")
        ids = [r.id for r in results]
        assert "com.example.CommentService" in ids

    def test_exact_miss_returns_prefix_fallback(self, engine):
        # "Comment" 没有精确命中，但有前缀 fallback
        results = engine.find("Comment")
        ids = [r.id for r in results]
        # 前缀 fallback 应该返回 CommentService / CommentVO 等
        assert any("Comment" in i for i in ids)

    def test_empty_pattern_returns_empty(self, engine):
        assert engine.find("") == []

    def test_exact_kind_filter(self, engine):
        results = engine.find("CommentService", kind="interface")
        # CommentService 是 class，不是 interface，过滤后应为空
        assert results == []

    def test_exact_lang_filter_kotlin(self, engine):
        results = engine.find("JavaHelper", language="kotlin")
        # JavaHelper 是 java，过滤后应为空
        assert results == []

    def test_exact_lang_filter_java(self, engine):
        results = engine.find("JavaHelper", language="java")
        assert len(results) == 1
        assert results[0].language == Language.JAVA

    def test_limit(self, engine):
        # 搜索所有符号（通配）并限制数量
        results = engine.find("*", limit=3)
        assert len(results) <= 3


# ─────────────────────────────────────────────────────────────────────────────
# 前缀查询
# ─────────────────────────────────────────────────────────────────────────────

class TestPrefixFind:
    def test_prefix_with_star(self, engine):
        results = engine.find("delete*")
        ids = [r.id for r in results]
        assert "com.example.CommentService.deleteComment" in ids

    def test_prefix_case_insensitive(self, engine):
        results = engine.find("Delete*")
        ids = [r.id for r in results]
        assert "com.example.CommentService.deleteComment" in ids

    def test_prefix_all_comment(self, engine):
        results = engine.find("Comment*")
        ids = [r.id for r in results]
        # CommentService, CommentVO, and methods starting with Comment (none here)
        service_ids = [i for i in ids if "CommentService" in i or "CommentVO" in i]
        assert len(service_ids) >= 2

    def test_prefix_no_match(self, engine):
        results = engine.find("XYZNonExistent*")
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 通配符查询
# ─────────────────────────────────────────────────────────────────────────────

class TestGlobFind:
    def test_suffix_wildcard(self, engine):
        results = engine.find("*Service")
        ids = [r.id for r in results]
        assert "com.example.CommentService" in ids
        assert "com.example.UserService" in ids

    def test_question_mark_wildcard(self, engine):
        # "get?omment" 匹配 "getComment"（C → ?）
        results = engine.find("get?omment")
        ids = [r.id for r in results]
        assert "com.example.CommentService.getComment" in ids

    def test_glob_kind_filter(self, engine):
        results = engine.find("*Service", kind="class")
        for r in results:
            assert r.kind == SymbolKind.CLASS

    def test_star_star_all(self, engine):
        results = engine.find("*", limit=100)
        # 所有 9 个符号都应命中
        assert len(results) == 9


# ─────────────────────────────────────────────────────────────────────────────
# 全限定名后缀查询
# ─────────────────────────────────────────────────────────────────────────────

class TestQualifiedSuffixFind:
    def test_qualified_suffix(self, engine):
        results = engine.find(".data.CommentVO")
        ids = [r.id for r in results]
        assert "com.example.data.CommentVO" in ids

    def test_qualified_suffix_with_method(self, engine):
        results = engine.find(".CommentService.deleteComment")
        ids = [r.id for r in results]
        assert "com.example.CommentService.deleteComment" in ids

    def test_qualified_suffix_no_match(self, engine):
        results = engine.find(".nonexistent.Foo")
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 调用链查询
# ─────────────────────────────────────────────────────────────────────────────

class TestCallersCallees:
    def test_find_callers(self, engine):
        callers = engine.find_callers("com.example.CommentService.generateId")
        ids = [c.id for c in callers]
        assert "com.example.CommentService.deleteComment" in ids
        assert "com.example.CommentService.getComment" in ids

    def test_find_callers_no_callers(self, engine):
        # UserService.findUser 没有被任何人调用
        callers = engine.find_callers("com.example.UserService.findUser")
        assert callers == []

    def test_find_callees(self, engine):
        callees = engine.find_callees("com.example.CommentService.deleteComment")
        ids = [c.id for c in callees]
        assert "com.example.CommentService.generateId" in ids

    def test_find_callees_no_callees(self, engine):
        callees = engine.find_callees("com.example.CommentService.generateId")
        assert callees == []

    def test_find_callers_nonexistent_symbol(self, engine):
        callers = engine.find_callers("com.example.Ghost")
        assert callers == []

    def test_find_callees_limit(self, engine):
        callees = engine.find_callees(
            "com.example.CommentService.deleteComment", limit=1
        )
        assert len(callees) <= 1


# ─────────────────────────────────────────────────────────────────────────────
# 实现类查询
# ─────────────────────────────────────────────────────────────────────────────

class TestFindImplementations:
    def test_find_impls(self, engine):
        impls = engine.find_implementations("com.example.ICommentRepo")
        ids = [i.id for i in impls]
        assert "com.example.CommentService" in ids

    def test_find_impls_no_impls(self, engine):
        impls = engine.find_implementations("com.example.JavaHelper")
        assert impls == []

    def test_find_impls_nonexistent(self, engine):
        impls = engine.find_implementations("com.example.IFake")
        assert impls == []


# ─────────────────────────────────────────────────────────────────────────────
# 文件大纲查询
# ─────────────────────────────────────────────────────────────────────────────

class TestFileOutline:
    def test_exact_path(self, engine):
        results = engine.file_outline("src/CommentService.kt")
        assert len(results) >= 1
        for r in results:
            assert r.file == "src/CommentService.kt"

    def test_suffix_path(self, engine):
        # 只传文件名后缀
        results = engine.file_outline("CommentService.kt")
        assert len(results) >= 1

    def test_outline_sorted_by_line(self, engine):
        results = engine.file_outline("src/CommentService.kt")
        lines = [r.line for r in results]
        assert lines == sorted(lines)

    def test_unknown_file(self, engine):
        results = engine.file_outline("NonExistent.kt")
        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 格式化输出
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatOutput:
    def test_format_symbols_text_non_empty(self, engine):
        syms = engine.find("CommentService")
        text = engine.format_symbols_text(syms)
        assert "com.example.CommentService" in text
        assert "src/CommentService.kt" in text

    def test_format_symbols_text_empty(self, engine):
        text = engine.format_symbols_text([])
        assert text == "(no results)"

    def test_format_callers_text_non_empty(self, engine):
        callers = engine.find_callers("com.example.CommentService.generateId")
        text = engine.format_callers_text(callers)
        assert "deleteComment" in text or "getComment" in text

    def test_format_callers_text_empty(self, engine):
        text = engine.format_callers_text([])
        assert text == "(none)"

    def test_format_impls_text_non_empty(self, engine):
        impls = engine.find_implementations("com.example.ICommentRepo")
        text = engine.format_impls_text(impls)
        assert "CommentService" in text

    def test_format_impls_text_empty(self, engine):
        text = engine.format_impls_text([])
        assert text == "(no implementations found)"

    def test_format_outline_text_indentation(self, engine):
        syms = engine.file_outline("src/CommentService.kt")
        text = engine.format_outline_text(syms)
        # 方法（有 parent_id 在同文件内）应有缩进
        assert "    " in text  # 4个空格缩进

    def test_format_outline_text_contains_line_numbers(self, engine):
        syms = engine.file_outline("src/CommentService.kt")
        text = engine.format_outline_text(syms)
        assert "L10" in text or "L20" in text

    def test_format_outline_text_empty(self, engine):
        text = engine.format_outline_text([])
        assert text == "(no symbols)"
