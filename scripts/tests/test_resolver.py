"""
测试 Resolver 的符号解析策略（含签名感知匹配）。

覆盖场景：
  1. 方法重载（同名不同参数个数）— 签名感知匹配
  2. 相同包调用 / 被调用
  3. 不同包调用 / 被调用
  4. 同文件内符号优先
  5. 签名提取工具方法
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
from code_index.core.resolver import Resolver


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
    module: str = "",
) -> SymbolNode:
    """创建 SymbolNode，自动从 sym_id 提取 module。"""
    if not module and "." in sym_id:
        # 从 sym_id 提取包名（去掉最后一段）
        module = sym_id.rsplit(".", 1)[0]
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
        module=module,
    )


def _edge(
    caller_id: str,
    callee_name: str,
    callee_id: str = "",
    file: str = "src/Sample.kt",
    line: int = 10,
    kind: EdgeKind = EdgeKind.CALL,
    callee_signature_hint: str = "",
) -> CallEdge:
    """创建 CallEdge，默认未解析（callee_id 为空）。"""
    return CallEdge(
        caller_id=caller_id,
        callee_name=callee_name,
        file=file,
        line=line,
        kind=kind,
        callee_id=callee_id,
        resolved=bool(callee_id),
        callee_signature_hint=callee_signature_hint,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 测试：签名提取工具方法
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractParamCount:
    """测试 Resolver._extract_param_count 静态方法。"""

    def test_kotlin_signature_no_params(self):
        signature = "fun process()"
        assert Resolver._extract_param_count(signature) == 0

    def test_kotlin_signature_one_param(self):
        signature = "fun process(id: String)"
        assert Resolver._extract_param_count(signature) == 1

    def test_kotlin_signature_two_params(self):
        signature = "fun process(id: String, name: String)"
        assert Resolver._extract_param_count(signature) == 2

    def test_java_signature_two_params(self):
        signature = "public void process(String a, int b)"
        assert Resolver._extract_param_count(signature) == 2

    def test_signature_with_generic_type(self):
        signature = "fun process(list: List<String>, map: Map<String, Int>)"
        assert Resolver._extract_param_count(signature) == 2

    def test_signature_with_nested_generics(self):
        signature = "fun process(items: List<Map<String, Int>>)"
        assert Resolver._extract_param_count(signature) == 1

    def test_signature_with_lambda_param(self):
        signature = "fun process(callback: (String, Int) -> Unit)"
        assert Resolver._extract_param_count(signature) == 1

    def test_empty_signature(self):
        assert Resolver._extract_param_count("") is None

    def test_no_parentheses(self):
        assert Resolver._extract_param_count("some text") is None


# ─────────────────────────────────────────────────────────────────────────────
# 测试：方法重载（签名感知匹配）
# ─────────────────────────────────────────────────────────────────────────────

class TestMethodOverloading:
    """
    方法重载场景：同一个类中有多个同名但参数不同的方法。
    验证签名感知解析能否正确区分重载方法。
    """

    def test_overload_same_file_signature_match(self):
        """
        场景：同文件内有重载方法 process(String) 和 process(Int)。
        调用 process("hello") 应该匹配到 process(String)。
        """
        g = IndexGraph()

        # 两个重载方法在同一文件
        sym1 = _sym(
            "com.example.Handler.process_string",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=10,
            parent_id="com.example.Handler",
            signature="fun process(value: String)",
        )
        sym2 = _sym(
            "com.example.Handler.process_int",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=20,
            parent_id="com.example.Handler",
            signature="fun process(value: Int)",
        )
        # caller 也在同一文件
        caller = _sym(
            "com.example.Handler.handle",
            "handle",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=30,
            parent_id="com.example.Handler",
        )

        for s in [sym1, sym2, caller]:
            g.add_symbol(s)

        # handle 调用 process("hello") —— 1 个参数
        edge = _edge(
            caller_id="com.example.Handler.handle",
            callee_name="process",
            file="src/Handler.kt",
            line=35,
            callee_signature_hint="1",  # 1 个参数
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # process(String) 有 1 个参数，应该匹配到它
        assert edge.callee_id == "com.example.Handler.process_string"

    def test_overload_same_file_signature_match_different_params(self):
        """
        场景：调用 process("hello", 42) —— 2 个参数，
        应该匹配到 process(String, Int)（2 个参数）。
        """
        g = IndexGraph()

        # 两个重载方法在同一文件
        sym1 = _sym(
            "com.example.Handler.process_1",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=10,
            parent_id="com.example.Handler",
            signature="fun process(value: String)",
        )
        sym2 = _sym(
            "com.example.Handler.process_2",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=20,
            parent_id="com.example.Handler",
            signature="fun process(a: String, b: Int)",
        )
        caller = _sym(
            "com.example.Handler.handle",
            "handle",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=30,
            parent_id="com.example.Handler",
        )

        for s in [sym1, sym2, caller]:
            g.add_symbol(s)

        # handle 调用 process("hello", 42) —— 2 个参数
        edge = _edge(
            caller_id="com.example.Handler.handle",
            callee_name="process",
            file="src/Handler.kt",
            line=35,
            callee_signature_hint="2",  # 2 个参数
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # process(String, Int) 有 2 个参数
        assert edge.callee_id == "com.example.Handler.process_2"

    def test_overload_no_signature_hint_fallback(self):
        """
        场景：没有签名提示时，Resolver 应该回退到旧策略（第一个匹配）。
        """
        g = IndexGraph()

        sym1 = _sym(
            "com.example.Handler.process_string",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=10,
            parent_id="com.example.Handler",
            signature="fun process(value: String)",
        )
        sym2 = _sym(
            "com.example.Handler.process_int",
            "process",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=20,
            parent_id="com.example.Handler",
            signature="fun process(value: Int)",
        )
        caller = _sym(
            "com.example.Handler.handle",
            "handle",
            SymbolKind.METHOD,
            file="src/Handler.kt",
            line=30,
            parent_id="com.example.Handler",
        )

        for s in [sym1, sym2, caller]:
            g.add_symbol(s)

        # 没有签名提示 —— 回退到第一个匹配
        edge = _edge(
            caller_id="com.example.Handler.handle",
            callee_name="process",
            file="src/Handler.kt",
            line=35,
            callee_signature_hint="",  # 无签名提示
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # 无签名提示，回退到第一个匹配（按 _by_file 中的顺序）
        assert edge.callee_id == "com.example.Handler.process_string"

    def test_overload_global_ambiguous_with_signature(self):
        """
        场景：全局多个同名符号，但签名不同，
        caller 与任何候选都不同包，但签名能区分。
        """
        g = IndexGraph()

        # 包 com.example.a 中的 process(String)
        sym_a = _sym(
            "com.example.a.Processor.process_1",
            "process",
            SymbolKind.METHOD,
            file="src/a/Processor.kt",
            line=10,
            parent_id="com.example.a.Processor",
            module="com.example.a",
            signature="fun process(value: String)",
        )
        # 包 com.example.b 中的 process(String, Int)
        sym_b = _sym(
            "com.example.b.Processor.process_2",
            "process",
            SymbolKind.METHOD,
            file="src/b/Processor.kt",
            line=10,
            parent_id="com.example.b.Processor",
            module="com.example.b",
            signature="fun process(a: String, b: Int)",
        )
        # caller 在 com.example.c 包中（不同包）
        caller = _sym(
            "com.example.c.Main.run",
            "run",
            SymbolKind.METHOD,
            file="src/c/Main.kt",
            line=5,
            parent_id="com.example.c.Main",
            module="com.example.c",
        )

        for s in [sym_a, sym_b, caller]:
            g.add_symbol(s)

        # run 调用 process("hello") —— 1 个参数
        edge = _edge(
            caller_id="com.example.c.Main.run",
            callee_name="process",
            file="src/c/Main.kt",
            line=10,
            callee_signature_hint="1",  # 1 个参数
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # process(String) 有 1 个参数，应该匹配到它
        assert edge.callee_id == "com.example.a.Processor.process_1"


# ─────────────────────────────────────────────────────────────────────────────
# 测试：相同包调用 / 被调用
# ─────────────────────────────────────────────────────────────────────────────

class TestSamePackageCall:
    """相同包内的调用解析测试。"""

    def test_same_package_call_actual(self):
        """
        场景：caller 和 callee 在同一文件中，且包内有其他同名方法。
        验证同文件优先 > 同包优先。
        """
        g = IndexGraph()

        # UserService.kt 中的符号
        user_service = _sym(
            "com.example.service.UserService",
            "UserService",
            SymbolKind.CLASS,
            file="src/service/UserService.kt",
            line=5,
            module="com.example.service",
        )
        user_service_find = _sym(
            "com.example.service.UserService.find",
            "find",
            SymbolKind.METHOD,
            file="src/service/UserService.kt",
            line=15,
            parent_id="com.example.service.UserService",
            module="com.example.service",
        )
        user_service_save = _sym(
            "com.example.service.UserService.save",
            "save",
            SymbolKind.METHOD,
            file="src/service/UserService.kt",
            line=25,
            parent_id="com.example.service.UserService",
            module="com.example.service",
        )

        # OrderService.kt 中也有 find
        order_service_find = _sym(
            "com.example.service.OrderService.find",
            "find",
            SymbolKind.METHOD,
            file="src/service/OrderService.kt",
            line=15,
            parent_id="com.example.service.OrderService",
            module="com.example.service",
        )

        for s in [user_service, user_service_find, user_service_save, order_service_find]:
            g.add_symbol(s)

        # UserService.save 调用 find（同文件 UserService.kt）
        edge = _edge(
            caller_id="com.example.service.UserService.save",
            callee_name="find",
            file="src/service/UserService.kt",
            line=30,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # 同文件优先：应该解析到 UserService.find（同文件）
        assert edge.callee_id == "com.example.service.UserService.find"

    def test_same_package_no_same_file_actual(self):
        """
        场景：caller 和 callee 同包但不同文件。
        """
        g = IndexGraph()

        # com.example.service 包中的两个类
        user_service = _sym(
            "com.example.service.UserService",
            "UserService",
            SymbolKind.CLASS,
            file="src/service/UserService.kt",
            line=5,
            module="com.example.service",
        )
        user_service_process = _sym(
            "com.example.service.UserService.process",
            "process",
            SymbolKind.METHOD,
            file="src/service/UserService.kt",
            line=15,
            parent_id="com.example.service.UserService",
            module="com.example.service",
        )

        order_service = _sym(
            "com.example.service.OrderService",
            "OrderService",
            SymbolKind.CLASS,
            file="src/service/OrderService.kt",
            line=5,
            module="com.example.service",
        )
        order_service_run = _sym(
            "com.example.service.OrderService.run",
            "run",
            SymbolKind.METHOD,
            file="src/service/OrderService.kt",
            line=15,
            parent_id="com.example.service.OrderService",
            module="com.example.service",
        )

        # com.example.other 包中也有 process
        other_process = _sym(
            "com.example.other.Other.process",
            "process",
            SymbolKind.METHOD,
            file="src/other/Other.kt",
            line=10,
            parent_id="com.example.other.Other",
            module="com.example.other",
        )

        for s in [user_service, user_service_process, order_service, order_service_run, other_process]:
            g.add_symbol(s)

        # OrderService.run 调用 process（caller 在 com.example.service 包）
        edge = _edge(
            caller_id="com.example.service.OrderService.run",
            callee_name="process",
            file="src/service/OrderService.kt",
            line=20,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # 同包优先：caller 包是 com.example.service，应匹配 UserService.process
        assert edge.callee_id == "com.example.service.UserService.process"


# ─────────────────────────────────────────────────────────────────────────────
# 测试：不同包调用 / 被调用
# ─────────────────────────────────────────────────────────────────────────────

class TestDifferentPackageCall:
    """不同包之间的调用解析测试。"""

    def test_different_package_call_global_unique(self):
        """
        场景：caller 在包 A，callee 在包 B，全局范围内 callee_name 唯一。
        Resolver 应该能正确解析。
        """
        g = IndexGraph()

        # com.example.a 包中的 caller
        caller = _sym(
            "com.example.a.Controller.handle",
            "handle",
            SymbolKind.METHOD,
            file="src/a/Controller.kt",
            line=10,
            parent_id="com.example.a.Controller",
            module="com.example.a",
        )

        # com.example.b 包中的 callee（全局唯一）
        callee = _sym(
            "com.example.b.Service.process",
            "process",
            SymbolKind.METHOD,
            file="src/b/Service.kt",
            line=20,
            parent_id="com.example.b.Service",
            module="com.example.b",
        )

        for s in [caller, callee]:
            g.add_symbol(s)

        edge = _edge(
            caller_id="com.example.a.Controller.handle",
            callee_name="process",
            file="src/a/Controller.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        assert edge.callee_id == "com.example.b.Service.process"

    def test_different_package_ambiguous_different_package(self):
        """
        场景：caller 在包 A，callee_name 在多个包中存在（B 和 C 都有）。
        caller 与所有候选都不在同包，Resolver 会选第一个（降级处理）。
        """
        g = IndexGraph()

        # com.example.a 包中的 caller
        caller = _sym(
            "com.example.a.Controller.handle",
            "handle",
            SymbolKind.METHOD,
            file="src/a/Controller.kt",
            line=10,
            parent_id="com.example.a.Controller",
            module="com.example.a",
        )

        # com.example.b 包中的 execute
        helper_b = _sym(
            "com.example.b.Helper.execute",
            "execute",
            SymbolKind.METHOD,
            file="src/b/Helper.kt",
            line=20,
            parent_id="com.example.b.Helper",
            module="com.example.b",
        )

        # com.example.c 包中也有 execute
        helper_c = _sym(
            "com.example.c.Helper.execute",
            "execute",
            SymbolKind.METHOD,
            file="src/c/Helper.kt",
            line=20,
            parent_id="com.example.c.Helper",
            module="com.example.c",
        )

        for s in [caller, helper_b, helper_c]:
            g.add_symbol(s)

        edge = _edge(
            caller_id="com.example.a.Controller.handle",
            callee_name="execute",
            file="src/a/Controller.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        assert edge.resolved is True
        # caller 包是 com.example.a，与 com.example.b 和 com.example.c 都不同包
        # Resolver 会选 candidates[0]（第一个匹配的）
        assert edge.callee_id in [
            "com.example.b.Helper.execute",
            "com.example.c.Helper.execute",
        ]


# ─────────────────────────────────────────────────────────────────────────────
# 测试：边界情况
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_callee_name(self):
        """callee_name 为空时，Resolver 不应解析。"""
        g = IndexGraph()

        caller = _sym(
            "com.example.Main.run",
            "run",
            SymbolKind.METHOD,
            file="src/Main.kt",
            line=10,
        )
        g.add_symbol(caller)

        edge = _edge(
            caller_id="com.example.Main.run",
            callee_name="",
            file="src/Main.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 0
        assert edge.resolved is False
        assert edge.callee_id == ""

    def test_no_matching_symbol(self):
        """callee_name 在图中不存在时，Resolver 不应解析。"""
        g = IndexGraph()

        caller = _sym(
            "com.example.Main.run",
            "run",
            SymbolKind.METHOD,
            file="src/Main.kt",
            line=10,
        )
        g.add_symbol(caller)

        edge = _edge(
            caller_id="com.example.Main.run",
            callee_name="nonExistent",
            file="src/Main.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 0
        assert edge.resolved is False
        assert edge.callee_id == ""

    def test_already_resolved_edge_skipped(self):
        """已经 resolved 的 edge 应该被跳过。"""
        g = IndexGraph()

        caller = _sym(
            "com.example.Main.run",
            "run",
            SymbolKind.METHOD,
            file="src/Main.kt",
            line=10,
        )
        callee = _sym(
            "com.example.Helper.process",
            "process",
            SymbolKind.METHOD,
            file="src/Helper.kt",
            line=20,
        )

        for s in [caller, callee]:
            g.add_symbol(s)

        # 已经 resolved 的 edge
        edge = _edge(
            caller_id="com.example.Main.run",
            callee_name="process",
            callee_id="com.example.Helper.process",
            file="src/Main.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        # 已经 resolved，不应该再解析
        assert count == 0
        assert edge.callee_id == "com.example.Helper.process"

    def test_rebuild_indexes_after_resolve(self):
        """Resolver 解析后应重建反向索引。"""
        g = IndexGraph()

        caller = _sym(
            "com.example.Main.run",
            "run",
            SymbolKind.METHOD,
            file="src/Main.kt",
            line=10,
        )
        callee = _sym(
            "com.example.Helper.process",
            "process",
            SymbolKind.METHOD,
            file="src/Helper.kt",
            line=20,
        )

        for s in [caller, callee]:
            g.add_symbol(s)

        # 未解析的 edge
        edge = _edge(
            caller_id="com.example.Main.run",
            callee_name="process",
            file="src/Main.kt",
            line=15,
        )
        g.add_edge(edge)

        resolver = Resolver(g)
        count = resolver.resolve_all()

        assert count == 1
        # 反向索引应该已重建
        callees = g.callees_of("com.example.Main.run")
        assert "com.example.Helper.process" in callees
