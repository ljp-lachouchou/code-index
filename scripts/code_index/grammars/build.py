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

# Grammar 仓库配置：{语言名: (git_url, 子目录(s), git_ref)}
# 子目录为 None 表示仓库根目录即 grammar 根
# 子目录为列表表示同一仓库内多个 grammar 子目录，编译到同一个 .so
# git_ref 为 None 表示用默认分支，否则 checkout 到指定 tag/commit
GRAMMAR_REPOS = {
    "kotlin": (
        "https://github.com/fwcd/tree-sitter-kotlin.git",
        None,
        None,
    ),
    "java": (
        "https://github.com/tree-sitter/tree-sitter-java.git",
        None,
        None,
    ),
    # tree-sitter-swift 新版去掉了 src/parser.c，需要 checkout 带 generated files 的 tag
    "swift": (
        "https://github.com/alex-pinkus/tree-sitter-swift.git",
        None,
        "0.4.3-with-generated-files",
    ),
    # tree-sitter-typescript 仓库内同时有 typescript/ 和 tsx/ 两个 grammar
    "typescript": (
        "https://github.com/tree-sitter/tree-sitter-typescript.git",
        ["typescript", "tsx"],  # 编译到同一个 .so
        None,
    ),
    "objc": (
        "https://github.com/mattmassicotte/tree-sitter-objc.git",
        None,
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


def _clone_or_update(repo_url: str, dest: Path, ref: str | None = None) -> None:
    """克隆或 pull 仓库到 dest。

    Args:
        repo_url: Git 仓库地址
        dest:     目标目录
        ref:      如果指定，克隆后 checkout 到该 ref（tag/commit）
    """
    if dest.exists():
        print(f"  [git pull] {dest}")
        subprocess.run(["git", "-C", str(dest), "pull", "--quiet"], check=True)
    else:
        if ref:
            # 需要完整克隆才能 checkout 到指定 ref
            print(f"  [git clone] {repo_url} → {dest} (ref={ref})")
            subprocess.run(
                ["git", "clone", "--quiet", repo_url, str(dest)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(dest), "checkout", "--quiet", ref],
                check=True,
            )
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

    repo_url, subdirs, ref = GRAMMAR_REPOS[lang]
    repo_dir = clone_dir / f"tree-sitter-{lang}"

    _clone_or_update(repo_url, repo_dir, ref=ref)

    # subdirs 可以是单个目录（str / None）或目录列表（list[str]）
    if subdirs is None:
        grammar_paths = [str(repo_dir)]
    elif isinstance(subdirs, list):
        grammar_paths = [str(repo_dir / sd) for sd in subdirs]
    else:
        grammar_paths = [str(repo_dir / subdirs)]

    out_file = GRAMMARS_DIR / OUTPUT_FILENAMES[lang]

    print(f"  [build] {lang} grammar → {out_file.name}")
    Language.build_library(
        str(out_file),
        grammar_paths,
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
    import argparse

    parser = argparse.ArgumentParser(
        description="编译 tree-sitter grammar 共享库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python build.py                    # 编译所有语言\n"
            "  python build.py typescript         # 位置参数（旧用法）\n"
            "  python build.py --lang typescript  # 选项参数\n"
            "  python build.py --lang kotlin --lang java\n"
        ),
    )
    parser.add_argument(
        "languages",
        nargs="*",
        metavar="LANG",
        help="要编译的语言（位置参数），不指定则编译全部",
    )
    parser.add_argument(
        "--lang", "-l",
        action="append",
        dest="lang_flags",
        metavar="LANG",
        help="要编译的语言（可多次指定）",
    )
    parsed = parser.parse_args()

    # 合并位置参数和 --lang 标志
    langs: list[str] = []
    if parsed.languages:
        langs.extend(parsed.languages)
    if parsed.lang_flags:
        langs.extend(parsed.lang_flags)

    main(langs if langs else None)
