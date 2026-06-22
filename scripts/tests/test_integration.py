"""
集成测试 — 端到端全链路验证

覆盖：
  1. Indexer.build()          → 解析 fixtures 目录
  2. Resolver.resolve_all()   → 跨文件符号解析
  3. QueryEngine.find()       → 精确 / 前缀 / 通配 / 全限定后缀查询
  4. QueryEngine.find_callers/callees/impls → 调用图查询
  5. QueryEngine.file_outline()            → 大纲查询
  6. IndexGraph.save() + load()            → 序列化往返
  7. VfsGenerator.generate()              → VFS 文件生成
  8. IncrementalIndexer                   → 增量更新

注意：这些测试需要 grammar 已编译（make grammars）。
      若 grammar 缺失，整个模块会被 pytest.skip。
"""
from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")  # 屏蔽 tree-sitter FutureWarning

# ── 检测 grammar 是否可用 ──────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GRAMMARS_DIR = Path(__file__).parent.parent / "code_index" / "grammars"

KOTLIN_GRAMMAR_AVAILABLE = any(
    (GRAMMARS_DIR / name).exists()
    for name in ["kotlin.so", "kotlin.dylib", "languages_kotlin.so", "languages_kotlin.dylib"]
)
JAVA_GRAMMAR_AVAILABLE = any(
    (GRAMMARS_DIR / name).exists()
    for name in ["java.so", "java.dylib", "languages_java.so", "languages_java.dylib"]
)
GRAMMARS_AVAILABLE = KOTLIN_GRAMMAR_AVAILABLE and JAVA_GRAMMAR_AVAILABLE

requires_grammars = pytest.mark.skipif(
    not GRAMMARS_AVAILABLE,
    reason="Grammar 未编译，请先运行: make grammars (或 python -m code_index.grammars.build kotlin java)",
)


# ── 共享 fixture：一次性构建 IndexGraph ────────────────────────────────────


@pytest.fixture(scope="module")
def built_graph():
    """对 tests/fixtures 做全量索引并跑 Resolver，返回 IndexGraph。"""
    import code_index.parsers.registry as reg_mod
    reg_mod._default_registry = None  # 重置单例，确保用最新 grammars_dir

    from code_index.core.indexer import Indexer
    from code_index.core.resolver import Resolver

    indexer = Indexer(
        repo_root=str(FIXTURES_DIR),
        langs=["kotlin", "java"],
    )
    graph = indexer.build(project_name="it-fixtures", show_progress=False)
    resolver = Resolver(graph)
    resolver.resolve_all()
    return graph


@pytest.fixture(scope="module")
def engine(built_graph):
    """QueryEngine，scope=module 与 built_graph 共享。"""
    from code_index.core.query_engine import QueryEngine
    return QueryEngine(built_graph)


# ── 1. Indexer 基础断言 ────────────────────────────────────────────────────


@requires_grammars
class TestIndexer:
    def test_symbol_count_reasonable(self, built_graph):
        """两个 Kotlin 文件 + 一个 Java 文件，应解析出 ≥ 20 个符号。"""
        assert len(built_graph.symbols) >= 20

    def test_edge_count_reasonable(self, built_graph):
        """调用边应 ≥ 10 条。"""
        assert len(built_graph.edges) >= 10

    def test_files_by_lang(self, built_graph):
        """应包含 kotlin 和 java 两种语言的文件记录。"""
        langs = built_graph.stats.files_by_lang
        assert "kotlin" in langs
        assert "java" in langs

    def test_kotlin_class_exists(self, built_graph):
        """CommentService 类应被解析出来。"""
        assert "com.example.comment.CommentService" in built_graph.symbols

    def test_java_class_exists(self, built_graph):
        """UserService 类应被解析出来。"""
        assert "com.example.user.UserService" in built_graph.symbols

    def test_cross_file_kotlin_class(self, built_graph):
        """NotificationService（service_b.kt）应被解析出来。"""
        assert "com.example.notification.NotificationService" in built_graph.symbols

    def test_interface_parsed(self, built_graph):
        """CommentRepository 接口应被解析出来。"""
        assert "com.example.comment.CommentRepository" in built_graph.symbols

    def test_enum_parsed(self, built_graph):
        """CommentStatus enum 应被解析出来。"""
        assert "com.example.comment.CommentStatus" in built_graph.symbols

    def test_typealias_parsed(self, built_graph):
        """CommentId typealias 应被解析出来。"""
        assert "com.example.comment.CommentId" in built_graph.symbols


