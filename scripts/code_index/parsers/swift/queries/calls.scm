; ──────────────────────────────────────────────────────────────────────────────
; Swift calls.scm — 提取调用关系和继承关系
; 兼容 tree-sitter-swift 0.4.3 (alex-pinkus/tree-sitter-swift)
; 注意：call_expression 结构已变化，不再使用 function: 字段
; ──────────────────────────────────────────────────────────────────────────────

; ── 方法调用：receiver.method() ───────────────────────────────────────────────
(call_expression
  (navigation_expression
    (navigation_suffix
      (simple_identifier) @callee))
  (call_suffix
    (value_arguments) @arguments)) @call

; ── 普通函数调用：func() ──────────────────────────────────────────────────────
(call_expression
  (simple_identifier) @callee
  (call_suffix
    (value_arguments) @arguments)) @call

; ── 类继承 / 协议遵从（inheritance clause）────────────────────────────────────
(class_declaration
  (inheritance_specifier
    (user_type
      (type_identifier) @callee))) @extends
