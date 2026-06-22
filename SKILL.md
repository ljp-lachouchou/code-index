---
name: code-index
description: >-
  AI 代码语义检索加速器。当 AI 需要查找符号定义、追踪调用链、理解模块结构时，
  优先通过 code-index 工具（VFS 直读或 CLI 查询）替代 grep/search_files，
  大幅减少无关噪声和 token 消耗。
  TRIGGER/USE when: 需要查找类/函数/接口/协议的定义位置；
  需要知道"谁调用了 X"或"X 调用了谁"；
  需要了解某个文件有哪些方法；
  需要查找接口/Protocol 的所有实现类；
  在开始修改代码前需要定位目标文件和行号。
---

你是一位熟练使用 code-index 工具的 AI 开发助手。code-index 已为当前仓库的
Kotlin / Java / Swift / Objective-C / TypeScript 代码建立了完整的语义符号索引，
存储在仓库根目录的 `.index/` 目录下。

**核心原则**：遇到任何代码符号导航需求，**优先走 code-index，禁止直接用 grep / search_files 做符号查找**。

---

## 1. 索引结构概览

```
.index/
├── graph.json                      # 完整符号图（code-index query 的数据源）
└── vfs/                            # 预计算静态文件（直接 cat 即可，零进程启动）
    ├── by-name/<lower_symbol>      # 符号定义（大小写合并，文件名全小写）
    ├── by-file/<escaped_path>      # 文件大纲（路径中 / → __）
    ├── by-kind/<kind>              # 按类型列出所有符号
    ├── callers/<lower_symbol>      # 调用者列表
    ├── callees/<lower_symbol>      # 被调用列表
    └── impls/<lower_symbol>        # 接口/Protocol 实现列表
```

> VFS 文件名全部小写，`DeleteComment` 和 `deleteComment` 都对应 `by-name/deletecomment`。

---

## 2. 工具选择决策树

```
需要查找代码符号？
├── 知道符号名（精确 / 前缀）
│   ├── [首选] cat .index/vfs/by-name/<lower_name>   ← 0ms，无进程启动
│   └── [备选] code-index query <name>               ← 支持通配符、--kind 过滤
│
├── 需要"谁调用了 X？"
│   ├── [首选] cat .index/vfs/callers/<lower_name>
│   └── [备选] code-index callers <name>
│
├── 需要"X 调用了谁？"
│   ├── [首选] cat .index/vfs/callees/<lower_name>
│   └── [备选] code-index callees <name>
│
├── 需要"某文件有哪些方法？"
│   ├── [首选] code-index outline <file_path>
│   └── cat .index/vfs/by-file/<escaped_path>
│
├── 需要"接口/Protocol 有哪些实现？"
│   ├── [首选] cat .index/vfs/impls/<lower_name>
│   └── [备选] code-index impls <name>
│
└── 模糊搜索（不知道全名）
    └── code-index query "*keyword*" [--kind class|method|...] [--lang kotlin|swift|...]
```

---

## 3. 操作手册

### 3.1 ensure_index — 确认索引可用

**在任何查询之前**，先确认索引状态：

```bash
code-index status
```

关键字段解读：
- `Status: ok` 或 `Status: stale` → 索引可用（stale 表示有新文件变更但旧符号仍有效）
- 若显示无索引 → 先构建：`code-index build`（Android 大仓约 5~10 分钟）

> **重要**：不要在每次查询前都重建索引，`build` 仅在索引不存在时才运行。

---

### 3.2 find_symbol — 查找符号定义

#### 方式 A：VFS 直读（首选，0ms）

```bash
# 符号名转小写后直读
cat .index/vfs/by-name/<lower_symbol_name>

# 示例
cat .index/vfs/by-name/deletecomment          # DeleteComment / deleteComment
cat .index/vfs/by-name/commentviewmodel       # CommentViewModel
cat .index/vfs/by-name/iaccountregionservice  # IAccountRegionService（接口）
```

输出格式（直接包含文件路径和行号，无需进一步查找）：
```
Definitions of 'DeleteComment' / 'deleteComment' [N total]
────────────────────────────────────────
com.example.module.ClassName.methodName
  File: features/xxx/src/.../File.kt:123
  Kind: METHOD | Lang: KOTLIN | Visibility: public
  Sig:  fun methodName(param: Type): ReturnType
```

#### 方式 B：CLI 精确/通配查询（复杂模式）

```bash
# 精确匹配
code-index query CommentService

# 前缀匹配（所有 delete 开头的符号）
code-index query "delete*"

# 通配匹配 + 类型过滤
code-index query "*Service" --kind class --lang kotlin
code-index query "*Delegate" --kind protocol --lang swift

# 全限定名后缀匹配
code-index query ".v2.comment.CommentVO"
```

---

### 3.3 find_callers — 谁调用了这个符号？

#### 方式 A：VFS 直读（首选）

```bash
cat .index/vfs/callers/<lower_symbol_name>

# 示例：谁调用了 deleteComment？
cat .index/vfs/callers/deletecomment
```

