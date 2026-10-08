"""Namespace adapters for the preserved A-stage functions.

No solver, model equations, pricing rule or physical checker is implemented here.
Every routed function retains the existing code object, except the checked native
optimize call which is redirected to the campaign's shared runtime accountant.
"""
import ast
import inspect
import textwrap
import types
from contextlib import contextmanager
from pathlib import Path


class DayDirectory:
    """Route legacy OUT/day and STATIC/day to an isolated request directory."""

    def __init__(self, day, folder):
        self.day, self.folder = day, Path(folder)

    def __truediv__(self, day):
        if day != self.day:
            raise ValueError('A_CAMPAIGN_CROSS_DATE_OUTPUT_FORBIDDEN')
        return self.folder


class InputDirectory:
    def __init__(self, day, folder, prefix=False):
        self.day, self.folder, self.prefix = day, Path(folder), prefix

    def __truediv__(self, key):
        if not self.prefix and key == 'inputs':
            return InputDirectory(self.day, self.folder, True)
        if self.prefix and key == self.day:
            return self.folder
        raise ValueError('A_CAMPAIGN_CROSS_DATE_INPUT_FORBIDDEN')


def rebound(function, namespace):
    """Reuse a code object without mutating any historical module globals."""
    result = types.FunctionType(function.__code__, namespace, function.__name__,
                                function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    result.__doc__ = function.__doc__
    result.__module__ = function.__module__
    result.__qualname__ = function.__qualname__
    return result


def group(module, names, **routing):
    """Related functions share the routed globals, including worker state."""
    namespace = dict(vars(module), **routing)
    for name in names:
        namespace[name] = rebound(getattr(module, name), namespace)
    return namespace


@contextmanager
def native_zero_scope(gp, construction_check=None):
    """Allow original model construction while rejecting every optimize call."""
    original = gp.Model
    checkpoints = [0]

    def checkpoint(force=False):
        checkpoints[0] += 1
        if construction_check is not None and (force or checkpoints[0] % 256 == 0):
            construction_check()

    class StaticOnly(original):
        def __init__(self, *args, **kwargs):
            checkpoint(True)
            super().__init__(*args, **kwargs)
            checkpoint(True)

        def optimize(self, *args, **kwargs):
            raise PermissionError('A_CAMPAIGN_NATIVE_ZERO_PREPARE')

    # Original methods, arguments and returned objects are unchanged. Sparse
    # construction can spend a long time inside a single class/factor call,
    # before its next original progress event. Observe only that wall clock.
    for name in ('addVar', 'addVars', 'addMVar', 'addConstr', 'addConstrs', 'addMConstr', 'update'):
        method = getattr(original, name, None)
        if method is None:
            continue
        def checked(self, *args, _original=method, _force=name in ('update', 'addVars', 'addMVar', 'addConstrs', 'addMConstr'), **kwargs):
            checkpoint(_force)
            result = _original(self, *args, **kwargs)
            if _force:
                checkpoint(True)
            return result
        setattr(StaticOnly, name, checked)

    gp.Model = StaticOnly
    try:
        yield
    finally:
        gp.Model = original


class ConstructionContext:
    """Original builder context plus the shared date clock and root progress."""
    def __init__(self, original, check, report):
        self.original, self.budget_check, self.report = original, check, report

    def __getattr__(self, name):
        return getattr(self.original, name)

    def check(self):
        self.budget_check()
        self.original.check()
        self.budget_check()

    def progress(self, value):
        self.budget_check()
        self.original.progress(value)
        self.report(value)
        self.budget_check()


class ConstructionNative:
    """Delegate the same scientific builder with only its context routed."""
    def __init__(self, original, check, report):
        self.original, self.budget_check, self.report = original, check, report

    def __getattr__(self, name):
        return getattr(self.original, name)

    def build(self, context, *args, **kwargs):
        self.budget_check()
        routed = ConstructionContext(context, self.budget_check, self.report)
        self.report(dict(phase='MODEL_BUILD_ENTER'))
        result = self.original.build(routed, *args, **kwargs)
        self.budget_check()
        self.report(dict(phase='MODEL_BUILD_COMPLETE'))
        return result


def routed_optimize(function, namespace):
    """Change exactly model.optimize(observe) into the shared ledger call."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    changes = []

    class Route(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.func, ast.Attribute) and node.func.attr == 'optimize'
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'model'):
                if (len(node.args) != 1 or not isinstance(node.args[0], ast.Name)
                        or node.args[0].id != 'observe' or node.keywords):
                    raise ValueError('A_NATIVE_OPTIMIZE_SOURCE_SHAPE_DRIFT')
                changes.append(node.lineno)
                return ast.copy_location(ast.Call(
                    func=ast.Name(id='_campaign_optimize', ctx=ast.Load()),
                    args=[ast.Name(id='model', ctx=ast.Load()), node.args[0]],
                    keywords=[]), node)
            return node

    tree = Route().visit(tree)
    if len(changes) != 1:
        raise ValueError('A_NATIVE_ONE_OPTIMIZE_ROUTE_REQUIRED')
    ast.fix_missing_locations(tree)
    exec(compile(tree, inspect.getfile(function), 'exec'), namespace)
    return namespace[function.__name__]


def dated_acceptance(function, expected_classes):
    """Only generalize May12's roster size; retain its P1 gap contract."""
    if type(expected_classes) is not int or expected_classes <= 0:
        raise ValueError('A_COMPLETE_DATE_CLASS_COUNT_REQUIRED')
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    changes = []

    class Count(ast.NodeTransformer):
        def visit_Compare(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.left, ast.Call)
                    and isinstance(node.left.func, ast.Attribute)
                    and isinstance(node.left.func.value, ast.Name)
                    and node.left.func.value.id == 'closure'
                    and node.left.func.attr == 'get'
                    and len(node.left.args) == 1
                    and isinstance(node.left.args[0], ast.Constant)
                    and node.left.args[0].value == 'classes'
                    and len(node.comparators) == 1
                    and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == 130):
                node.comparators[0] = ast.Name(id='_campaign_classes', ctx=ast.Load())
                changes.append(node.lineno)
            return node

        def visit_Constant(self, node):
            if node.value == 'FULL_130_CLASS_DOMAIN_REQUIRED':
                return ast.copy_location(ast.Constant('FULL_DATE_CLASS_DOMAIN_REQUIRED'), node)
            return node

    tree = Count().visit(tree)
    if len(changes) != 1:
        raise ValueError('A_MAY12_CLASS_COUNT_SOURCE_SHAPE_DRIFT')
    ast.fix_missing_locations(tree)
    namespace = dict(function.__globals__, _campaign_classes=expected_classes)
    exec(compile(tree, inspect.getfile(function), 'exec'), namespace)
    return namespace[function.__name__]
