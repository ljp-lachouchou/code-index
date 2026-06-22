"""code-index CLI 主入口。

通过 pyproject.toml 的 [project.scripts] 注册为 `code-index`。

懒加载策略：
  每个子命令的模块只在该子命令实际被调用时才导入，
  避免一次性导入所有子模块（tree-sitter、rich 等重型依赖），
  大幅减少 CLI 冷启动时间。
"""

from __future__ import annotations

import click


class _LazyGroup(click.Group):
    """按需导入子命令模块的 click.Group。"""

    # 子命令名 → (模块相对路径, 命令对象名)
    _COMMANDS: dict[str, tuple[str, str]] = {
        "build":   ("code_index.cli.build",   "build_cmd"),
        "query":   ("code_index.cli.query",   "query_cmd"),
        "callers": ("code_index.cli.callers", "callers_cmd"),
        "callees": ("code_index.cli.callees", "callees_cmd"),
        "outline": ("code_index.cli.outline", "outline_cmd"),
        "impls":   ("code_index.cli.impls",   "impls_cmd"),
        "status":  ("code_index.cli.status",  "status_cmd"),
        "serve":   ("code_index.cli.daemon",  "serve_cmd"),
        "stop":    ("code_index.cli.daemon",  "stop_cmd"),
    }

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._COMMANDS:
            mod_path, attr = self._COMMANDS[cmd_name]
            import importlib
            mod = importlib.import_module(mod_path)
            return getattr(mod, attr)
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(self._COMMANDS)


@click.command(cls=_LazyGroup)
@click.version_option(package_name="code-index", prog_name="code-index")
def main():
    """code-index — AI 代码语义索引工具。

    \b
    常用工作流：
      code-index build                  # 构建索引
      code-index query deleteComment    # 查找符号
      code-index callers deleteComment  # 查找调用者
      code-index outline src/Foo.kt     # 查看文件大纲
      code-index status                 # 查看索引状态
    """
