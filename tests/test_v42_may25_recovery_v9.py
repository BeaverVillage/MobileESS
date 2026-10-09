"""Actual Solver parameter delivery is tested with Native optimize forbidden."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v42_pr134_b1.common import ROOT, atomic, read, sha
from v42_may25_recovery_v9 import numerical, a_stage, storage, coordinator as co, budget, execution
from v42_may25_recovery_v9.policy import ATTEMPT, VERSION, MANIFEST


@pytest.mark.parametrize('day', sorted(numerical.DAYS))
@pytest.mark.parametrize('component', ('PHASE_I', 'ORIGINAL_P1'))
def test_all_31_dates_original_a_policy_delivery(day, component):
    class Model:
        def __init__(self): self.Params = SimpleNamespace()
        def setParam(self, name, value): setattr(self.Params, name, value)
    baseline = dict(Threads=1, Heuristics=.05, MIPGap=.005, Presolve=-1, Method=2, IntFeasTol=1e-5)
    def original(model, policy, gp):
        for name, value in baseline.items(): model.setParam(name, value)
        return dict(baseline)
    with patch.object(numerical, 'original_apply', side_effect=original):
        m = Model(); effective = numerical.apply_precision(m, {}, None, day=day, component=component)
    assert all(effective[k] == v for k, v in numerical.PRECISION.items())
    assert effective['Presolve'] == (0 if component == 'PHASE_I' else -1)
    assert all(effective[k] == v for k, v in baseline.items() if k != 'Presolve')


def test_a_optimizer_and_native_source_reverse_ast_are_preserved():
    from v42_may_build_v6 import a_stage as original
    assert a_stage.prepare is original.prepare
    assert a_stage.SOURCE_PORT_PROOF['reverse_AST_exact']
    with patch.object(a_stage, 'rebound', return_value=lambda *args: 'original-called') as rebind:
        assert a_stage.run({}, object()) == 'original-called'
        assert rebind.call_args.args[0] is original.run
        ns = rebind.call_args.args[1]
        assert ns['_native'] is a_stage._native
        for key, value in original.run.__globals__.items():
            if key != '_native': assert ns[key] is value


def test_actual_gurobi_all_days_b2_entry_has_precision_and_unchanged_model(tmp_path):
    import gurobipy as gp
    from v42_may25_recovery_v9.preflight import native_zero
    # guard denial proves the parameters reach the actual entry without an
    # optimize call; no fake model can claim a scientific certification PASS.
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag', 0); env.start()
        with native_zero() as calls:
            for day in sorted(numerical.DAYS):
                with gp.Model(env=env) as m:
                    x = m.addVar(lb=0, ub=7, obj=3, vtype='I')
                    m.addConstr(2*x <= 10); m.update()
                    before = (m.getA().toarray().copy(), m.getAttr('RHS'), m.getAttr('VType'), m.getAttr('Obj'))
                    m.Params.Heuristics=.05; m.Params.MIPGap=.03
                    b = budget.DateBudget(tmp_path/day/'NATIVE_RUNTIME_LEDGER.json')
                    request = dict(day=day, arm='B2')
                    token = execution._active.set(dict(request=request, preflight_native_zero=True))
                    try:
                        with pytest.raises(PermissionError, match='NATIVE_OPTIMIZE_FORBIDDEN'):
                            b.native_optimize(m, component='P1', track='M_LB')
                    finally:
                        execution._active.reset(token)
                    assert all(getattr(m.Params, k) == v for k, v in numerical.PRECISION.items())
                    assert m.Params.Heuristics == .05 and m.Params.MIPGap == .03 and m.Params.Threads == 1
                    import numpy as np
                    assert np.array_equal(before[0], m.getA().toarray())
                    assert before[1:] == (m.getAttr('RHS'), m.getAttr('VType'), m.getAttr('Obj'))
                    ledger = read(b.path)
                    assert not ledger['calls'] and ledger['measured_Native_Runtime'] == 0
                    assert ledger['admission_failures'][0]['precision_parameters'] == numerical.PRECISION
            assert calls == []


def test_invalid_date_fails_closed():
    with pytest.raises(PermissionError, match='EXACT_MAY_ARM_DATE'):
        numerical.set_precision(object(), day='2025-06-01', component='PHASE_I')


def test_explicit_stop_restores_only_25_26_and_preserves_all_other_rows(tmp_path):
    cp = dict(run_id='fixture', state='HOLD', dates={})
    for arm, day in co.AXIS:
        completed = arm == 'B1' and day <= '2025-05-24'
        cp['dates'][co.key(arm,day)] = dict(arm=arm, day=day,
            status='PASS' if completed else 'PENDING', attempts=int(completed))
    cp['dates']['B1/2025-05-25'].update(status='NUMERICAL_FAILURE', attempts=1, result='immutable_failed_result')
    request_path = tmp_path/'old26/request.json'
    cp['dates']['B1/2025-05-26'].update(status='RUNNING', attempts=1, request=str(request_path))
    old = deepcopy(cp)
    atomic(tmp_path/'boundary.json',cp)
    stop = dict(workers=[dict(day='2025-05-26',worker_dead=True,
        worker=dict(PID=2147483647, created=0, command=['python.exe',str(request_path)]))])
    atomic(tmp_path/'stop.json',stop)
    manifest = dict(run_id=cp['run_id'],implementation=dict(version=VERSION),
        base_checkpoint=dict(path=str(tmp_path/'boundary.json'),sha256=sha(tmp_path/'boundary.json')),
        may26_stop=dict(path=str(tmp_path/'stop.json')))
    with patch('v42_may_mess_build_v7.coordinator.read_actives',return_value={}):
        result = storage.initialize_checkpoint(tmp_path,manifest)
    for name,row in result['dates'].items():
        if name in ('B1/2025-05-25','B1/2025-05-26'):
            assert row['status']=='PENDING' and row['attempts']==0
            assert row['original_attempt']==old['dates'][name]
            assert row['authorized_attempt_id']==ATTEMPT
        else: assert row==old['dates'][name]
    assert sha(tmp_path/'boundary.json') == manifest['base_checkpoint']['sha256']


def test_wrong_stop_request_cannot_reset_may26(tmp_path):
    # The previous test's complete coverage is not needed to reject a live
    # worker. Rejection must occur before any restart checkpoint is written.
    atomic(tmp_path/'boundary.json',dict(dates={}))
    manifest = dict(base_checkpoint=dict(path=str(tmp_path/'boundary.json'),sha256=sha(tmp_path/'boundary.json')))
    with patch('v42_may_mess_build_v7.coordinator.read_actives',return_value={'B1/x':dict(worker=dict(PID=1))}), \
            patch.object(storage,'same_process',return_value=True):
        with pytest.raises(PermissionError,match='NO_RUNNING_PREVIOUS_WORKER'):
            storage.initialize_checkpoint(tmp_path,manifest)
    assert not (tmp_path/'CHECKPOINT_V9.json').exists()


def test_display_binds_v9_and_reuses_certified_gap_only(monkeypatch):
    from v42_may25_recovery_v9 import monitor
    from v42_may_monitor_gap_v8.monitor import gap_info
    assert not gap_info(dict(UB=None,independent_Global_LB=None,Certified_Gap=None,
        progress=dict(MIPGap=.01)))['available']
    row = dict(UB=1.,independent_Global_LB=.997,Certified_Gap=.003,progress={},target_gap=.005)
    assert gap_info(row)['available']
    assert monitor.base.co is co


def test_manifest_cannot_merge_all_date_precision_with_wrong_b2_builder():
    from v42_may25_recovery_v9.policy import BUILD_VERSION
    from v42_b2_build_optimization.builder import VERSION as builder_version
    assert BUILD_VERSION == builder_version
    assert VERSION != builder_version


def test_m_frontier_certified_gap_reaches_display_without_native_gap_alias():
    from v42_may25_recovery_v9.worker import canonical
    from v42_may_monitor_gap_v8.monitor import gap_info
    value = canonical(dict(phase='M_ADAPTIVE_L1', UB=1., global_LB=.98, gap=.02))
    assert value['certified_gap'] == .02
    assert value['independent_Global_LB'] == .98
    assert value['gap_source'] == 'REUSED_M_INDEPENDENT_EXACT_FRONTIER'
    assert 'certified_gap' not in canonical(dict(phase='P1', UB=1., global_LB=.98, gap=.02))
    assert 'certified_gap' not in canonical(dict(phase='M_ADAPTIVE_L1', UB=1., global_LB=2., gap=.02))
    assert not gap_info(dict(UB=1., independent_Global_LB=.98, Certified_Gap=None,
        progress=dict(MIPGap=.001)))['available']
