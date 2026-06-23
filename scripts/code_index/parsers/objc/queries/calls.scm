; ──────────────────────────────────────────────────────────────────────────────
; Objective-C calls.scm — 提取调用关系和继承关系
; ──────────────────────────────────────────────────────────────────────────────

; ── ObjC 消息发送：[receiver selector] ────────────────────────────────────────
(message_expression
  (identifier) @callee) @call

; ── 类继承（: SuperClass）─────────────────────────────────────────────────────
(superclass_reference
  (identifier) @callee) @extends

; ── 协议遵从（<Protocol1, Protocol2>）────────────────────────────────────────
(protocol_qualifiers
  (identifier) @callee) @extends
