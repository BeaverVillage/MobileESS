BUILD7BR1 — MOVE-DICTIONARY KEY ARITY RUNTIME FIX

BUILD7B reached the integrated Full-54 model-construction stage and failed before
optimization because one departure-indicator generator unpacked the `mv` dictionary
key incorrectly.

`mv` is defined as:
    mv[(mess_id, horizon_step, route_slot)] = binary_variable

The failed expression iterated the dictionary as if the key were only:
    (horizon_step, route_slot)

R1 changes exactly that departure-indicator expression to iterate the actual 3-tuple
key and to filter both `mess_id` and `horizon_step`.

No variable, physics equation, route authority, SOC equation, grid equation, debt
definition, objective priority, no-look-ahead rule, tolerance, parent authority, or
K9H7_RESULT_V1 contract is changed.

The release test additionally pins the exact BUILD7B failure archive and performs a
static AST audit of every direct iteration over the `mv` dictionary so the same
key-arity class cannot remain elsewhere in `build_full`.
