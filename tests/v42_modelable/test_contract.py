"""Synthetic authority checks plus April source evidence; no new grid experiments."""
import csv
from copy import deepcopy
import json
import zipfile
from pathlib import Path
import numpy as np
import pytest
from v42_modelable.population import classify, common_arm_population
from v42_modelable.cc4 import april_projection
from v42_modelable.execution import residuals, execution_guard, b0_sanity
from v42_modelable.power import allocate_unknown
from v42_modelable.freeze import ROOT, OUT
from v42_april_port.builder import B0_FLAGS
from v42_final.common import MODEL
from v42_april_b0_v2.reference import build_reference

def read(name): return json.loads((OUT/name).read_text(encoding='utf8'))

@pytest.fixture
def source():
    r=dict(job_uid='one',submit_time='2025-04-01T00:00:00+00:00',runtime_inference_event_time='2025-04-01T01:00:00+00:00',
           GPU_gang=4,Q50_total_seconds=900,service_slots=1,runtime_authority=MODEL,state='PENDING')
    raw=dict(submit_time=r['submit_time'],gpus_requested=4,partition='gpu-h100')
    return r,raw,{'AIDC01':40},{'AIDC01':[40]},'2025-03-31T00:00:00+00:00'

@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),0,-1,True,1.5])
def test_missing_invalid_gpu_never_imputed(source,value):
    row,raw,*rest=source; raw['gpus_requested']=value; row['GPU_gang']=None
    result=classify(row,raw,*rest)
    assert not result['modelable']; assert row['GPU_gang'] is None

@pytest.mark.parametrize('field',['voltage','line_loading','actual_result','May_policy_result','can_timeshift','can_checkpoint_migrate'])
def test_modelability_independent_of_results_and_flexibility(source,field):
    row,raw,*rest=source
    base=classify(row,raw,*rest); row[field]=False
    assert classify(row,raw,*rest)==base
    row[field]=999
    assert classify(row,raw,*rest)==base

def test_absent_site_still_physical(source):
    assert classify(*source)['modelable']

def test_incompatible_request_source_record_not_missing_gpu(source):
    row,raw,*rest=source; row['GPU_gang']=raw['gpus_requested']=96
    r=classify(row,raw,*rest)
    assert r['classification']=='UNMODELABLE_SOURCE_RECORD'
    assert r['reasons']==['NO_COMPATIBLE_CURRENT_WHOLE_GANG_RACK_SITE']

@pytest.mark.parametrize('change',['future_submission','model_not_available','wrong_runtime','missing_runtime','gpu_conflict'])
def test_causal_runtime_and_raw_identity(source,change):
    row,raw,*rest=source
    if change=='future_submission': raw['submit_time']=row['submit_time']='2025-04-02T00:00:00+00:00'
    if change=='model_not_available': rest[-1]='2025-04-03T00:00:00+00:00'
    if change=='wrong_runtime': row['runtime_authority']='requested-walltime'
    if change=='missing_runtime': row['Q50_total_seconds']=None
    if change=='gpu_conflict':
        raw['gpus_requested']=8
        with pytest.raises(ValueError,match='IMMUTABLE_RAW_GPU_CONFLICT'): classify(row,raw,*rest)
        return
    assert not classify(row,raw,*rest)['modelable']

def test_same_population_nonflex_retained_all_arms():
    jobs=[dict(job_uid='flex',GPU_gang=4,runtime_authority=MODEL),dict(job_uid='fixed',GPU_gang=8,runtime_authority=MODEL)]
    arms=common_arm_population(jobs,{'flex'})
    for arm,rows in arms.items():
        assert {r['job_uid'] for r in rows}=={'flex','fixed'}
        assert all(not r['flexibility_enabled'] for r in rows if r['job_uid']=='fixed')
        assert sum(r['GPU_gang'] for r in rows)==12
    with pytest.raises(ValueError,match='FLEX_NOT_SUBSET'): common_arm_population(jobs,{'missing'})

def test_prediction_projection_does_not_interpret_other_rows(tmp_path):
    data=np.full((5,24,2),np.nan); data[1]=3.; data[2]=4.
    path=tmp_path/'prediction.npz'; np.savez_compressed(path,q=data)
    projected,shape=april_projection(path,[1,2])
    assert shape==(5,24,2); assert np.isfinite(projected).all()
    assert (projected[0]==3).all() and (projected[1]==4).all()

def test_unknown_capacity_failure_not_clipped_or_retimed():
    known=np.array([[39.,30.]]*96); unknown=np.full(96,20.)
    before=unknown.copy(); allocated,residual=allocate_unknown(known,unknown,[40,40])
    assert np.array_equal(unknown,before)
    assert np.allclose(allocated.sum(1)+residual,unknown)
    assert np.allclose(residual,9.)
    assert ((known+allocated)<=40).all()

def test_reference_deterministic_no_future_release():
    issue='2025-04-01T00:00:00+00:00'
    fixed=dict(job_uid='running',submit_time=issue,state_at_D1_cutoff='RUNNING',GPU_gang=4,service_slots=0,
        nominal_remaining_seconds=0,runtime_authority=MODEL,source_site=None,source_site_authority=None)
    pending=dict(fixed,job_uid='pending',state_at_D1_cutoff='PENDING',GPU_gang=40,service_slots=1,nominal_remaining_seconds=900)
    args=([fixed,pending],{'AIDC01':40},{'AIDC01':[40]})
    r,a=build_reference(*args,issue_time=issue); rr,aa=build_reference(*args,issue_time=issue)
    assert r==rr and a==aa; assert len(r)==2
    assert [j for j in r if j['job_uid']=='pending'][0]['reason']=='CAUSAL_RELEASE_AUTHORITY_UNAVAILABLE'
    assert not a['workload_drop']

