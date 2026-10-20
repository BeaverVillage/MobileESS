"""Preserve the dated CC4 calendar when generating the fixed-M1 A2 grid."""
import ast
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
import numpy as np
from v44.common import atomic, now

POLICY = 'R032_A2_FIXED_M1_GRID_CC4_BUNDLE_DAY'


def check_state(state):
    """Check actual model conservation rows, before any native optimization."""
    from v42_final.workload import ForecastBook
    import pandas as pd
    bundle = state['data'][0]
    book = ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),
        pd.Timestamp(bundle['day']+'T00:00:00+10:00').timestamp())
    event = pd.Timestamp(bundle['issue_time']).timestamp()
    snapshot = state['reference'];globals = state['scientific_descriptor']['globals']
    columns = snapshot.matrix.tocsc();receipts=[]
    for prefix,field in [('CC4','remaining_CC4_Q50_GPUh'),('CC4_reserve_timing','remaining_CC4_reserve_GPUh')]:
        for h in range(24):
            expected = book.row(h,event)[field];name=f'{prefix}_carryout[{h}]'
            if expected == 0 and name not in globals: continue
            if name not in globals: raise ValueError('R032_CC4_COHORT_MISSING:'+name)
            column = int(globals[name])
            if not 0<=column<state['n']: raise ValueError('R032_CC4_GLOBAL_COLUMN_DRIFT')
            rows=columns.indices[columns.indptr[column]:columns.indptr[column+1]]
            values=columns.data[columns.indptr[column]:columns.indptr[column+1]]
            if (len(rows)!=1 or values[0]!=1 or snapshot.senses[rows[0]]!='='
                    or snapshot.rhs[rows[0]]!=expected):
                raise ValueError('R032_CC4_WORK_CONSERVATION_RHS_DRIFT:'+name)
            receipts.append(dict(cohort=name,work_GPUh=float(expected),row=int(rows[0])))
    proof=dict(UTC=now(),PASS=True,policy=POLICY,day=bundle['day'],checked_cohorts=receipts,
        all_nominal_and_reserve_hours_checked=True,check_before_any_optimization=True)
    atomic(Path(state['_campaign']['output'])/'R032_CC4_MODEL_GUARD.json',proof)
    return proof


def dated_tree(tree):
    count = []
    class Calendar(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == '2025-05-01T00:00:00+10:00':
                count.append(node.lineno)
                return ast.copy_location(ast.parse("bundle['day']+'T00:00:00+10:00'", mode='eval').body, node)
            return node
    result = Calendar().visit(tree)
    if len(count) != 1:
        raise ValueError('R032_EXACT_SINGLE_CC4_DAY_CONSTANT_REQUIRED')
    return ast.fix_missing_locations(result)


@contextmanager
def install():
    from v44.frozen.v43_a2 import adapter
    original_grid, original_tree = adapter.fixed_grid, adapter.source_tree
    original_route = adapter.routed_function

    def fixed_grid(module, mess):
        def source_tree(current, name):
            tree = original_tree(current, name)
            return dated_tree(tree) if current is module and name == 'planning_grid' else tree
        # The original adapter still performs its exact Stage and M1-control
        # substitutions. Only its source tree's date constant is corrected.
        with patch.object(adapter, 'source_tree', source_tree):
            function, changes = original_grid(module, mess)
        function._r032_cc4_bundle_day = True
        return function, dict(changes, CC4_calendar='CURRENT_BUNDLE_DAY')

    def routed_function(module,name,namespace,mess):
        function,changes=original_route(module,name,namespace,mess)
        if name=='verify_case':
            def checked(state):
                value=function(state)
                check_state(state)
                return value
            namespace[name]=checked
            return checked,changes
        return function,changes

    with patch.object(adapter, 'fixed_grid', fixed_grid),patch.object(adapter,'routed_function',routed_function):
        yield
