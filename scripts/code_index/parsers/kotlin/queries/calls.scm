; ════════════════════════════════════════════════════════════════════
; Kotlin calls.scm — 调用关系提取 tree-sitter query
;
; @call    → 函数/方法调用（EdgeKind.CALL）
; @extends → 继承/实现关系（EdgeKind.EXTENDS / IMPLEMENTS）
; ════════════════════════════════════════════════════════════════════

; ── 普通函数调用：foo() ───────────────────────────────────────────────
(call_expression
  (simple_identifier) @callee) @call

; ── 方法调用：obj.method() ────────────────────────────────────────────
; navigation_expression 的结构：simple_identifier + navigation_suffix
(call_expression
  (navigation_expression
    (navigation_suffix
      (simple_identifier) @callee))) @call

; ── 继承/实现关系（delegation_specifier）────────────────────────────
(delegation_specifier
  (user_type
    (type_identifier) @callee)) @extends
