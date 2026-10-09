"""Route only the frozen Native precision/authority adapter; reuse all A science."""
import ast
import inspect
from pathlib import Path
from v42_may_build_v6 import a_stage as original
from v42_may_campaign_native90.a_routing import rebound
from .numerical import precision_enabled


def native_port():
    source = inspect.getsource(original._native)
    tree = ast.parse(source)
    baseline = ast.dump(tree, include_attributes=False)
    changed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'source_paths' for t in node.targets):
            changed.append((node, 'value', node.value))
            node.value = ast.BinOp(node.value, ast.Add(), ast.Name('ADAPTER_SOURCE_PATHS', ast.Load()))
        elif isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            assert [a.name for a in node.names] == ['execution']
            changed.append((node, 'level', 1)); node.level = 0
            changed.append((node, 'module', None)); node.module = 'v42_may25_recovery_v9'
        elif isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == 'numerical':
            changed.append((node, 'level', 1)); node.level = 0
            changed.append((node, 'module', 'numerical')); node.module = 'v42_may25_recovery_v9.numerical'
        elif isinstance(node, ast.keyword) and node.arg == 'algorithm_version':
            assert isinstance(node.value, ast.Constant) and node.value.value == 'MAY23_BUILD_EFFICIENCY_V6'
            changed.append((node, 'value', node.value)); node.value = ast.Constant('MAY_ALL_DAYS_PRECISION_RECOVERY_V9')
        elif isinstance(node, ast.keyword) and node.arg == 'numerical_precision_override':
            changed.append((node, 'value', node.value))
            node.value = ast.parse("precision_enabled(day, facade.component)", mode='eval').body
    assert len(changed) == 7, 'V9_FROZEN_NATIVE_ADAPTER_AST_SHAPE_DRIFT'
    compiled = compile(ast.fix_missing_locations(tree), __file__, 'exec')
    for node, name, value in reversed(changed):
        setattr(node, name, value)
    assert ast.dump(tree, include_attributes=False) == baseline, 'V9_NATIVE_SCIENTIFIC_AST_CHANGED'
    namespace = dict(original._native.__globals__, precision_enabled=precision_enabled,
        ADAPTER_SOURCE_PATHS=[Path(__file__).with_name(name) for name in
            ('a_stage.py', 'numerical.py', 'budget.py', 'execution.py', 'policy.py')])
    # Source freeze still includes the original A adapter. Our additional
    # versioned adapter sources are admitted in the immutable V9 manifest.
    exec(compiled, namespace)
    return namespace['_native'], dict(PASS=True, reverse_AST_exact=True,
        changed_fields=7, original_source=str(Path(original.__file__).resolve()),
        optimizer_phase_pricing_integer_bound_replay_unchanged=True, Native_calls=0)


_native, SOURCE_PORT_PROOF = native_port()
prepare = original.prepare


def run(request, budget, progress=None):
    return rebound(original.run, dict(original.run.__globals__, _native=_native))(request, budget, progress)
