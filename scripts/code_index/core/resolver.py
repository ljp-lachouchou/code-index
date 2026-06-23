"""
Resolver — 跨文件符号解析

将 CallEdge 中的 callee_name（原始短名）解析为 callee_id（全限定名）。

策略（按优先级）：
1. 同文件内 + 签名匹配（最高置信度）
2. 同文件内定义的符号（短名匹配）
3. 精确短名匹配（全局唯一）
4. 跨文件短名匹配（有歧义时选最近的包）
5. 无法解析 → callee_id 保持空，resolved = False

签名感知匹配：
当 callee_signature_hint 存在时（如参数个数），
用签名信息辅助区分重载方法，提高解析精度。
"""

from __future__ import annotations

import re

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

        hint = edge.callee_signature_hint

        # 1. 同文件内的符号（最高置信度）
        same_file_ids = self.graph._by_file.get(edge.file, [])
        same_file_matches = []
        for sym_id in same_file_ids:
            sym = self.graph.symbols.get(sym_id)
            if sym and sym.name == callee_name:
                same_file_matches.append(sym_id)

        if len(same_file_matches) == 1:
            return same_file_matches[0]

        # 如果同文件有多个匹配（重载），尝试用签名信息区分
        if len(same_file_matches) > 1 and hint:
            best = self._match_by_signature(same_file_matches, hint)
            if best:
                return best
            # 签名匹配失败，返回第一个（降级）
            return same_file_matches[0]
        elif same_file_matches:
            return same_file_matches[0]

        # 2. 精确短名匹配（全局唯一）
        candidates = self.graph._by_name.get(callee_name, [])
        if len(candidates) == 1:
            return candidates[0]

        # 3. 多候选时：先用签名信息区分
        if len(candidates) > 1:
            if hint:
                best = self._match_by_signature(candidates, hint)
                if best:
                    return best

            # 签名无法区分，优先选与 caller 同包的符号
            caller = self.graph.symbols.get(edge.caller_id)
            if caller and caller.module:
                for cid in candidates:
                    sym = self.graph.symbols.get(cid)
                    if sym and sym.module == caller.module:
                        return cid
            # 没有同包的，选第一个（降级处理）
            return candidates[0]

        return ""

    def _match_by_signature(self, candidate_ids: list[str], hint: str) -> str:
        """根据签名提示（参数个数）在候选中找出最匹配的符号。

        Args:
            candidate_ids: 候选符号 ID 列表
            hint: 签名提示字符串，格式为 "<param_count>"（如 "2" 表示2个参数）

        Returns:
            最匹配的符号 ID，或空字符串表示无法匹配
        """
        if not hint:
            return ""

        try:
            hint_param_count = int(hint)
        except ValueError:
            return ""

        best_match = ""
        best_score = -1

        for sym_id in candidate_ids:
            sym = self.graph.symbols.get(sym_id)
            if not sym or not sym.signature:
                continue

            # 从符号签名中提取参数个数
            param_count = self._extract_param_count(sym.signature)
            if param_count is None:
                continue

            # 参数个数完全匹配
            if param_count == hint_param_count:
                return sym_id  # 精确匹配，直接返回

            # 记录最接近的（参数个数差距最小的）
            score = -abs(param_count - hint_param_count)
            if score > best_score:
                best_score = score
                best_match = sym_id

        return best_match

    @staticmethod
    def _extract_param_count(signature: str) -> int | None:
        """从签名字符串中提取参数个数。

        支持的签名格式：
        - Java:  "public void process(String a, int b)"  → 2
        - Kotlin: "fun process(a: String, b: Int)"     → 2
        - Swift: "func process(_ a: String, b: Int)"    → 2

        Args:
            signature: 签名字符串

        Returns:
            参数个数，或 None 如果无法解析
        """
        if not signature:
            return None

        # 尝试提取括号内的参数部分
        # 匹配各种语言的函数签名模式
        match = re.search(r"[\w\s<>]+\s*\(([^)]*)\)", signature)
        if not match:
            return None

        params_text = match.group(1).strip()
        if not params_text:
            return 0

        # 简单参数分割：按逗号分割，但要跳过模板参数中的逗号
        # 如 Map<String, Int> 不应被分割
        param_count = 0
        depth = 0
        current_param = []

        for char in params_text:
            if char in "<({":
                depth += 1
                current_param.append(char)
            elif char in ">)}" :
                depth -= 1
                current_param.append(char)
            elif char == "," and depth == 0:
                if current_param:
                    param_count += 1
                    current_param = []
            else:
                current_param.append(char)

        # 最后一个参数
        if current_param and any(c.strip() for c in current_param):
            param_count += 1

        return param_count if param_count > 0 else None
