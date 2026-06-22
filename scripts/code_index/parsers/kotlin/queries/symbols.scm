; ════════════════════════════════════════════════════════════════════
; Kotlin symbols.scm — 符号提取 tree-sitter query
;
; 每个 @symbol 锚点对应一个符号节点，
; 附属捕获（@name / @modifiers 等）提供该符号的元数据。
;
; 注意：fwcd/tree-sitter-kotlin grammar 的 class_declaration 等节点
; 子节点无 field label，需要直接匹配节点类型。
; ════════════════════════════════════════════════════════════════════

; ── 普通类（含 data class / sealed class / abstract class）──────────
(class_declaration
  (modifiers)? @modifiers
  (type_identifier) @name
  (primary_constructor)? @constructor
  (class_body)? @body) @symbol

; ── 接口声明（grammar 中也是 class_declaration，首子节点为 interface）
; 用更宽松的匹配，靠 parser.py 中的 _infer_kind 通过 source text 判断

; ── object 声明（单例）───────────────────────────────────────────────
(object_declaration
  (type_identifier) @name) @symbol

; ── companion object（无名）─────────────────────────────────────────
(companion_object
  (class_body)? @body) @symbol

; ── 顶层函数 ─────────────────────────────────────────────────────────
(function_declaration
  (modifiers)? @modifiers
  (simple_identifier) @name
  (function_value_parameters) @params) @symbol

; ── enum 类声明 ──────────────────────────────────────────────────────
; enum class 也是 class_declaration（已被第一条捕获），此处单独标记 enum_entry
(enum_entry
  (simple_identifier) @name) @symbol

; ── typealias ────────────────────────────────────────────────────────
(type_alias
  (type_identifier) @name) @symbol
