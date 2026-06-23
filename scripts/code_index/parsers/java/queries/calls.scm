; ════════════════════════════════════════════════════════════════════
; Java calls.scm — 调用关系提取 tree-sitter query
; ════════════════════════════════════════════════════════════════════

; ── 方法调用：obj.method() ────────────────────────────────────────────
(method_invocation
  name: (identifier) @callee
  (argument_list) @arguments) @call

; ── 类实例化：new Foo() ───────────────────────────────────────────────
(object_creation_expression
  type: (type_identifier) @callee
  (argument_list) @arguments) @call

; ── 继承关系：extends ─────────────────────────────────────────────────
(superclass
  (type_identifier) @callee) @extends

; ── 实现关系：implements ──────────────────────────────────────────────
(super_interfaces
  (type_list
    (type_identifier) @callee)) @extends
