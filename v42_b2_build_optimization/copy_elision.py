"""Snapshot the same updated FULL model before its original owner disposes it."""
import ast
import copy
from .contracts import require


def snapshot_before_dispose(definition, *, fixture=False):
    original = copy.deepcopy(definition)
    hits = []
    for node in ast.walk(definition):
        if isinstance(node, ast.Expr) and ast.unparse(node) == 'captured.append(model.copy())':
            hits.append(node)
    indices = [i for i, n in enumerate(definition.body)
               if ast.unparse(n) == 'model = captured[0]']
    if fixture and not hits and not indices:
        return dict(applied=False, evidence='FAKE_SOURCE_HAS_NO_MODEL_COPY')
    require(len(hits) == len(indices) == 1, 'B2_ORIGINAL_MODEL_COPY_SOURCE_SHAPE')
    i = indices[0]
    require(i + 1 < len(definition.body)
        and ast.unparse(definition.body[i + 1]) == 'try:\n    A, d = arrays(model)\nfinally:\n    model.dispose()',
        'B2_ORIGINAL_MATRIX_EXTRACTION_DISPOSAL_SHAPE')
    # Capture has just set the original P1 objective and called model.update().
    # arrays() returns detached CSR/NumPy values, not a live model reference.
    hits[0].value = ast.parse('captured.append(arrays(model))').body[0].value
    definition.body[i:i + 2] = ast.parse('A, d = captured[0]').body
    restored = copy.deepcopy(definition)
    restored_hits = [n for n in ast.walk(restored) if isinstance(n, ast.Expr)
                     and ast.unparse(n) == 'captured.append(arrays(model))']
    require(len(restored_hits) == 1, 'B2_ARRAY_SNAPSHOT_CAPTURE_SHAPE')
    restored_hits[0].value = ast.parse('captured.append(model.copy())').body[0].value
    restored.body[i:i + 1] = ast.parse('model = captured[0]\ntry:\n    A, d = arrays(model)\nfinally:\n    model.dispose()').body
    require(ast.dump(restored, include_attributes=False) == ast.dump(original, include_attributes=False),
            'B2_COPY_ELISION_CHANGED_SCIENTIFIC_STATEMENTS')
    return dict(applied=True, eliminated_model_copies=1, fresh_FULL_models=1,
        snapshot='ORIGINAL_UPDATED_MODEL_BEFORE_NATIVE_SOLVE_FINALLY_DISPOSE',
        original_native_owner_disposal_preserved=True, scientific_AST_roundtrip_identical=True,
        numeric_constants_changed=False, candidates_removed=0, matrices_reused_from_other_builds=0)
