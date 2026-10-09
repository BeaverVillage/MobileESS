"""Reuse original exact projection, unioning overlapping state intervals once."""
import ast
import inspect
from collections import defaultdict
from contextlib import contextmanager


class Intervals:
    def __init__(self):
        self.rows = defaultdict(list)

    def add(self, site, start, end):
        if end > start:
            self.rows[site].append((start, end))

    def materialize(self):
        result = set()
        for site, intervals in self.rows.items():
            lo = hi = None
            for start, end in sorted(intervals):
                if lo is None:
                    lo, hi = start, end
                elif start <= hi:
                    hi = max(hi, end)
                else:
                    result.update((site, slot) for slot in range(lo, hi))
                    lo, hi = start, end
            if lo is not None:
                result.update((site, slot) for slot in range(lo, hi))
        return result


def routed_prune(original):
    tree = ast.parse(inspect.getsource(original))
    found = [0]
    class Route(ast.NodeTransformer):
        def visit_Expr(self, node):
            if ast.unparse(node) == "states['r1'].update(((d, t) for t in range(int(R), int(R) + rem)))":
                found[0] += 1
                return ast.copy_location(ast.parse('intervals.add(d, int(R), int(R) + rem)').body[0], node)
            return self.generic_visit(node)
    tree = Route().visit(tree)
    if found != [1]:
        raise ValueError('ORIGINAL_R1_INTERVAL_UNION_SOURCE_SHAPE')
    function = tree.body[0]
    function.body.insert(0, ast.parse('intervals = Intervals()').body[0])
    for i, node in enumerate(function.body):
        if (isinstance(node, ast.Assign) and ast.unparse(node).startswith('events = {')
                and 'tuple(sorted(a))' in ast.unparse(node)):
            function.body.insert(i, ast.parse("states['r1'] = intervals.materialize()").body[0])
            break
    else:
        raise ValueError('ORIGINAL_STATE_MATERIALIZATION_SOURCE_SHAPE')
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__, Intervals=Intervals)
    exec(compile(tree, inspect.getfile(original), 'exec'), namespace)
    return namespace[original.__name__]


@contextmanager
def interval_projection():
    import v42_exact.support as support
    original = support.prune
    support.prune = routed_prune(original)
    try:
        yield
    finally:
        support.prune = original
