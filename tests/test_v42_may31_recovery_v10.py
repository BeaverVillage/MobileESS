from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ast
import inspect
import pytest
from v42_pr134_b1.common import atomic, read, record, sha
from v42_may31_recovery_v10 import numerical, a_stage, coordinator as co, storage, budget, execution
from v42_may31_recovery_v10.policy import RETRY_DATES, ATTEMPT, VERSION


@pytest.mark.parametrize('day',sorted(numerical.DAYS))
@pytest.mark.parametrize('component',('PHASE_I','ORIGINAL_P1','INTEGER_CONTROL'))
def test_a_precision_reaches_actual_gurobi_without_native_entry(day,component):
    import gurobipy as gp
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag',0);env.start()
        with gp.Model(env=env) as model:
            x=model.addVar(lb=0,ub=7,obj=3,vtype='I');model.addConstr(2*x<=10);model.update()
            before=(model.getA().toarray().copy(),model.getAttr('RHS'),model.getAttr('VType'),model.getAttr('Obj'))
            def original(m,policy,gp):
                for k,v in dict(Threads=1,Method=2,Heuristics=.05,IntFeasTol=1e-5,MIPGap=.005,Presolve=-1).items():m.setParam(k,v)
                return {}
            with patch.object(numerical,'original_apply',side_effect=original):
                effective=numerical.apply_precision(model,{},gp,day=day,component=component)
            assert all(getattr(model.Params,k)==v for k,v in numerical.PRECISION.items())
            assert effective['FeasibilityTol']==1e-9
            assert model.Params.Method==2 and model.Params.Heuristics==.05
            assert model.Params.IntFeasTol==1e-5 and model.Params.MIPGap==.005
            assert model.Params.Presolve==(0 if component=='PHASE_I' else -1)
            import numpy as np
            assert np.array_equal(before[0],model.getA().toarray())
            assert before[1:]==(model.getAttr('RHS'),model.getAttr('VType'),model.getAttr('Obj'))


@pytest.mark.parametrize('text,status,candidate,expected',[
    ('TELEMETRY_CALLBACK_ERROR: ValueError: A_CERTIFIED_LB_UB_CONFLICT',11,False,'NUMERICAL_FAILURE'),
    ('TELEMETRY_CALLBACK_ERROR: ValueError: A_CERTIFIED_LB_UB_CONFLICT',9,True,'NUMERICAL_FAILURE'),
    ('TELEMETRY_CALLBACK_ERROR: unknown callback bug',11,False,'IMPLEMENTATION_FAILURE'),
    ('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED',11,False,'TIME_LIMIT_NO_VALID_INCUMBENT'),
    ('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED',9,True,'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'),
    ('ORIGINAL_NUMERICAL_REPLAY_REJECTED',2,False,'NUMERICAL_FAILURE'),
    ('INPUT_DATE_IDENTITY',2,False,'INPUT_FAILURE')])
def test_callback_failure_is_not_fabricated_timeout(text,status,candidate,expected):
    assert a_stage.failure_classification(RuntimeError(text),status,candidate)==expected


def test_original_scientific_algorithm_and_strict_lb_ub_assertion_remain():
    from v42_may_build_v6 import a_stage as original
    assert a_stage.prepare is original.prepare
    assert a_stage.SOURCE_PORT_PROOF['reverse_AST_exact']
    assert a_stage.RUN_PORT_PROOF['reverse_AST_exact']
    assert a_stage.RUN_PORT_PROOF['changed_fields']==1
    tree=ast.parse(inspect.getsource(original.run))
    assert any(isinstance(n,ast.Compare) and isinstance(n.left,ast.Name) and n.left.id=='upper'
               and isinstance(n.ops[0],ast.Lt) and isinstance(n.comparators[0],ast.Name)
               and n.comparators[0].id=='exact_lb' for n in ast.walk(tree))


