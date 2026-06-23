; ──────────────────────────────────────────────────────────────────────────────
; Swift symbols.scm — 提取 Swift 代码中的符号定义
; 兼容 tree-sitter-swift 0.4.3 (alex-pinkus/tree-sitter-swift)
; 注意：0.4.3 中 class/struct/enum/actor/extension 统一为 class_declaration
; ──────────────────────────────────────────────────────────────────────────────

; ── 类/结构体/枚举/Actor 声明（统一为 class_declaration）────────────────────────
(class_declaration
  name: (type_identifier) @name) @symbol

; ── 协议声明 ──────────────────────────────────────────────────────────────────
(protocol_declaration
  name: (type_identifier) @name) @symbol

; ── 顶层函数 / 方法 ───────────────────────────────────────────────────────────
(function_declaration
  name: (simple_identifier) @name) @symbol

; ── 初始化器 ──────────────────────────────────────────────────────────────────
(init_declaration) @symbol

; ── typealias ─────────────────────────────────────────────────────────────────
(typealias_declaration
  name: (type_identifier) @name) @symbol
