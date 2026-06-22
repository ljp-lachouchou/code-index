; ──────────────────────────────────────────────────────────────────────────────
; TypeScript calls.scm — 提取调用关系、继承关系、JSX 组件使用
; ──────────────────────────────────────────────────────────────────────────────

; ── 普通函数调用：func() ──────────────────────────────────────────────────────
(call_expression
  function: (identifier) @callee) @call

; ── 方法调用：obj.method() ───────────────────────────────────────────────────
(call_expression
  function: (member_expression
    property: (property_identifier) @callee)) @call

; ── new 构造调用：new ClassName() ────────────────────────────────────────────
(new_expression
  constructor: (identifier) @callee) @call

; ── 类继承：class A extends B ────────────────────────────────────────────────
(class_heritage
  (extends_clause
    value: (identifier) @callee)) @extends

; ── 接口继承：interface A extends B, C ───────────────────────────────────────
(interface_declaration
  (extends_clause
    (type_identifier) @callee)) @extends

; ── JSX 组件使用（React Native）：<MyComponent ... /> ───────────────────────
(jsx_opening_element
  name: (identifier) @callee) @call

(jsx_self_closing_element
  name: (identifier) @callee) @call