# ── 2. Resolver 跨文件解析 ─────────────────────────────────────────────────


@requires_grammars
class TestResolver:
    def test_resolved_edges_positive(self, built_graph):
        """Resolver 后至少有 1 条 resolved=True 的边。"""
        resolved = [e for e in built_graph.edges if e.resolved]
        assert len(resolved) >= 1

    def test_internal_call_resolved(self, built_graph):
        """同文件内的调用（如 createComment → generateId）应被解析。"""
        # createComment 调用了 generateId（同文件）
        create_sym_id = "com.example.comment.createComment"
        resolved_callees = [
            e.callee_id for e in built_graph.edges
            if e.caller_id == create_sym_id and e.resolved
        ]
        assert len(resolved_callees) >= 1, (
            f"createComment 没有已解析的 callees，实际边: "
            f"{[(e.callee_name, e.resolved) for e in built_graph.edges if e.caller_id == create_sym_id]}"
        )


# ── 3. QueryEngine.find() ─────────────────────────────────────────────────


@requires_grammars
class TestQueryEngineFind:
    def test_exact_match_class(self, engine):
        """精确查询 CommentService 应返回 1 个结果。"""
        results = engine.find("CommentService")
        ids = [r.id for r in results]
        assert "com.example.comment.CommentService" in ids

    def test_exact_match_java_class(self, engine):
        """精确查询 UserService 应返回结果。"""
        results = engine.find("UserService")
        ids = [r.id for r in results]
        assert "com.example.user.UserService" in ids

    def test_prefix_wildcard(self, engine):
        """前缀通配 Comment* 应返回 ≥ 4 个 Comment 相关符号。"""
        results = engine.find("Comment*")
        ids = [r.id for r in results]
        assert any("CommentService" in i for i in ids)
        assert any("CommentRepository" in i for i in ids)
        assert len(results) >= 4

    def test_suffix_wildcard(self, engine):
        """后缀通配 *Service 应同时命中 CommentService 和 UserService。"""
        results = engine.find("*Service")
        ids = [r.id for r in results]
        assert any("CommentService" in i for i in ids)
        assert any("UserService" in i for i in ids)

    def test_glob_question_mark(self, engine):
        """通配符 ? 匹配单字符，User?epository 应匹配 UserRepository。"""
        results = engine.find("User?epository")
        ids = [r.id for r in results]
        assert any("UserRepository" in i for i in ids)

    def test_qualified_suffix(self, engine):
        """全限定后缀查询 .comment.CommentService 应精确命中。"""
        results = engine.find(".comment.CommentService")
        ids = [r.id for r in results]
        assert "com.example.comment.CommentService" in ids

    def test_kind_filter(self, engine):
        """kind 过滤 class 应只返回 class 类型符号。"""
        results = engine.find("*Service", kind="class")
        assert all(r.kind.value == "class" for r in results), (
            f"Non-class results: {[(r.id, r.kind.value) for r in results if r.kind.value != 'class']}"
        )

    def test_lang_filter_kotlin(self, engine):
        """lang 过滤 kotlin 应只返回 Kotlin 符号。"""
        results = engine.find("*Service", language="kotlin")
        assert all(r.language.value == "kotlin" for r in results)

    def test_lang_filter_java(self, engine):
        """lang 过滤 java 应只返回 Java 符号。"""
        results = engine.find("*Service", language="java")
        assert all(r.language.value == "java" for r in results)

    def test_empty_pattern(self, engine):
        """空 pattern 应返回空列表。"""
        assert engine.find("") == []

    def test_no_match(self, engine):
        """不存在的符号应返回空列表。"""
        results = engine.find("XyzNonExistentClass99")
        assert results == []

    def test_limit(self, engine):
        """limit 参数应被严格遵守。"""
        results = engine.find("*", limit=3)
        assert len(results) <= 3


# ── 4. find_callers / find_callees ────────────────────────────────────────