def test_only_failed_may31_restarts_and_all_61_other_rows_preserved(tmp_path):
    cp=dict(run_id='fixture',state='HOLD',dates={})
    for arm,day in co.AXIS:
        cp['dates'][co.key(arm,day)]=dict(arm=arm,day=day,status='PASS' if arm=='B1' else 'PENDING',attempts=int(arm=='B1'))
    cp['dates']['B1/2025-05-31'].update(status='TIME_LIMIT_NO_VALID_INCUMBENT',result='immutable_failed_result')
    old=deepcopy(cp);atomic(tmp_path/'boundary.json',cp)
    manifest=dict(run_id='fixture',base_checkpoint=record(tmp_path/'boundary.json'))
    with patch('v42_may25_recovery_v9.coordinator.read_actives',return_value={}):
        result=storage.initialize_checkpoint(tmp_path,manifest)
    assert RETRY_DATES==('2025-05-31',)
    for name,row in result['dates'].items():
        if name=='B1/2025-05-31':
            assert row['status']=='PENDING' and row['attempts']==0
            assert row['original_attempt']==old['dates'][name] and row['authorized_attempt_id']==ATTEMPT
        else: assert row==old['dates'][name]
    assert sha(tmp_path/'boundary.json')==manifest['base_checkpoint']['sha256']


def test_successful_may31_cannot_be_restarted(tmp_path):
    atomic(tmp_path/'boundary.json',dict(dates={'B1/2025-05-31':dict(status='PASS',attempts=1)}))
    with patch('v42_may25_recovery_v9.coordinator.read_actives',return_value={}):
        with pytest.raises(PermissionError,match='EXPLICIT_FAILED'):
            storage.initialize_checkpoint(tmp_path,dict(base_checkpoint=record(tmp_path/'boundary.json')))
    assert not (tmp_path/'CHECKPOINT_V10.json').exists()


def test_prior_date_native_runtime_is_carried_without_old_point_or_bound(tmp_path):
    prior=tmp_path/'prior';prior.mkdir()
    atomic(prior/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=194.44199967384338,inflight=None,
        calls=[dict(Native_Runtime=194.44199967384338,runtime_unavailable=False)]))
    atomic(tmp_path/'boundary.json',dict(dates={'B1/2025-05-31':dict(result=str(prior/'RESULT.json'))}))
    manifest=tmp_path/'manifest.json'
    atomic(manifest,dict(base_checkpoint=record(tmp_path/'boundary.json'),prior_native_ledger=record(prior/'NATIVE_RUNTIME_LEDGER.json')))
    token=execution._active.set(dict(request=dict(arm='B1',day='2025-05-31',manifest=str(manifest))))
    try:
        b=budget.DateBudget(tmp_path/'new/NATIVE_RUNTIME_LEDGER.json')
    finally: execution._active.reset(token)
    assert b.used()==194.44199967384338
    assert b.remaining()==5400-194.44199967384338
    assert b.calls==[] and b.prior_attempt['point_or_bound_transferred'] is False
    b.charge(5)
    ledger=read(b.path)
    assert ledger['measured_Native_Runtime']==199.44199967384338
    assert ledger['date_runtime_reset'] is False


def test_failed_native_runtime_measurement_cannot_be_reused(tmp_path):
    prior=tmp_path/'prior';prior.mkdir()
    atomic(prior/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=0,inflight={'component':'INTEGER_CONTROL'},calls=[]))
    atomic(tmp_path/'boundary.json',dict(dates={'B1/2025-05-31':dict(result=str(prior/'RESULT.json'))}))
    manifest=tmp_path/'manifest.json'
    atomic(manifest,dict(base_checkpoint=record(tmp_path/'boundary.json'),prior_native_ledger=record(prior/'NATIVE_RUNTIME_LEDGER.json')))
    token=execution._active.set(dict(request=dict(arm='B1',day='2025-05-31',manifest=str(manifest))))
    try:
        with pytest.raises(PermissionError,match='UNMEASURED_PRIOR'):
            budget.DateBudget(tmp_path/'new/NATIVE_RUNTIME_LEDGER.json')
    finally: execution._active.reset(token)
