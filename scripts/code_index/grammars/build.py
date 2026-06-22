"""
Grammar 编译脚本

使用 tree-sitter==0.21.* 的 Language.build_library() API 将各语言
grammar 源码编译成共享库（.so/.dylib/.dll）并保存到本目录。

用法：
    python -m code_index.grammars.build          # 编译所有语言
    python -m code_index.grammars.build kotlin   # 只编译 Kotlin
    python -m code_index.grammars.build java     # 只编译 Java

前提：
    pip install tree-sitter==0.21.*
    git（用于克隆 grammar 仓库）
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 本目录（grammars/）
GRAMMARS_DIR = Path(__file__).parent.resolve()

# Grammar 仓库配置：{语言名: (git_url, 子目录)}
# 子目录为 None 表示仓库根目录即 grammar 根
GRAMMAR_REPOS = {
    "kotlin": (
        "https://github.com/fwcd/tree-sitter-kotlin.git",
        None,
    ),
    "java": (
        "https://github.com/tree-sitter/tree-sitter-java.git",
        None,
    ),
    "swift": (
        "https://github.com/alex-pinkus/tree-sitter-swift.git",
        None,
    ),
    "typescript": (
        "https://github.com/tree-sitter/tree-sitter-typescript.git",
        "typescript",  # 仓库内 typescript/ 子目录
    ),
    "objc": (
        "https://github.com/mattmassicotte/tree-sitter-objc.git",
        None,
    ),
}

# 输出 .so 文件名
OUTPUT_FILENAMES = {
    "kotlin":     "languages_kotlin.so",
    "java":       "languages_java.so",
    "swift":      "languages_swift.so",
    "typescript": "languages_typescript.so",
    "objc":       "languages_objc.so",
}


def _clone_or_update(repo_url: str, dest: Path) -> None:
    """克隆或 pull 仓库到 dest。"""
    if dest.exists():
        print(f"  [git pull] {dest}")
        subprocess.run(["git", "-C", str(dest), "pull", "--quiet"], check=True)
    else:
        print(f"  [git clone] {repo_url} → {dest}")
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", repo_url, str(dest)],
            check=True,
        )


def build_grammar(lang: str, clone_dir: Path) -> Path:
    """编译单个语言 grammar，返回 .so 路径。"""
    try:
        from tree_sitter import Language  # type: ignore
    except ImportError:
        print("ERROR: tree-sitter not installed. Run: pip install 'tree-sitter>=0.21,<0.22'")
        sys.exit(1)

    repo_url, subdir = GRAMMAR_REPOS[lang]
    repo_dir = clone_dir / f"tree-sitter-{lang}"

    _clone_or_update(repo_url, repo_dir)

    grammar_path = repo_dir / subdir if subdir else repo_dir
    out_file = GRAMMARS_DIR / OUTPUT_FILENAMES[lang]

    print(f"  [build] {lang} grammar → {out_file.name}")
    Language.build_library(
        str(out_file),
        [str(grammar_path)],
    )
    print(f"  [OK] {out_file}")
    return out_file


def main(langs: list[str] | None = None) -> None:
    """编译所有（或指定）语言的 grammar。"""
    targets = langs or list(GRAMMAR_REPOS.keys())
    unknown = [l for l in targets if l not in GRAMMAR_REPOS]
    if unknown:
        print(f"ERROR: unknown language(s): {', '.join(unknown)}")
        print(f"Available: {', '.join(GRAMMAR_REPOS.keys())}")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="code-index-grammars-") as tmp:
        clone_dir = Path(tmp)
        print(f"\nBuilding {len(targets)} grammar(s): {', '.join(targets)}")
        print(f"Clone dir: {clone_dir}\n")

        success = []
        failed = []
        for lang in targets:
            try:
                build_grammar(lang, clone_dir)
                success.append(lang)
            except Exception as e:
                print(f"  [FAIL] {lang}: {e}")
                failed.append(lang)

    print(f"\n{'='*40}")
    print(f"Built:  {', '.join(success) or '(none)'}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args if args else None)