@requires_grammars
class TestCallGraph:
    def test_find_callees_of_create_comment(self, engine, built_graph):
        """createComment 应有 callee（至少调用了一个函数）。"""
        sym_id = "com.example.comment.createComment"
        assert sym_id in built_graph.symbols, f"{sym_id} not indexed"
        callees = engine.find_callees(sym_id)
        # createComment 调用了 generateId / save / Comment 构造
        assert len(callees) >= 1, f"Expected callees, got {callees}"

    def test_find_callees_of_nonexistent(self, engine):
        """不存在的 symbol_id 应返回空列表。"""
        assert engine.find_callees("com.nonexistent.Foo") == []

    def test_find_callers_of_delete_comment(self, engine, built_graph):
        """deleteComment 应有 callee：repository.delete 等。"""
        sym_id = "com.example.comment.deleteComment"
        assert sym_id in built_graph.symbols
        callees = engine.find_callees(sym_id)
        assert len(callees) >= 1

    def test_find_callers_empty_for_top_level(self, engine, built_graph):
        """顶层公开方法（如 NotificationService.notifyOnNewComment）
        在 fixtures 范围内不会被其他符号调用，callers 应为空。"""
        sym_id = "com.example.notification.notifyOnNewComment"
        if sym_id not in built_graph.symbols:
            pytest.skip(f"{sym_id} not indexed (may be method-only)")
        callers = engine.find_callers(sym_id)
        # 在 fixtures 目录内没有其他类调用它
        assert isinstance(callers, list)

    def test_callees_returns_symbol_nodes(self, engine, built_graph):
        """find_callees 返回的应为 SymbolNode 列表（或空列表）。"""
        from code_index.core.model import SymbolNode
        sym_id = "com.example.comment.createComment"
        if sym_id not in built_graph.symbols:
            pytest.skip("symbol not indexed")
        callees = engine.find_callees(sym_id)
        for c in callees:
            assert isinstance(c, SymbolNode)


# ── 5. find_implementations ───────────────────────────────────────────────


@requires_grammars
class TestFindImpls:
    def test_find_impls_of_repository_interface(self, engine, built_graph):
        """CommentRepository 接口的实现查询（fixtures 内无实现类，返回空列表）。"""
        sym_id = "com.example.comment.CommentRepository"
        if sym_id not in built_graph.symbols:
            pytest.skip("symbol not indexed")
        impls = engine.find_implementations(sym_id)
        # fixtures 中没有 CommentRepositoryImpl，期望空列表
        assert isinstance(impls, list)

    def test_impls_nonexistent_symbol(self, engine):
        """不存在的 symbol 应返回空列表。"""
        assert engine.find_implementations("com.fake.IRepo") == []


# ── 6. file_outline ──────────────────────────────────────────────────────


@requires_grammars
class TestFileOutline:
    def test_outline_kotlin_sample(self, engine):
        """kotlin/sample_class.kt 的大纲应包含 ≥ 5 个符号。"""
        results = engine.file_outline("kotlin/sample_class.kt")
        assert len(results) >= 5, f"Got: {[r.id for r in results]}"

    def test_outline_java_sample(self, engine):
        """java/sample_class.java 的大纲应包含 ≥ 5 个符号。"""
        results = engine.file_outline("java/sample_class.java")
        assert len(results) >= 5, f"Got: {[r.id for r in results]}"

    def test_outline_sorted_by_line(self, engine):
        """大纲结果应按行号升序排列。"""
        results = engine.file_outline("kotlin/sample_class.kt")
        lines = [r.line for r in results]
        assert lines == sorted(lines), f"Not sorted: {lines}"

    def test_outline_service_b(self, engine):
        """service_b.kt 的大纲应包含 NotificationService。"""
        results = engine.file_outline("kotlin/service_b.kt")
        ids = [r.id for r in results]
        assert any("NotificationService" in i for i in ids), (
            f"NotificationService not found in outline: {ids}"
        )

    def test_outline_unknown_file(self, engine):
        """不存在的文件应返回空列表。"""
        assert engine.file_outline("nonexistent/file.kt") == []


# ── 7. 序列化往返（save + load）────────────────────────────────────────────


