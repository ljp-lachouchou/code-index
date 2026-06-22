; ──────────────────────────────────────────────────────────────────────────────
; Swift symbols.scm — 提取 Swift 代码中的符号定义
; 兼容 tree-sitter-swift (alex-pinkus/tree-sitter-swift)
; ──────────────────────────────────────────────────────────────────────────────

; ── 类声明 ────────────────────────────────────────────────────────────────────
(class_declaration
  name: (type_identifier) @name) @symbol

; ── 结构体声明 ────────────────────────────────────────────────────────────────
(struct_declaration
  name: (type_identifier) @name) @symbol

; ── 协议声明 ──────────────────────────────────────────────────────────────────
(protocol_declaration
  name: (type_identifier) @name) @symbol

; ── Actor 声明（Swift 5.5+）─────────────────────────────────────────────────
(actor_declaration
  name: (type_identifier) @name) @symbol

; ── 扩展声明 ──────────────────────────────────────────────────────────────────
(extension_declaration
  (type_identifier) @name) @symbol

; ── 枚举声明 ──────────────────────────────────────────────────────────────────
(enum_declaration
  name: (type_identifier) @name) @symbol

; ── 顶层函数 / 方法 ───────────────────────────────────────────────────────────
(function_declaration
  name: (simple_identifier) @name) @symbol

; ── 初始化器 ──────────────────────────────────────────────────────────────────
(init_declaration) @symbol

; ── typealias ─────────────────────────────────────────────────────────────────
(typealias_declaration
  name: (type_identifier) @name) @symbol
