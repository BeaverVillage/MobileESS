import ast
import copy
import json
import numpy as np
import pytest
from v42_holdout.common import ROOT,OUT,DAYS,BASE,require_may,read,destination
from v42_holdout.calendar_adapter import Calendar,producer
from v42_holdout.actual import adapted_day
from v42_holdout.report import judge,metrics

@pytest.mark.parametrize('day',['2025-04-30','2025-06-01','2025-05-32','2026-05-01'])
def test_frozen_holdout_period_rejects_other_dates(day):
    with pytest.raises(ValueError):require_may(day)

def test_calendar_adapter_only_changes_calendar_ast():
    class Reverse(ast.NodeTransformer):
        def visit_Constant(self,n):
            if isinstance(n.value,str):n.value=n.value.replace('2025-05-','2025-04-').replace('DAY_202505','DAY_202504')
            return n
        def visit_Call(self,n):
            self.generic_visit(n)
            if isinstance(n.func,ast.Name) and n.func.id=='range' and all(isinstance(x,ast.Constant) for x in n.args) and [x.value for x in n.args]==[1,32]:n.args[1].value=31
            return n
    for name in ['v42_capacity/planning.py','v42_capacity/replay.py']:
        original=ast.parse((ROOT/name).read_text(encoding='utf-8'))
        adapted=Calendar().visit(copy.deepcopy(original))
        assert ast.dump(Reverse().visit(adapted))==ast.dump(original)

def test_actual_scientific_loop_is_exactly_PR128():
    runner=adapted_day()
    assert runner.__globals__['BASE']==BASE
    assert runner.__globals__['OUT']==OUT
    assert runner.__globals__['require_april'] is require_may

def test_calendar_adapter_cannot_override_scientific_parameters():
    with pytest.raises(ValueError,match='ONLY_FROZEN_PRODUCER_OUTPUT_ROUTING_ALLOWED'):
        producer('v42_capacity.planning',OUT=OUT,PRIOR=OUT,gamma=0)

@pytest.mark.parametrize('cells,complete,expected',[(0,True,'margin=0 holdout PASS candidate'),(1,True,'margin=0 holdout FAIL'),(99,True,'margin=0 holdout FAIL'),(0,False,'NOT_EVALUABLE_INCOMPLETE_HOLDOUT')])
def test_verdict_does_not_tune_or_use_residual_coverage(cells,complete,expected):
    assert judge(cells,complete=complete,planning_violations=0)==expected

def test_full_31_day_statistics_cannot_drop_bad_days():
    plan=np.ones((31,96,1));actual=plan.copy();actual[-1,-1,0]+=0.02
    stats,cov=metrics(dict(V_PLAN=plan,V_ACTUAL_AC=actual,e_total=actual-plan),DAYS,['x.1'])
    assert stats['points']==2976 and stats['worst_location']['day']=='2025-05-31'
    assert np.isclose(stats['maximum_absolute_error'],.02)
    assert cov['exceedance_days']==['2025-05-31'] and cov['acceptance_gate'] is False

@pytest.mark.parametrize('day',DAYS)
def test_measured_holdout_receipts_and_frozen_arrays(day):
    dest=destination(day);r=read(dest/'FRESH_ACTUAL_AC_RECEIPT.json')
    assert r['converged_slots']==96 and r['all_RegControls_enabled']
    assert r['fixed_capacitors_all_ON'] and r['CapControl_count']==0
    assert not r['Actual_Planning_tap_replay'] and not r['Actual_Planning_cap_replay']
    assert r['Actual_P_repair']==r['Actual_Q_repair']==r['Actual_global_reoptimization']==r['MESS_PQ']==0
    p=np.load(dest/'V_PLAN.npz');a=np.load(dest/'V_ACTUAL_AC.npz');physical=np.load(dest/'ACTUAL_PHYSICAL.npz')
    assert p['V_PLAN'].shape==a['V_ACTUAL_AC'].shape==(96,386)
    assert np.array_equal(p['node_names'],a['node_names'])
    assert np.array_equal(a['PCC_P_kw'],physical['PCC_P_kw']) and np.array_equal(a['PCC_Q_kvar'],physical['PCC_Q_kvar'])
    assert np.all(a['capacitor_states']==1)
    cap=read(dest/'ACTUAL_CAPACITY_RECEIPT.json');assert cap['capacity_violations']==cap['dropped_jobs']==0
    assert cap['actual_IT_kWh']>0 and cap['actual_PCC_kWh']>0 and cap['actual_GPUh']>0

def test_holdout_scope_and_final_margin_not_generalized():
    flags=read(OUT/'FINAL_FLAGS.json');spec=read(OUT/'PREREGISTRATION.json')
    assert spec['margin_pu']==0 and spec['Planning_voltage_band']==[.95,1.05]
    assert spec['days']==list(DAYS) and spec['exact_base']==BASE
    assert all(flags[k]=='NOT_RUN' for k in ['B1','B2','B3','M1','A2','M2'])
    assert flags['FINAL_MARGIN_ACCEPTED'] is False and flags['PROBLEM13_FINAL_VALIDATED'] is False
    assert flags['margin_retuning_calls']==flags['parameter_tuning_calls']==0

def test_all_may_planning_frozen_before_any_private_actual():
    f=read(OUT/'ALL_MAY_PLANNING_FROZEN.json');p=read(OUT/'ACTUAL_PHYSICAL_FREEZE.json')
    assert f['PASS'] and f['days']==list(DAYS)
    assert f['Actual_truth_loaded'] is False and p['all_31_Planning_frozen_before_private_truth']

def test_forecast_vintage_gate_is_pre_actual_and_d1():
    from v42_april_port.builder import timestamp
    vintage=read(OUT/'D1_FORECAST_VINTAGE_CAUSALITY.json')
    assert vintage['PASS'] and vintage['before_first_Actual_AC'] and len(vintage['days'])==31
    for row in vintage['days']:
        assert all(timestamp(t)<=timestamp(row['issue']) for t in row['GFS_initialization_UTC'])
        assert timestamp(row['AEMO_demand_issue'])<=timestamp(row['issue'])
        assert timestamp(row['AEMO_pv_issue'])<=timestamp(row['issue'])