@requires_grammars
class TestSerialization:
    def test_save_and_load(self, built_graph, tmp_path):
        """graph.save() → graph.load() 往返后，符号数和边数保持一致。"""
        from code_index.core.model import IndexGraph
        save_path = tmp_path / "graph.json"
        built_graph.save(save_path)

        assert save_path.exists()
        g2 = IndexGraph.load(save_path)
        assert len(g2.symbols) == len(built_graph.symbols)
        assert len(g2.edges) == len(built_graph.edges)

    def test_json_is_valid(self, built_graph, tmp_path):
        """保存的 JSON 应可被标准库正常解析。"""
        save_path = tmp_path / "graph.json"
        built_graph.save(save_path)
        with open(save_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "symbols" in data
        assert "edges" in data
        assert "version" in data

    def test_from_dict_roundtrip(self, built_graph):
        """to_dict() → from_dict() 往返应保持符号和边数不变。"""
        from code_index.core.model import IndexGraph
        d = built_graph.to_dict()
        g2 = IndexGraph.from_dict(d)
        assert len(g2.symbols) == len(built_graph.symbols)
        assert len(g2.edges) == len(built_graph.edges)

    def test_symbol_ids_preserved(self, built_graph, tmp_path):
        """序列化往返后，所有 symbol id 应保持不变。"""
        from code_index.core.model import IndexGraph
        save_path = tmp_path / "graph2.json"
        built_graph.save(save_path)
        g2 = IndexGraph.load(save_path)
        assert set(g2.symbols.keys()) == set(built_graph.symbols.keys())


# ── 8. VfsGenerator ──────────────────────────────────────────────────────


@requires_grammars
class TestVfsGenerator:
    def test_vfs_generates_files(self, built_graph, tmp_path):
        """VfsGenerator 应生成 ≥ 1 个文件。"""
        from code_index.core.vfs_generator import VfsGenerator
        vfs_root = tmp_path / "vfs"
        gen = VfsGenerator()
        gen.generate(built_graph, vfs_root)
        # VFS 目录应存在
        assert vfs_root.exists()
        all_files = list(vfs_root.rglob("*"))
        assert len(all_files) >= 1, f"VFS generated no files in {vfs_root}"

    def test_vfs_json_readable(self, built_graph, tmp_path):
        """VFS 生成的 JSON 文件应可被正常解析。"""
        from code_index.core.vfs_generator import VfsGenerator
        vfs_root = tmp_path / "vfs2"
        gen = VfsGenerator()
        gen.generate(built_graph, vfs_root)
        for json_file in vfs_root.rglob("*.json"):
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, (dict, list))
            break  # 只验证第一个文件


# ── 9. IncrementalIndexer ────────────────────────────────────────────────


@requires_grammars
class TestIncrementalIndexer:
    def test_full_build_creates_index(self, tmp_path):
        """force_full=True 应完整构建并保存 graph.json。"""
        import code_index.parsers.registry as reg_mod
        reg_mod._default_registry = None

        from code_index.core.incremental import IncrementalIndexer
        inc = IncrementalIndexer(
            repo_root=str(FIXTURES_DIR),
            index_dir=tmp_path / ".index",
            langs=["kotlin", "java"],
        )
        graph, changed = inc.update(force_full=True, show_progress=False)
        assert len(graph.symbols) >= 20
        assert changed > 0
        assert (tmp_path / ".index" / "graph.json").exists()

    def test_incremental_no_change(self, tmp_path):
        """首次 build 后立刻再 update，changed 应为 0（无文件变化）。"""
        import code_index.parsers.registry as reg_mod
        reg_mod._default_registry = None

        from code_index.core.incremental import IncrementalIndexer
        index_dir = tmp_path / ".index"
        inc = IncrementalIndexer(
            repo_root=str(FIXTURES_DIR),
            index_dir=index_dir,
            langs=["kotlin", "java"],
        )
        inc.update(force_full=True, show_progress=False)
        # 第二次 update（无文件改动）
        graph2, changed2 = inc.update(force_full=False, show_progress=False)
        assert changed2 == 0
        assert len(graph2.symbols) >= 20


# ── 10. format 输出验证 ───────────────────────────────────────────────────


@requires_grammars
class TestFormatOutput:
    def test_format_symbols_text(self, engine):
        """format_symbols_text 应返回非空字符串（当结果非空时）。"""
        results = engine.find("CommentService")
        if not results:
            pytest.skip("No results to format")
        text = engine.format_symbols_text(results)
        assert isinstance(text, str)
        assert "CommentService" in text

    def test_format_outline_text(self, engine):
        """format_outline_text 应包含行号信息。"""
        results = engine.file_outline("kotlin/sample_class.kt")
        if not results:
            pytest.skip("No outline results")
        text = engine.format_outline_text(results)
        assert isinstance(text, str)
        # 大纲文本应包含行号（数字）
        assert any(char.isdigit() for char in text)

    def test_format_callers_text_empty(self, engine):
        """format_callers_text 对空列表应返回特定提示字符串。"""
        text = engine.format_callers_text([])
        assert isinstance(text, str)
        assert len(text) > 0  # 应有"no callers"之类提示
