;; TypeScript calls.scm -- Extract call relationships, inheritance, JSX component usage
;;
;; Simple function call: func()
(call_expression
  function: (identifier) @callee
  arguments: (arguments) @arguments) @call

;; Method call: obj.method()
(call_expression
  function: (member_expression
    property: (property_identifier) @callee)
  arguments: (arguments) @arguments) @call

;; new expression: new ClassName()
(new_expression
  constructor: (identifier) @callee
  arguments: (arguments) @arguments) @call

;; class extends: class A extends B
(class_declaration
  (class_heritage
    (extends_clause
      value: (identifier) @callee))) @extends

;; interface extends: interface A extends B, C
(interface_declaration
  (extends_type_clause
    (type_identifier) @callee)) @extends

;; JSX component usage (React Native): <MyComponent ... />
(jsx_opening_element
  (identifier) @callee) @call

(jsx_self_closing_element
  (identifier) @callee) @call
