import ast
from copy import deepcopy
from types import SimpleNamespace
import pandas as pd
import pytest
from v44_recovery_r032 import cc4_date as repair
from v44_recovery_r032 import operations as op
from v44_recovery_r032 import fresh_a2, parent_admission
from v44.frozen.v43_a2 import adapter
from v42_boundary import model


class Captured(Exception): pass


def capture_book(function,bundle):
    seen=[]
    def timing(m,book,event,*args,**kwargs):
        seen.append((book,event)); raise Captured()
    function.__globals__['bind_forecast']=timing
    function.__globals__['pd']=SimpleNamespace(Timestamp=pd.Timestamp,
        read_csv=lambda path:SimpleNamespace(kappa=SimpleNamespace(to_numpy=lambda:[]),Q10=[],Q90=[]))
    with pytest.raises(Captured): function(None,bundle,{}, {})
    return seen[0]


@pytest.mark.parametrize('number',range(1,8))
def test_fixed_m1_grid_uses_current_forecast_day(number):
    day=f'2025-05-{number:02d}'
    bundle=dict(day=day,issue_time=(pd.Timestamp(day+'T00:00:00+10:00')-pd.Timedelta(hours=6)).isoformat(),
                C0_Q50=[10.]*24,C0_Q90=[15.]*24)
    with repair.install(): function,changes=adapter.fixed_grid(model,{})
    book,event=capture_book(function,bundle)
    assert book.day_start==pd.Timestamp(day+'T00:00:00+10:00').timestamp()
    assert all(book.row(h,event)['remaining_CC4_Q50_GPUh']==10 for h in range(24))
    assert changes==dict(stage=2,control=1,CC4_calendar='CURRENT_BUNDLE_DAY')
    assert function._v42_dynamic_bundle_day_routed


def test_original_bug_reproduces_missing_early_cohorts():
    bundle=dict(day='2025-05-02',issue_time='2025-05-01T18:00:00+10:00',C0_Q50=[10.]*24,C0_Q90=[15.]*24)
    function,_=adapter.fixed_grid(model,{})
    book,event=capture_book(function,bundle)
    assert [book.row(h,event)['remaining_CC4_Q50_GPUh'] for h in range(24)]==[0.]*18+[10.]*6


def test_only_the_single_calendar_expression_changes():
    tree=adapter.source_tree(model,'planning_grid')
    actual=repair.dated_tree(deepcopy(tree))
    expected=deepcopy(tree)
    timestamp=next(n for n in ast.walk(expected) if isinstance(n,ast.Constant) and n.value=='2025-05-01T00:00:00+10:00')
    # Reversing the one date substitution must restore the entire original AST.
    class Undo(ast.NodeTransformer):
        def visit_BinOp(self,node):
            if ast.unparse(node)=="bundle['day'] + 'T00:00:00+10:00'":
                return deepcopy(timestamp)
            return self.generic_visit(node)
    assert ast.dump(Undo().visit(actual))==ast.dump(expected)


def test_source_shape_drift_fails_closed():
    with pytest.raises(ValueError): repair.dated_tree(ast.parse('x=1'))
    with pytest.raises(ValueError): repair.dated_tree(ast.parse("a='2025-05-01T00:00:00+10:00';b='2025-05-01T00:00:00+10:00'"))


def test_fixed_grid_scope_restores_even_on_exception():
    original=adapter.fixed_grid; source=adapter.source_tree
    with pytest.raises(RuntimeError):
        with repair.install(): raise RuntimeError('test')
    assert adapter.fixed_grid is original and adapter.source_tree is source


def test_completed_parent_compilers_keep_original_replays():
    assert parent_admission.compile_validate().__name__=='validate'
    assert fresh_a2.compiled().__name__=='run'


@pytest.mark.parametrize('entry',[op.ALGORITHM,op.model.ENTRY,op.previous.ENTRY])
def test_all_coordinator_children_use_repaired_entry(entry):
    routed=op.command(['python','-u','-m',entry,'--worker','request'])
    assert routed[3]==op.ENTRY and routed[-2:]==['--algorithm',op.ALGORITHM]


def test_only_exact_failed_and_user_stopped_attempts_are_released():
    assert op.released(op.PARENT) and op.released(op.INTERRUPTED)
    assert not op.released(op.PARENT.with_name('attempt015'))
    assert not op.released(None)


def model_state(tmp_path):
    import numpy as np
    from scipy import sparse
    names=[f'{prefix}_carryout[{h}]' for prefix in ('CC4','CC4_reserve_timing') for h in range(24)]
    snapshot=SimpleNamespace(matrix=sparse.eye(48,format='csr'),rhs=np.array([10.]*24+[5.]*24),senses=np.array(['=']*48))
    return dict(data=[dict(day='2025-05-02',issue_time='2025-05-01T18:00:00+10:00',C0_Q50=[10.]*24,C0_Q90=[15.]*24)],
        n=48,reference=snapshot,scientific_descriptor=dict(globals={n:i for i,n in enumerate(names)}),
        _campaign=dict(output=str(tmp_path)))


def test_model_guard_checks_all_actual_conservation_rhs(tmp_path):
    state=model_state(tmp_path)
    assert len(repair.check_state(state)['checked_cohorts'])==48
    state['reference'].rhs[0]=0
    with pytest.raises(ValueError,match='RHS_DRIFT'):repair.check_state(state)


def test_model_guard_rejects_missing_cohort_before_native(tmp_path):
    state=model_state(tmp_path)
    del state['scientific_descriptor']['globals']['CC4_carryout[0]']
    with pytest.raises(ValueError,match='COHORT_MISSING'):repair.check_state(state)