def test_b0_ml_on_actions_off_and_offline_only():
    assert B0_FLAGS['ML_RUNTIME_USED'] and B0_FLAGS['AIDC_PRESENT']
    assert not B0_FLAGS['AIDC_FLEX_OPTIMIZATION'] and not B0_FLAGS['MESS_ACTIVE']
    assert B0_FLAGS['P_MESS']==B0_FLAGS['Q_MESS']==B0_FLAGS['movement']==0
    assert B0_FLAGS['OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY'] and not B0_FLAGS['DA_AC_OPERATIONAL_GATE']
    for k in ['global_optimization','local_p_repair','local_q_repair','schedule_repair','route_repair']:
        assert B0_FLAGS[k]==0

@pytest.mark.parametrize('field',['served_jobs','served_GPUh','AIDC_IT_energy_kWh','AIDC_PCC_energy_kWh','active_AIDC_slots'])
def test_b0_positive_presence_gate_rejects_zero(field):
    metrics={k:1 for k in ['served_jobs','served_GPUh','AIDC_IT_energy_kWh','AIDC_PCC_energy_kWh','active_AIDC_slots']}
    assert b0_sanity(metrics); metrics[field]=0
    with pytest.raises(ValueError): b0_sanity(metrics)

def test_residual_identity_and_alignment():
    r=residuals([[1.,.98]],[[.999,.977]],[[1.006,.974]])
    assert np.allclose(r['e_total'],r['e_model']+r['e_forecast'])
    assert np.allclose(r['r_up'],[[.006,0]]) and np.allclose(r['r_down'],[[0,.006]])
    with pytest.raises(ValueError): residuals([1],[1,2],[1])

@pytest.mark.parametrize('day',range(1,31))
def test_modelable_day_evidence_complete_inputs_no_future_leak(day):
    folder='BUNDLE/DAY_202504%02d/'%day
    p=read(folder+'PLANNING_INPUT_BUNDLE.json'); a=read(folder+'ACTUAL_INPUT_BUNDLE.json')
    assert all(type(r['GPU_gang']) is int and r['GPU_gang']>0 and r['compatible_sites'] and r['runtime_authority']==MODEL for r in p['known_population']+a['post_issue_arrivals'])
    assert not p['future_actual_arrival_IDs_present']
    assert not ({r['job_uid'] for r in p['known_population']} & {r['job_uid'] for r in a['post_issue_arrivals']})
    assert p['flags']['ML_RUNTIME_USED'] and p['flags']['COMMON_CC4_USED']
    assert p['primary_voltage_band_pu']==[.95,1.05]
    assert p['forecast_inputs']['CC4_bound']
    assert read(folder+'POWER_AUTHORITY.json')['May_numerical_coefficients_copied'] is False

def test_all_raw_events_accounted_and_gpu_coverage_not_invented():
    pop=read('POPULATION/APRIL_MODELABILITY_SUMMARY.json')
    assert pop['raw_unique_jobs']==pop['modelable_unique_jobs']+pop['unmodelable_unique_jobs']
    assert pop['raw_events']==pop['modelable_events']+pop['unmodelable_events']
    with (OUT/'POPULATION/V42_UNMODELABLE_WORKLOAD_LEDGER.csv').open(encoding='utf8') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==pop['unmodelable_events']
    assert all(r['source_sha256'] and r['source_member'] and r['exclusion_reason'] for r in rows)
    assert pop['GPUH_COVERAGE']=='NOT_IDENTIFIABLE_FROM_SOURCE' and pop['excluded_GPUh'] is None
    assert pop['missing_GPU_imputed']==0

def test_stop_is_current_reference_and_power_not_unmodelable_raw():
    v=read('FINAL_VERDICT.json')
    assert not v['raw_unmodelable_presence_is_STOP_reason']
    assert v['reference_ready_days']==28 and v['CC4_nominal_capacity_infeasible_days']==15
    assert v['B0_executed_days']==0 and v['voltage_measurements'] is None
    with pytest.raises(ValueError): execution_guard(read('REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json')['audits'])

def test_may_metadata_only_and_final_margin_not_accepted():
    m=read('POPULATION/MAY_RULE_COMPATIBILITY_AUDIT.json')
    assert m['compared_rows']==1649
    assert not m['May_outcomes_used'] and not m['May_Actual_outcomes_read'] and not m['May_metadata_as_numeric_April_donor']
    flags=read('FINAL_FLAGS.json')
    assert not flags['FINAL_MARGIN_ACCEPTED'] and not flags['MAY_USED_FOR_MARGIN_CALIBRATION']
    assert all(flags[k]=='NOT_RUN' for k in ('B1','B2','B3','May','M1_Benders'))

def test_rules_frozen_before_statistics():
    p=read('PREREGISTRATION.json')
    assert p['rules_frozen_before_statistics']
    for stem in ('V42_PHYSICAL_MODELABILITY','V42_FLEXIBILITY_ELIGIBILITY'):
        a=read('POPULATION/'+stem+'_AUTHORITY.json')
        assert a['frozen'] and a['result_independent'] and not a['population_statistics_observed_before_freeze']
