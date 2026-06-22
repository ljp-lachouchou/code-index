"""
Resolver — 跨文件符号解析

将 CallEdge 中的 callee_name（原始短名）解析为 callee_id（全限定名）。

策略（按优先级）：
1. 精确短名匹配（同包内唯一）
2. 同文件内定义的符号（最高置信度）
3. 跨文件短名匹配（有歧义时选最近的包）
4. 无法解析 → callee_id 保持空，resolved = False
"""

from __future__ import annotations

from .model import IndexGraph, CallEdge


class Resolver:
    """跨文件符号解析器。

    在 Indexer 完成全量解析后运行一次，
    尽可能地将 CallEdge.callee_name → callee_id。
    """

    def __init__(self, graph: IndexGraph):
        self.graph = graph

    def resolve_all(self) -> int:
        """解析图中所有未解析的 CallEdge。

        Returns:
            成功解析的 edge 数量
        """
        resolved_count = 0

        for edge in self.graph.edges:
            if edge.resolved:
                continue

            callee_id = self._resolve_edge(edge)
            if callee_id:
                edge.callee_id = callee_id
                edge.resolved = True
                resolved_count += 1

        # 重建反向索引（因为 callee_id 已更新）
        self.graph.rebuild_indexes()
        return resolved_count

    def _resolve_edge(self, edge: CallEdge) -> str:
        """尝试解析单条 CallEdge 的 callee_id。"""
        callee_name = edge.callee_name
        if not callee_name:
            return ""

        # 1. 同文件内的符号（最高置信度）
        same_file_ids = self.graph._by_file.get(edge.file, [])
        for sym_id in same_file_ids:
            sym = self.graph.symbols.get(sym_id)
            if sym and sym.name == callee_name:
                return sym_id

        # 2. 精确短名匹配（全局唯一）
        candidates = self.graph._by_name.get(callee_name, [])
        if len(candidates) == 1:
            return candidates[0]

        # 3. 多候选时：优先选与 caller 同包的符号
        if len(candidates) > 1:
            caller = self.graph.symbols.get(edge.caller_id)
            if caller and caller.module:
                for cid in candidates:
                    sym = self.graph.symbols.get(cid)
                    if sym and sym.module == caller.module:
                        return cid
            # 没有同包的，选第一个（降级处理）
            return candidates[0]

        return ""
