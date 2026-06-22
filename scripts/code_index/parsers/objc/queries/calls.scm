; ──────────────────────────────────────────────────────────────────────────────
; Objective-C calls.scm — 提取调用关系和继承关系
; ──────────────────────────────────────────────────────────────────────────────

; ── ObjC 消息发送：[receiver selector] ────────────────────────────────────────
(message_expression
  (selector) @callee) @call

; ── 类继承（: SuperClass）─────────────────────────────────────────────────────
(superclass_reference
  (class_name) @callee) @extends

; ── 协议遵从（<Protocol1, Protocol2>）────────────────────────────────────────
(protocol_reference_list
  (protocol_name) @callee) @extends
