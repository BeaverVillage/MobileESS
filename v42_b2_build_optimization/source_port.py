"""Isolate one original builder; preserve every scientific AST statement."""
import ast
import hashlib
from pathlib import Path

from .contracts import digest, require, require_sha


def instrument_builder(source, namespace, native_inputs, profile, expected_source_sha):
    """Route the original loader and add phase scopes around unchanged bodies.

    Flattening the added scopes must yield the exact original AST, apart from
    one native_inputs import replaced by its same-source immutable input port.
    The proof is evaluated before compilation; no matrix coefficient is edited.
    """
    source = Path(source)
    require_sha(expected_source_sha)
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_source_sha, "B2_BUILDER_SOURCE_SHA_DRIFT")
    tree = ast.parse(raw.decode("utf-8-sig"), filename=str(source))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_case"]
    require(len(functions) == 1, "B2_ORIGINAL_BUILD_CASE_REQUIRED")
    definition = functions[0]
    original_ast = ast.dump(definition, include_attributes=False)
    import_count = 0
    for index, node in enumerate(definition.body):
        if isinstance(node, ast.ImportFrom) and node.module == "v42_bootstrap.m1" and [a.name for a in node.names] == ["native_inputs"]:
            definition.body[index] = ast.copy_location(ast.Assign([ast.Name("native_inputs", ast.Store())],
                ast.Name("_b2_native_inputs", ast.Load())), node)
            import_count += 1
    require(import_count == 1, "B2_NATIVE_INPUT_IMPORT_SHAPE_DRIFT")
    routed_ast = ast.dump(definition, include_attributes=False)
    def target(node, name):
        return isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    starts = [i for i, node in enumerate(definition.body) if target(node, "captured")]
    inputs = [i for i, node in enumerate(definition.body) if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "native_inputs"]
    graph = [i for i, node in enumerate(definition.body) if target(node, "graph")]
    compact = [i for i, node in enumerate(definition.body) if target(node, "compact")]
    proof = [i for i, node in enumerate(definition.body) if isinstance(node, ast.Try) and any(
        isinstance(item, ast.Assign) and isinstance(item.value, ast.Call)
        and isinstance(item.value.func, ast.Name) and item.value.func.id == "verify_transport" for item in node.body)]
    require(len(starts) == len(compact) == len(proof) == len(inputs) == len(graph) == 1
        and inputs[0] < graph[0] < starts[0] < compact[0] < proof[0],
        "B2_BUILD_PHASE_SOURCE_SHAPE_DRIFT")
    boundaries = [(0, inputs[0], "input_preparation"),
        (graph[0], graph[0] + 1, "graph"),
        (graph[0] + 1, starts[0], "input_preparation"),
        (starts[0], compact[0], "full_model"),
        (compact[0], proof[0], "compact_c3a"), (proof[0], proof[0] + 1, "equivalence")]
    boundaries = [boundary for boundary in boundaries if boundary[0] < boundary[1]]
    for begin, end, phase in reversed(boundaries):
        nodes = definition.body[begin:end]
        wrapper = ast.With(items=[ast.withitem(context_expr=ast.Call(func=ast.Attribute(
            ast.Name("_b2_profile", ast.Load()), "phase", ast.Load()), args=[ast.Constant(phase)], keywords=[]), optional_vars=None)], body=nodes)
        definition.body[begin:end] = [ast.copy_location(wrapper, nodes[0])]
    # The added wrappers only time source bodies. Verify no original scientific
    # node was lost, duplicated, reordered or changed while grouping phases.
    class Unwrap(ast.NodeTransformer):
        def visit_With(self, node):
            call = node.items[0].context_expr
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "_b2_profile":
                return [self.visit(child) for child in node.body]
            return self.generic_visit(node)
    import copy
    flattened = Unwrap().visit(copy.deepcopy(definition))
    require(ast.dump(flattened, include_attributes=False) == routed_ast, "B2_BUILD_SCIENTIFIC_AST_DRIFT")
    scope = dict(namespace, _b2_native_inputs=native_inputs, _b2_profile=profile)
    exec(compile(ast.fix_missing_locations(ast.Module([definition], type_ignores=[])), str(source) + ":B2_ISOLATED", "exec"), scope)
    return scope["build_case"], dict(source_sha=expected_source_sha,
        original_ast_sha=digest(original_ast), routed_ast_sha=digest(routed_ast),
        only_loader_routing_and_phase_scopes=True, numeric_constants_changed=False,
        source_statements_preserved=True, FULL_Compact_C3A_builds_preserved=True)
