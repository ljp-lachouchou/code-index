; ──────────────────────────────────────────────────────────────────────────────
; Swift calls.scm — 提取调用关系和继承关系
; ──────────────────────────────────────────────────────────────────────────────

; ── 方法调用：receiver.method() ───────────────────────────────────────────────
(call_expression
  function: (navigation_expression
    (navigation_suffix
      (simple_identifier) @callee))) @call

; ── 普通函数调用：func() ──────────────────────────────────────────────────────
(call_expression
  function: (simple_identifier) @callee) @call

; ── 类继承 / 协议遵从（inheritance clause）────────────────────────────────────
(inheritance_specifier
  (user_type
    (type_identifier) @callee)) @extends
