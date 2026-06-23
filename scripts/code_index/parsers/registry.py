"""
解析器注册表

根据文件扩展名查找对应的 Parser 实例。
支持懒加载：grammar 编译后才实例化 Parser。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .base import BaseParser


# grammar 共享库的默认搜索路径
GRAMMARS_DIR = Path(__file__).parent.parent / "grammars"


class ParserRegistry:
    """解析器注册表：扩展名 → BaseParser 实例。

    使用懒加载：首次请求某语言时才实例化 Parser
    （因为实例化需要 grammar .so 文件存在）。
    """

    def __init__(self, grammars_dir: Optional[Path] = None):
        self._grammars_dir = grammars_dir or GRAMMARS_DIR
        self._parsers: dict[str, BaseParser] = {}    # ext → parser
        self._factories: dict[str, callable] = {}    # lang_name → factory func
        self._ext_to_lang: dict[str, str] = {}       # ext → lang_name
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册默认的语言解析器工厂（懒加载）。"""

        # ── Phase 1: Kotlin / Java ─────────────────────────────────────────
        def _kotlin_factory() -> BaseParser:
            from .kotlin.parser import KotlinParser
            return KotlinParser(self._grammar_path("kotlin"))

        def _java_factory() -> BaseParser:
            from .java.parser import JavaParser
            return JavaParser(self._grammar_path("java"))

        # ── Phase 2: Swift / ObjC ──────────────────────────────────────────
        def _swift_factory() -> BaseParser:
            from .swift.parser import SwiftParser
            return SwiftParser(self._grammar_path("swift"))

        def _objc_factory() -> BaseParser:
            from .objc.parser import ObjCParser
            return ObjCParser(self._grammar_path("objc"))

        # ── Phase 3: TypeScript / TSX ──────────────────────────────────────
        def _typescript_factory() -> BaseParser:
            from .typescript.parser import TypeScriptParser
            return TypeScriptParser(self._grammar_path("typescript"))

        # 注册：语言名 → 工厂函数
        self._factories["kotlin"] = _kotlin_factory
        self._factories["java"] = _java_factory
        self._factories["swift"] = _swift_factory
        self._factories["objc"] = _objc_factory
        self._factories["typescript"] = _typescript_factory

        # 注册：扩展名 → 语言名
        self._ext_to_lang.update({
            "kt": "kotlin",
            "kts": "kotlin",
            "java": "java",
            "swift": "swift",
            "m": "objc",
            "h": "objc",
            "mm": "objc",
            "ts": "typescript",
            "tsx": "typescript",
        })

    def _grammar_path(self, lang: str) -> str:
        """查找编译好的 grammar 共享库路径（.so / .dylib）。"""
        candidates = [
            self._grammars_dir / f"{lang}.so",
            self._grammars_dir / f"{lang}.dylib",
            self._grammars_dir / f"languages_{lang}.so",
            self._grammars_dir / f"languages_{lang}.dylib",
            self._grammars_dir / f"tree-sitter-{lang}.so",
            self._grammars_dir / f"tree-sitter-{lang}.dylib",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        raise FileNotFoundError(
            f"找不到 {lang} 的 grammar 共享库，请先运行: make grammars\n"
            f"搜索路径: {self._grammars_dir}"
        )

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        """根据文件路径返回对应的 Parser 实例（懒加载）。

        Returns:
            BaseParser 实例，或 None（不支持的文件类型）
        """
        ext = Path(file_path).suffix.lstrip(".")
        lang = self._ext_to_lang.get(ext)
        if lang is None:
            return None

        if lang not in self._parsers:
            factory = self._factories.get(lang)
            if factory is None:
                return None
            try:
                self._parsers[lang] = factory()
            except FileNotFoundError as e:
                # grammar 未编译，打印警告（仅第一次）并跳过此语言
                import warnings
                warnings.warn(
                    f"\n[code-index] WARNING: {lang} grammar 未编译，该语言的文件将被跳过。\n"
                    f"  请运行: cd scripts && make grammars-{lang}\n"
                    f"  或:     python code_index/grammars/build.py {lang}\n"
                    f"  原因: {e}",
                    stacklevel=4,
                )
                self._parsers[lang] = None  # type: ignore[assignment]  # 标记为"已尝试但失败"
                return None

        return self._parsers[lang]

    def get_parser_for_lang(self, lang: str) -> Optional[BaseParser]:
        """直接按语言名获取 Parser。"""
        # 确保已初始化
        dummy_ext = next(
            (ext for ext, l in self._ext_to_lang.items() if l == lang), None
        )
        if dummy_ext is None:
            return None
        return self.get_parser(f"dummy.{dummy_ext}")

    def supported_extensions(self) -> list[str]:
        """返回所有支持的文件扩展名列表。"""
        return list(self._ext_to_lang.keys())

    def supported_languages(self) -> list[str]:
        """返回所有支持的语言名称列表。"""
        return list(self._factories.keys())

    def available_parsers(self) -> list[str]:
        """返回 grammar 已编译（可用）的语言列表。"""
        result = []
        for lang in self._factories:
            try:
                self._grammar_path(lang)
                result.append(lang)
            except FileNotFoundError:
                pass
        return result


# 全局单例注册表（大多数场景直接用这个）
_default_registry: Optional[ParserRegistry] = None


def get_registry(grammars_dir: Optional[Path] = None) -> ParserRegistry:
    """获取全局注册表单例。"""
    global _default_registry
    if _default_registry is None or grammars_dir is not None:
        _default_registry = ParserRegistry(grammars_dir)
    return _default_registry
