; ──────────────────────────────────────────────────────────────────────────────
; Objective-C symbols.scm — 提取 ObjC 代码中的符号定义
; 兼容 tree-sitter-objc (mattmassicotte/tree-sitter-objc)
; ──────────────────────────────────────────────────────────────────────────────

; ── @interface 类声明 ─────────────────────────────────────────────────────────
(class_interface
  (identifier) @name) @symbol

; ── @implementation 实现块 ────────────────────────────────────────────────────
(class_implementation
  (identifier) @name) @symbol

; ── @interface 分类（Category）─────────────────────────────────────────────────
(category_interface
  (identifier) @name) @symbol

; ── @implementation 分类实现 ──────────────────────────────────────────────────
(category_implementation
  (identifier) @name) @symbol

; ── @protocol 协议声明 ────────────────────────────────────────────────────────
(protocol_declaration
  (identifier) @name) @symbol

; ── 方法声明（instance + class）────────────────────────────────────────────────
(method_declaration
  (identifier) @name) @symbol
