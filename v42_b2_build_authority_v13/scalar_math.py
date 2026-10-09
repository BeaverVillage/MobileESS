"""Private per-build memo for the original PCS scalar math arguments only."""
import ast
from contextlib import contextmanager
import hashlib
import math
from pathlib import Path
from types import FunctionType

from .contracts import digest, require, require_sha


class OriginalScalarMathMemo:
    def __init__(self, cos, sin):
        require(callable(cos) and callable(sin), "PCS_ORIGINAL_MATH_FUNCTIONS_REQUIRED")
        self.original = {"cos": cos, "sin": sin}
        self.values = {"cos": {}, "sin": {}}
        self.requests = {"cos": 0, "sin": 0}
        self.evaluations = {"cos": 0, "sin": 0}

    def _call(self, name, angle):
        require(type(angle) is float and math.isfinite(angle), "PCS_ORIGINAL_FINITE_FLOAT_ANGLE_REQUIRED")
        self.requests[name] += 1
        # Float hex preserves the exact source argument, including signed zero.
        key = angle.hex()
        if key not in self.values[name]:
            result = self.original[name](angle)
            require(type(result) is float and math.isfinite(result), "PCS_ORIGINAL_SCALAR_RESULT_REQUIRED")
            self.values[name][key] = result
            self.evaluations[name] += 1
        return self.values[name][key]

    def cos(self, angle):
        return self._call("cos", angle)

    def sin(self, angle):
        return self._call("sin", angle)

    def receipt(self):
        return dict(requests=dict(self.requests), original_math_evaluations=dict(self.evaluations),
            hits={name: self.requests[name] - self.evaluations[name] for name in self.requests},
            exact_argument_key="FLOAT_HEX", result_arithmetic_changed=False,
            cache_scope="ONE_SOURCE_MODEL_BUILD", real_performance_comparison="NOT_RUN")


@contextmanager
def original_pcs_math_scope(module, source, expected_source_sha):
    """Expose an identical PCS function with only private math globals routed.

    The original solve function sees the temporary module attribute within one
    authorized build. Its global math functions and all source bytes remain
    intact. The original pcs_rows object is restored even when construction
    raises; there is no process-wide math patch or persistent scalar cache.
    """
    source = Path(source).resolve()
    require_sha(expected_source_sha)
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_source_sha, "PCS_SOURCE_SHA_DRIFT")
    definition = [node for node in ast.parse(raw.decode("utf-8-sig")).body
        if isinstance(node, ast.FunctionDef) and node.name == "pcs_rows"]
    require(len(definition) == 1, "PCS_ORIGINAL_SOURCE_FUNCTION_REQUIRED")
    original = module.pcs_rows
    require(isinstance(original, FunctionType)
        and Path(original.__code__.co_filename).resolve() == source
        and original.__code__.co_firstlineno == definition[0].lineno,
        "PCS_ORIGINAL_FUNCTION_SOURCE_IDENTITY")
    require(original.__globals__.get("FACES") == 16, "PCS_ORIGINAL_FACES_REQUIRED")
    memo = OriginalScalarMathMemo(original.__globals__["cos"], original.__globals__["sin"])
    globals_copy = dict(original.__globals__, cos=memo.cos, sin=memo.sin)
    routed = FunctionType(original.__code__, globals_copy, original.__name__,
        original.__defaults__, original.__closure__)
    routed.__kwdefaults__ = original.__kwdefaults__
    routed.__annotations__ = dict(original.__annotations__)
    require(routed.__code__ is original.__code__, "PCS_SOURCE_BYTECODE_DRIFT")
    proof = dict(source_sha=expected_source_sha,
        original_pcs_ast_sha=digest(ast.dump(definition[0], include_attributes=False)),
        source_AST_and_bytecode_preserved=True, original_FACES=16,
        original_cos_sin_only=True, coefficient_expressions_changed=False,
        source_globals_unchanged=True, function_restored=False)
    module.pcs_rows = routed
    try:
        yield memo, proof
    finally:
        module.pcs_rows = original
        proof["function_restored"] = module.pcs_rows is original
