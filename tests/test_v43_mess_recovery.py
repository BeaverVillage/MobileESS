import importlib

import pytest

from v43_mess.library import load
from v43_mess.worker import result_fields


def test_real_selective_row_hash_dependency_is_available():
    load()
    module = importlib.import_module('tools.time_decomposed_lb.grid')
    value = module._row_sha(0, 'fixture', '<', 1., [(0, 1.)])
    assert len(value) == 64
    assert value == module._row_sha(0, 'fixture', '<', 1., [(0, 1.)])
    assert value != module._row_sha(0, 'fixture', '<', 2., [(0, 1.)])


def test_beam_pcs_dependency_is_loaded_from_exact_definition_slice():
    from v43_mess.library import dependency_smoke
    load();proof=dependency_smoke()
    assert proof['PASS'] and proof['Native_calls']==0
    module=importlib.import_module('v42_ultracompact.current_verify')
    assert callable(module.physical_pcs_authority)
    assert not any(name in vars(module) for name in ('SAVED','ROOT','CASE','OUT'))


@pytest.mark.parametrize('feasible', [False, True])
def test_full_verdict_and_global_bounds_merge_without_duplicate_keywords(feasible):
    bounds = dict(FULL_feasible=feasible, Global_UB=.7 if feasible else None,
                  Global_LB=.4, global_gap_certified=False)
    result = dict(case_sha='fixture', **result_fields(dict(FULL_validated=feasible), bounds))
    assert result['FULL_feasible'] is feasible
    assert result['PASS'] is feasible
    assert result['Global_LB'] == .4


def test_disagreeing_full_verdict_is_not_silently_overwritten():
    with pytest.raises(ValueError, match='DISAGREE'):
        result_fields(dict(FULL_validated=False), dict(FULL_feasible=True))


def test_inner_beam_failure_is_not_reported_as_normal_budget_exhaustion():
    from v43_mess.worker import execution_status
    ub=dict(FULL_validated=False,adaptive_search=dict(termination_reason='IMPLEMENTATION_OR_NUMERICAL_FAILURE',
        history=[dict(error="NameError('missing')")]))
    result=execution_status(ub,dict(global_gap_certified=False))
    assert result['status']=='IMPLEMENTATION_FAILURE' and not result['M_stage_execution_PASS']
    assert result['implementation_errors']==["NameError('missing')"]


def test_score_lp_cost_never_consumes_native_budget(tmp_path):
    from v43_mess.budget import StageBudget
    from v43.common import read
    from types import SimpleNamespace
    from pathlib import Path
    from uuid import uuid4
    tmp_path=Path('D:/MobileESS_V43/test_temp')/('B2_EXTERNAL_COST_'+uuid4().hex)
    case=SimpleNamespace(case_sha='fixture',identity=dict(arm='B2',stage='M1',source_sha='fixture'))
    b=StageBudget(tmp_path/'EXTERNAL_COST_FIXTURE.json',case=case,kind='PLANNING_NATIVE')
    b.record_external('M_PR222_SCORE_ONLY',.125,solver='HIGHS',status='0')
    saved=read(b.path)
    assert b.used()==0 and b.remaining()==1800. and not b.calls
    assert saved['costs'][0]['wall_seconds']==.125 and not saved['costs'][0]['consumes_native_timeout']
    for seconds in (-1.,float('nan'),float('inf')):
        with pytest.raises(ValueError):b.record_external('BAD',seconds)
    with pytest.raises(ValueError):b.record_external('BAD',1.,solver='GUROBI')


def test_construction_profiling_retains_every_original_math_statement():
    import ast,inspect,textwrap
    from v42_may_campaign_native90.m_model import build_case
    from v43_mess.performance import profiled_build
    tree=profiled_build(build_case)._v43_profiled_ast
    class Unwrap(ast.NodeTransformer):
        def visit_With(self,node):
            node=self.generic_visit(node)
            if (len(node.items)==1 and isinstance(node.items[0].context_expr,ast.Call)
                    and isinstance(node.items[0].context_expr.func,ast.Name)
                    and node.items[0].context_expr.func.id=='_v43_phase'):
                return node.body
            return node
    original=ast.parse(textwrap.dedent(inspect.getsource(build_case)))
    assert ast.dump(Unwrap().visit(tree),include_attributes=False)==ast.dump(original,include_attributes=False)
