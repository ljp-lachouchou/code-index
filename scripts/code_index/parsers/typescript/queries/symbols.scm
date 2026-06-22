; ──────────────────────────────────────────────────────────────────────────────
; TypeScript symbols.scm — 提取 TS/TSX 代码中的符号定义
; 兼容 tree-sitter-typescript (tree-sitter/tree-sitter-typescript)
; React Native 专项：识别函数式组件（返回 JSX 的箭头函数/函数声明）
; ──────────────────────────────────────────────────────────────────────────────

; ── 类声明 ────────────────────────────────────────────────────────────────────
(class_declaration
  name: (type_identifier) @name) @symbol

; ── 接口声明 ──────────────────────────────────────────────────────────────────
(interface_declaration
  name: (type_identifier) @name) @symbol

; ── 函数声明（普通函数 + React 组件）────────────────────────────────────────
(function_declaration
  name: (identifier) @name) @symbol

; ── 变量声明中的箭头函数 / 函数表达式（含 React 组件）──────────────────────
; const MyComponent = () => <View>...</View>
; const myFunc = function() { ... }
(variable_declarator
  name: (identifier) @name
  value: (arrow_function)) @symbol

(variable_declarator
  name: (identifier) @name
  value: (function_expression)) @symbol

; ── type alias 声明 ───────────────────────────────────────────────────────────
(type_alias_declaration
  name: (type_identifier) @name) @symbol

; ── enum 声明 ─────────────────────────────────────────────────────────────────
(enum_declaration
  name: (identifier) @name) @symbol