#### 方式 B：CLI

```bash
code-index callers deleteComment
code-index callers fetchUserProfile --format json
```

---

### 3.4 find_callees — 这个符号调用了什么？

#### 方式 A：VFS 直读（首选）

```bash
cat .index/vfs/callees/<lower_symbol_name>
```

#### 方式 B：CLI

```bash
code-index callees viewDidLoad --lang swift
code-index callees HomeScreen --lang typescript
```

---

### 3.5 file_outline — 查看文件结构

```bash
# CLI（推荐，支持模糊路径）
code-index outline CommentHeaderViewModel.kt
code-index outline features/notedetail/ren_comment_section

# VFS（路径中 / 替换为 __）
cat ".index/vfs/by-file/features__notedetail__xxx__File.kt"
```

---

### 3.6 find_implementations — 查找接口实现

#### 方式 A：VFS 直读（首选）

```bash
cat .index/vfs/impls/<lower_interface_name>

# 示例
cat .index/vfs/impls/icommentrepository       # Kotlin 接口
cat .index/vfs/impls/userserviceprotocol      # Swift Protocol
```

#### 方式 B：CLI

```bash
code-index impls ICommentRepository --lang kotlin
code-index impls UserServiceProtocol --lang swift
```

---

## 4. 典型工作流示例

### 场景 A：修改某个方法前，先找到它在哪

```bash
# Step 1: 查找符号定义（直接得到文件路径+行号）
cat .index/vfs/by-name/deletecomment

# Step 2: 了解谁在调用它（评估改动影响范围）
cat .index/vfs/callers/deletecomment

# Step 3: 用 read_file 读取目标文件（带行号精确定位）
# → read_file path=<上一步输出的 File 路径> offset=<行号-5> limit=60
```

### 场景 B：理解某个类的完整结构

```bash
# Step 1: 查看文件大纲（所有方法一览，不读完整文件）
code-index outline CommentHeaderViewModel.kt

# Step 2: 用 read_file 精确读取感兴趣的方法段落
```

### 场景 C：找到接口的所有实现，选择正确的扩展点

```bash
# Step 1: 查找接口定义
cat .index/vfs/by-name/icommentrepository

# Step 2: 查找所有实现类
cat .index/vfs/impls/icommentrepository

# Step 3: 查看某个实现类文件的大纲
code-index outline RealCommentRepository.kt
```

### 场景 D：理解某个新模块的调用关系

```bash
# Step 1: 找到入口类/函数
code-index query "*Manager" --kind class --lang kotlin

# Step 2: 分析入口调用了什么
cat .index/vfs/callees/<lower_name>

# Step 3: 分析谁在使用这个 Manager
cat .index/vfs/callers/<lower_name>
```

---

## 5. 禁止行为（Token 浪费红线）

| 禁止的做法 | 正确替代 |
|---|---|
| `grep -r "deleteComment" --include="*.kt"` | `cat .index/vfs/by-name/deletecomment` |
| `search_files(regex="deleteComment")` | `cat .index/vfs/by-name/deletecomment` |
| `search_files(regex="class.*Service")` | `code-index query "*Service" --kind class` |
| `find . -name "*.kt" \| xargs grep` | `code-index query <pattern> --lang kotlin` |
| 不看索引直接全量读整个目录 | `code-index outline <file>` 先获取大纲 |

> **为什么？** grep 会扫描 build/ 目录下的编译产物、匹配注释/变量名/字符串，
> 单次搜索返回 60+ 条噪声；code-index 只返回函数/类定义，结果精准。
> VFS 直读不需要启动任何进程，响应时间接近 0ms。

---

## 6. 故障处理

### 索引过期（新建文件未被索引）

```bash
code-index build        # 增量更新（只解析变更文件，通常 < 30s）
code-index build --full # 强制全量重建（索引损坏时使用）
```

### Daemon 预热（可选）

CLI 命令会自动启动 Daemon，无需手动干预。若想提前预热减少首次查询延迟：

```bash
code-index serve        # 后台启动，查询响应 < 10ms
code-index stop         # 停止
```

### 符号找不到

1. 确认符号名拼写（VFS 文件名全小写）
2. 尝试通配：`code-index query "*PartialName*"`
3. 检查索引覆盖语言：`code-index status`
4. 确认不是 build/ 目录下的生成代码（索引默认跳过）

---

## 7. 快速参考卡

```bash
# 状态检查
code-index status

# 符号查找（VFS 首选，0ms）
cat .index/vfs/by-name/<lower_name>     # 定义
cat .index/vfs/callers/<lower_name>     # 调用者
cat .index/vfs/callees/<lower_name>     # 被调用者
cat .index/vfs/impls/<lower_name>       # 接口实现
code-index outline <file_path>          # 文件大纲

# 模糊/过滤查询（CLI）
code-index query "<pattern>" [--kind <kind>] [--lang <lang>]
code-index callers <symbol>
code-index impls <interface>

# 索引维护
code-index build           # 增量更新
code-index build --full    # 强制全量重建
```
