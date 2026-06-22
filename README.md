# code-index

多语言代码语义索引工具，让 AI 编码助手
能精准定位代码符号，替代低效的 grep 全文搜索，大幅减少 token 消耗。

支持 Kotlin / Java / Swift / Objective-C / TypeScript，基于 tree-sitter 解析。

## 工作原理

```
仓库代码 → tree-sitter 解析 → 符号图 (.index/graph.json)
                                      ↓
                             VFS 静态文件 (.index/vfs/)
                                      ↓
                          AI 通过 cat 或 CLI 查询（0~10ms）
```

- **VFS 直读**：`cat .index/vfs/by-name/<symbol>` 即可得到定义位置 + 签名，零进程启动
- **CLI 查询**：支持通配符、类型过滤、调用链分析、接口实现查找

## 目录结构

```
code-index/
├── SKILL.md          # AI 使用规则（Claude / Codex / Codewiz 通用）
├── README.md         # 本文件
└── scripts/
    ├── install.sh    # 一键安装
    ├── pyproject.toml
    ├── Makefile
    ├── code_index/   # Python 核心包（解析引擎 + CLI）
    └── tests/
```

## 快速安装

### 方式一：作为 AI Skill 安装到项目（推荐）

```bash
# 克隆到项目，让 AI 自动发现 SKILL.md 规则
git clone <this-repo-url> .codewiz/skills/code-index  # Codewiz / Claude
# 或
git clone <this-repo-url> .cursor/rules/code-index    # Cursor
# 或放在项目根目录的 AGENTS.md 中 @import

# 安装工具
bash .codewiz/skills/code-index/scripts/install.sh

# 构建索引（在仓库根目录执行）
code-index build
```

### 方式二：全局安装（独立使用）

```bash
git clone <this-repo-url>
cd code-index
bash scripts/install.sh

# 在任意仓库目录构建索引
cd /path/to/your/repo
code-index build
```

## 前置条件

- Python >= 3.10
- git（编译 tree-sitter grammar 时需要拉取语法文件）
- pip

## 常用命令

```bash
# 构建 / 更新索引
code-index build                           # 增量更新
code-index build --full                    # 强制全量重建
code-index status                          # 查看索引状态

# 符号查找
code-index query deleteComment             # 精确查找
code-index query "delete*"                 # 前缀匹配
code-index query "*Service" --kind class   # 通配 + 类型过滤
code-index query "*Delegate" --lang swift  # 指定语言

# 调用链分析
code-index callers deleteComment           # 谁调用了它？
code-index callees deleteComment           # 它调用了谁？

# 文件结构
code-index outline CommentViewModel.kt     # 文件大纲

# 接口实现
code-index impls ICommentRepository        # 所有实现类
code-index impls UserServiceProtocol       # Swift Protocol 实现
```

## VFS 静态文件直读（0ms，AI 首选方式）

```bash
# 符号名全部转小写
cat .index/vfs/by-name/deletecomment      # 定义位置 + 签名
cat .index/vfs/callers/deletecomment      # 调用者列表
cat .index/vfs/callees/deletecomment      # 被调用列表
cat .index/vfs/impls/icommentrepository   # 接口实现列表
code-index outline SomeFile.kt            # 文件大纲
```

## 支持语言

| 语言 | CLI 参数 |
|---|---|
| Kotlin + Java（Android） | `--lang kotlin` / `--lang java` |
| Swift + Objective-C（iOS） | `--lang swift` / `--lang objc` |
| TypeScript / TSX（React Native） | `--lang typescript` |

## 为什么不用 grep？

| 指标 | grep | code-index VFS |
|---|---|---|
| 响应时间 | ~500ms（大仓） | ~0ms |
| 结果质量 | 60+ 条（含注释/变量/build 产物） | 精准数条（仅函数/类定义） |
| 包含签名 | 否 | 是 |
| 包含行号 | 否 | 是 |
| token 消耗 | 高（大量噪声） | 极低 |
