; ──────────────────────────────────────────────────────────────────────────────
; Objective-C symbols.scm — 提取 ObjC 代码中的符号定义
; 兼容 tree-sitter-objc (mattmassicotte/tree-sitter-objc)
; ──────────────────────────────────────────────────────────────────────────────

; ── @interface 类声明 ─────────────────────────────────────────────────────────
(class_interface
  (class_name) @name) @symbol

; ── @implementation 实现块 ────────────────────────────────────────────────────
(class_implementation
  (class_name) @name) @symbol

; ── @interface 分类（Category）─────────────────────────────────────────────────
(category_interface
  (class_name) @name) @symbol

; ── @implementation 分类实现 ──────────────────────────────────────────────────
(category_implementation
  (class_name) @name) @symbol

; ── @protocol 协议声明 ────────────────────────────────────────────────────────
(protocol_declaration
  (protocol_name) @name) @symbol

; ── 实例方法声明 ──────────────────────────────────────────────────────────────
(instance_method_declaration
  (method_selector) @name) @symbol

; ── 类方法声明 ────────────────────────────────────────────────────────────────
(class_method_declaration
  (method_selector) @name) @symbol

; ── 实例方法定义（implementation 中）─────────────────────────────────────────
(instance_method_definition
  (method_selector) @name) @symbol

; ── 类方法定义（implementation 中）──────────────────────────────────────────
(class_method_definition
  (method_selector) @name) @symbol
