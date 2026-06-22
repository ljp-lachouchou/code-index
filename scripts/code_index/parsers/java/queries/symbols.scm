; ════════════════════════════════════════════════════════════════════
; Java symbols.scm — 符号提取 tree-sitter query
; ════════════════════════════════════════════════════════════════════

; ── 类声明 ────────────────────────────────────────────────────────────
(class_declaration
  name: (identifier) @name
  (class_body)? @body) @symbol

; ── 接口声明 ─────────────────────────────────────────────────────────
(interface_declaration
  name: (identifier) @name
  (interface_body)? @body) @symbol

; ── 枚举声明 ─────────────────────────────────────────────────────────
(enum_declaration
  name: (identifier) @name
  (enum_body)? @body) @symbol

; ── 注解类型声明 ──────────────────────────────────────────────────────
(annotation_type_declaration
  name: (identifier) @name) @symbol

; ── 方法声明 ─────────────────────────────────────────────────────────
(method_declaration
  name: (identifier) @name
  parameters: (formal_parameters) @params
  (type_identifier)? @return_type) @symbol

; ── 构造函数声明 ──────────────────────────────────────────────────────
(constructor_declaration
  name: (identifier) @name
  parameters: (formal_parameters) @params) @symbol
