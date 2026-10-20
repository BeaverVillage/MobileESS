"""Reproduce the defect and independently compare corrected CC4 rows to A1."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r032
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
import gurobipy as gp
from v44.common import read, record, atomic, now
from v44_recovery_r032 import operations as op, cc4_date, parent_admission
from v44.frozen.v43_a2 import adapter
from v42_pr134_b1.native import date_route
from v42_boundary import model
from v42_compact.common import PR97
from v42_temporal.service import bind_forecast
from v42_final.workload import ForecastBook
from v42_may_campaign_native90.preflight import native_zero
from v44 import q250_m4_v2 as q

output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=False)
parent=op.PARENT;a2=parent/'A2';request=read(a2/'request.json')
bundle=read(Path(request['input_folder'])/'NATIVE_INPUT.json');failure=read(a2/'OUTPUT/I/R3.json')
envelope=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv')
kernel=pd.read_csv(a2/'OUTPUT/STATIC/BASE/CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
old_forecast=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp())
new_forecast=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),pd.Timestamp(bundle['day']+'T00:00:00+10:00').timestamp())
event=pd.Timestamp(bundle['issue_time']).timestamp()

def violation(book):
    worst=0.;g=failure['globals']
    for prefix,field in [('CC4','remaining_CC4_Q50_GPUh'),('CC4_reserve_timing','remaining_CC4_reserve_GPUh')]:
        for h in range(24):
            work=book.row(h,event)[field];total=0.
            for t in range(4*h,min(96,4*h+len(envelope))):
                total+=g.get(f'{prefix}_x[{h},{t}]',0.);lag=t-4*h
                worst=max(worst,float(envelope.Q10.iloc[lag]*work-total),float(total-envelope.Q90.iloc[lag]*work))
            worst=max(worst,abs(total+g.get(f'{prefix}_carryout[{h}]',0.)-work))
    return worst

class Captured(Exception): pass
def timing_model(function):
    m=gp.Model('NATIVE0_CC4');m.Params.OutputFlag=0;seen=[]
    def capture(model,book,event_time,*ignored,**kwargs):
        result=bind_forecast(model,book,event_time,kernel,envelope.Q10,envelope.Q90)
        seen.append((book,result));raise Captured()
    function.__globals__['bind_forecast']=capture
    function.__globals__['pd']=SimpleNamespace(Timestamp=pd.Timestamp,read_csv=lambda p:
        SimpleNamespace(kappa=SimpleNamespace(to_numpy=lambda:kernel),Q10=envelope.Q10,Q90=envelope.Q90))
    try:function(m,bundle,{}, {})
    except Captured:pass
    m.update()
    answer=dict(matrix=m.getA(),rhs=np.array(m.getAttr('RHS')),senses=m.getAttr('Sense'),
        names=m.getAttr('VarName'),rows=m.getAttr('ConstrName'),lb=np.array(m.getAttr('LB')),
        ub=np.array(m.getAttr('UB')),types=m.getAttr('VType'),book=seen[0][0],work=seen[0][1])
    m.dispose();return answer

with native_zero() as attempts:
    original,_=adapter.fixed_grid(model,{})
    old=timing_model(original)
    with cc4_date.install(): corrected,changes=adapter.fixed_grid(model,{})
    fixed=timing_model(corrected)
    # The original dated A1 model is an independent, previously certified source
    # of exactly the same CC4 service equations and workload for this day.
    expected=timing_model(date_route(model.planning_grid))
    for key in ('rhs','lb','ub'): assert np.array_equal(fixed[key],expected[key]),key
    for key in ('senses','names','rows','types'): assert fixed[key]==expected[key],key
    assert fixed['matrix'].shape==expected['matrix'].shape and (fixed['matrix']!=expected['matrix']).nnz==0
    assert len(fixed['work']['nominal']['carryout'])==24
    assert len(fixed['work']['reserve']['carryout'])==24
    def guard_state(timing):
        return dict(data=[bundle],n=len(timing['names']),
            reference=SimpleNamespace(matrix=timing['matrix'],rhs=timing['rhs'],senses=np.array(timing['senses'])),
            scientific_descriptor=dict(globals={n:i for i,n in enumerate(timing['names'])}),
            _campaign=dict(output=str(output)))
    guard=cc4_date.check_state(guard_state(fixed))
    rejected=False
    try: cc4_date.check_state(guard_state(old))
    except ValueError as error:
        assert 'COHORT_MISSING' in str(error);rejected=True
    assert rejected
    assert violation(old_forecast)<1e-5 and abs(violation(new_forecast)-1472.8251211027343)<1e-9
    with q.install(op.PERMIT):
        completed=parent_admission.validate(parent,output/'M1_FULL_REPLAY')
    assert completed['PASS'] and not attempts
proof=dict(UTC=now(),PASS=True,sources=op.sources(),Native_optimization_calls=0,
    defect='A2_FIXED_GRID_RECOMPILES_MAY01_DATE_WHILE_CLAIMING_DYNAMIC_DAY_ALREADY_ROUTED',
    incorrect_reference_day='2025-05-01',correct_reference_day=bundle['day'],
    incorrect_old_point_violation=violation(old_forecast),correct_day_old_point_violation=violation(new_forecast),
    corrected_CC4_matrix_RHS_bounds_types_names_identical_to_original_dated_A1=True,
    before_native_guard_rejects_old_incomplete_model=True,before_native_guard_accepts_corrected_model=True,
    original_cohorts=len(old['work']['nominal']['carryout']),corrected_cohorts=24,
    original_CC4_rows=old['matrix'].shape[0],corrected_CC4_rows=fixed['matrix'].shape[0],
    same_completed_M1_full_replay=record(output/'M1_FULL_REPLAY/R032_COMPLETED_M1_COMPATIBILITY.json'),
    M1_plan_reused=True,old_A2_P1_point_bound_or_native_clock_reused=False,
    old_failed_result=record(a2/'RESULT.json'),old_rejected_replay=record(a2/'OUTPUT/I/R3.json'))
atomic(output/'VALIDATION.json',proof)
print(proof)
