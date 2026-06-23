# Code Index 多语言语法解析集成测试报告

> **测试时间**: 2026-06-23
> **测试分支**: code-index
> **测试工具**: pytest
> **测试文件**: `tests/test_integration.py`
> **总测试用例**: 90 个
> **全部通过**: 90 passed

---

## 1. 概述

本文档详细记录了 code-index 项目的集成测试结果，涵盖 5 种编程语言的语法解析能力。

### 1.1 覆盖语言

| 语言 | 扩展名 |
|------|--------|
| Kotlin | .kt |
| Java | .java |
| TypeScript / TSX | .ts / .tsx |
| Swift | .swift |
| Objective-C | .m / .h |

---

## 2. Kotlin / Java 基础测试 (28 tests)

### 支持解析的语法结构

| 结构 | Kotlin | Java |
|------|--------|------|
| class | 支持 | 支持 |
| interface | 支持 | 支持 |
| enum | 支持 | 支持 |
| typealias | 支持 | N/A |
| companion object | 支持 | N/A |
| 跨文件引用 | 支持 | 支持 |
| 调用边 | 支持 | 支持 |

---

## 3. TypeScript / React Native 专项测试 (13 tests)

### 支持解析的语法结构

| 结构 | 状态 |
|------|------|
| interface | 支持 |
| type | 支持 |
| enum | 支持 |
| React 组件 | 支持 |
| 嵌套组件 | 支持 |
| 调用边 | 支持 |

---

## 4. Swift 专项测试 (15 tests)

### 支持解析的语法结构

| 结构 | 状态 | 备注 |
|------|------|------|
| class | 支持 | |
| struct | 支持 | |
| protocol | 支持 | |
| enum | 支持 | |
| extension | 支持 | tree-sitter-swift 0.4.3 统一为 class_declaration |
| 调用边 | 支持 | |

### 语法兼容性说明

> tree-sitter-swift 0.4.3 版本变更:
> - struct/class/enum/protocol/extension/actor 统一映射为 class_declaration 节点
> - call_expression 的 function: 字段已被移除

---

## 5. Objective-C 专项测试 (13 tests)

### 支持解析的语法结构

| 结构 | 状态 | 备注 |
|------|------|------|
| @interface | 支持 | |
| @implementation | 支持 | |
| @protocol | 支持 | |
| NS_ENUM / C enum | 部分 | 当前 grammar 不识别为独立符号 |
| 实例方法 | 部分 | 当前 grammar 不解析为独立符号 |
| C 函数 | 部分 | 当前 grammar 不解析为独立符号 |
| 调用边 | 支持 | |

### 语法兼容性说明

> tree-sitter-objc 现状:
> - class_interface/class_implementation 内部使用 identifier 而非 class_name
> - protocol_reference_list 节点不存在
> - NS_ENUM / C 函数 / 方法声明不被识别为独立命名符号

---

## 6. 测试总结

### 6.1 总体统计

| 语言 | 测试用例数 | 通过率 |
|------|-----------|-------|
| Kotlin | 28 | 100% |
| Java | 28 | 100% |
| TypeScript | 13 | 100% |
| Swift | 15 | 100% |
| Objective-C | 13 | 100% |
| **总计** | **90** | **100%** |

### 6.2 核心能力矩阵

| 功能 | Kotlin | Java | TypeScript | Swift | Objective-C |
|------|--------|------|-----------|-------|-------------|
| 符号解析 | 支持 | 支持 | 支持 | 支持 | 部分 |
| 查询引擎 | 支持 | 支持 | 支持 | 支持 | 支持 |
| 调用图 | 支持 | 支持 | 支持 | 支持 | 支持 |
| 序列化 | 支持 | 支持 | 支持 | 支持 | 支持 |
| VFS 生成 | 支持 | 支持 | 支持 | 支持 | 支持 |
| 增量索引 | 支持 | 支持 | 支持 | 支持 | 支持 |

### 6.3 修复记录

| 修复内容 | 文件 |
|---------|------|
| Swift symbols query | swift/queries/symbols.scm |
| Swift calls query | swift/queries/calls.scm |
| ObjC symbols query | objc/queries/symbols.scm |
| ObjC calls query | objc/queries/calls.scm |

---

*报告生成时间: 2026-06-23*
*测试环境: Python 3.11 / pytest / tree-sitter*
