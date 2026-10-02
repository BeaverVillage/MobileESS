"""Small explicit test fixtures only; never exported as April voltage evidence."""
from copy import deepcopy
from pathlib import Path
import ast
import csv
import json
import math
import pytest
from v42_april_b0_v2.contracts import *
from v42_april_b0_v2.reference import build_reference
from v42_april_b0_v2.statistics import *

DAY='2025-04-01'
ISSUE='2025-03-31T18:00:00+10:00'
DOC=Path(__file__).resolve().parents[2]/'docs/v42_april_b0_voltage_margin_calibration_v2'


def flags():
    return dict(B0_ONLY=True,AIDC_PRESENT=True,AIDC_WORKLOAD_PRESENT=True,AIDC_FLEXIBILITY_OPTIMIZATION=False,
                MESS_ACTIVE=False,B1_RUN=False,B2_RUN=False,B3_RUN=False,M1_BENDERS_RUN=False,MAY_RUN=False,
                MAY_USED_FOR_CALIBRATION=False,FINAL_MARGIN_ACCEPTED=False,historical_requested_walltime_fallback=False)


def job(uid='j',gpu=4,n=2,state='PENDING',site=None):
    return dict(job_uid=uid,state_at_D1_cutoff=state,submit_time='2025-03-31T00:00:00+10:00',
                GPU_gang=gpu,service_slots=n,runtime_authority=MODEL,source_site=site,
                source_site_authority='OBSERVED' if site else None)


def reference(jobs):
    return build_reference(jobs,{'AIDC01':4,'AIDC02':4},{'AIDC01':(4,),'AIDC02':(4,)},issue_time=ISSUE)


def frozen():
    rows=[dict(job_id='j',reference_start=0,planning_site='AIDC01',service_slots=2,GPU_gang=4,runtime_authority=MODEL)]
    return freeze_reference(DAY,rows,deepcopy(rows),dict.fromkeys(AUTHORITY_KEYS,'a'*64),flags(),
                            dict.fromkeys(ZERO_ACTIONS,0),dict(P=[0]*96,Q=[0]*96,movement=[0]*96))


def receipt(actual=False):
    f=frozen()
    r=dict(day=DAY,frozen_reference_sha256=f.sha256,common_authority=f.document['authority'],
           controls=dict.fromkeys(ZERO_ACTIONS,0),engine='OpenDSS',fresh=True,synthetic=False,
           physical_arrays_sha256='b'*64,inputs_sha256='c'*64 if actual else 'a'*64,grid_sha256='a'*64)
    if actual:
        r.update(execution_layer='DDAY_ACTUAL',DayAhead_power_arrays_copied=False,
                 IT_recomputed_from_actual_occupancy=True,realized_authority_verified=True)
    else:
        r.update(execution_layer='OFFLINE_CALIBRATION',OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True,operational_gate=False)
    return r


def curves():
    p=[dict(day=DAY,node='n',phase='a',slot=i,timestamp=f'{DAY}T00:{(i+1)*15:02}:00+10:00',voltage_pu=v)
       for i,v in enumerate([1.,1.,1.])]
    d=[dict(r,voltage_pu=v) for r,v in zip(p,[1.002,.998,1.])]
    a=[dict(r,voltage_pu=v) for r,v in zip(p,[1.006,.991,1.])]
    return p,d,a


def evidence(name):
    return json.loads((DOC/name).read_text(encoding='utf8'))


def test_valid_B0_flags_and_explicit_zero_actions():
    validate_flags(flags());validate_controls(dict.fromkeys(ZERO_ACTIONS,0))


@pytest.mark.parametrize('key',list(flags()))
def test_scope_flags_cannot_be_changed(key):
    f=flags();f[key]=not f[key]
    with pytest.raises(ValueError,match='SCOPE'):validate_flags(f)


@pytest.mark.parametrize('action',ZERO_ACTIONS)
def test_flex_MESS_and_actual_actions_forbidden(action):
    r=receipt(actual=True);r['controls'][action]=1
    with pytest.raises(ValueError,match='ACTION_FORBIDDEN'):replay_receipt(frozen(),r,actual=True)


def test_zero_flags_do_not_substitute_for_nonzero_physical_AIDC():
    r=dict(AIDC_PRESENT=True,it_energy_kwh=1.,pcc_energy_kwh=2.,active_slots=1,served_workload=1,
           common_workload_sha256='a'*64,workload_dropped=False)
    presence(r,'a'*64)
    for field in ('it_energy_kwh','pcc_energy_kwh','active_slots','served_workload'):
        bad=dict(r);bad[field]=0
        with pytest.raises(ValueError,match='NONZERO'):presence(bad,'a'*64)


def test_AIDC_off_and_workload_drop_rejected():
    with pytest.raises(ValueError,match='AIDC_OFF'):presence({'AIDC_PRESENT':False},'a'*64)
    f=frozen();rows=f.document['jobs']
    with pytest.raises(ValueError,match='WORKLOAD_DROP'):
        freeze_reference(DAY,rows,[],f.document['authority'],flags(),f.document['controls'],f.document['mess'])


def test_reference_frozen_detached_and_pair_identical():
    f=frozen();copy=f.document;copy['jobs'][0]['GPU_gang']=1
    assert f.document['jobs'][0]['GPU_gang']==4
    pair_receipts(f,receipt(),receipt(True))
    r=receipt(True);r['frozen_reference_sha256']='e'*64
    with pytest.raises(ValueError,match='FROZEN_REFERENCE_CHANGED'):pair_receipts(f,receipt(),r)


def test_common_service_changed_rejected():
    f=frozen();rows=f.document['jobs'];changed=deepcopy(rows);changed[0]['service_slots']=1
    with pytest.raises(ValueError,match='COMMON_WORKLOAD_CHANGED'):
        freeze_reference(DAY,rows,changed,f.document['authority'],flags(),f.document['controls'],f.document['mess'])


def test_historical_requested_runtime_cannot_be_promoted():
    jobs=[job()];jobs[0]['runtime_authority']='REQUESTED_WALLTIME'
    rows,a=reference(jobs)
    assert a['blocked_jobs']==1 and not a['workload_drop']
    assert rows[0]['reason']=='CURRENT_RUNTIME_SERVICE_AUTHORITY_MISSING'


def test_missing_reference_fields_no_longer_stop_generator():
    rows,a=reference([job()])
    assert rows[0]['reference_site']=='AIDC01' and rows[0]['reference_start']==0
    assert rows[0]['fallback_used'] and a['full_reference_ready']


def test_deterministic_placement_independent_of_input_order():
    jobs=[job('a'),job('b'),job('c')]
    a,ra=reference(jobs);b,rb=reference(list(reversed(jobs)))
    assert a==b
    assert [(j['reference_site'],j['reference_start']) for j in a]==[('AIDC01',0),('AIDC02',0),('AIDC01',2)]


def test_current_source_site_kept_without_relocation():
    rows,a=reference([job('a',site='AIDC02'),job('b',site='AIDC02')])
    assert [r['reference_site'] for r in rows]==['AIDC02','AIDC02']
    assert [r['reference_start'] for r in rows]==[0,2]
    assert a['fallback_jobs']==0


def test_running_observed_site_preserved_before_fallback():
    rows,a=reference([job('a',state='RUNNING'),job('b',state='RUNNING',site='AIDC01')])
    assert rows[1]['reference_site']=='AIDC01' and rows[0]['reference_site']=='AIDC02'
    assert all(r['physical_running_retained'] for r in rows)


def test_running_Q50_expiry_does_not_invent_physical_completion():
    rows,a=reference([job('r',n=0,state='RUNNING',site='AIDC01'),job('p',site='AIDC01')])
    assert rows[1]['q50_expired_hard_occupancy'] and not rows[1]['synthetic_completion']
    assert rows[0]['reason']=='CAUSAL_RELEASE_AUTHORITY_UNAVAILABLE'


def test_missing_GPU_row_retained_and_FCFS_does_not_drop_it():
    rows,a=reference([job('a',gpu=None),job('b')])
    assert len(rows)==2 and a['blocked_jobs']==2
    assert rows[0]['reason']=='GPU_REQUEST_AUTHORITY_MISSING'
    assert rows[1]['reason']=='FCFS_PREDECESSOR_UNRESOLVED'


def test_capacity_and_gang_compatibility_not_relaxed():
    rows,a=reference([job(gpu=5)])
    assert a['blocked_jobs']==1 and rows[0]['reason']=='GANG_COMPATIBILITY_UNAVAILABLE'


@pytest.mark.parametrize('field',['voltage','line_loading','electricity_price','end_time','actual_runtime','actual_result'])
def test_reference_rejects_grid_and_future_inputs(field):
    jobs=[job()];jobs[0][field]=1
    with pytest.raises(ValueError,match='FUTURE_OR_GRID'):reference(jobs)


def test_future_submission_not_known_at_cutoff():
    j=job();j['submit_time']='2025-04-01T01:00:00+10:00'
    with pytest.raises(ValueError,match='D1_CAUSAL'):reference([j])


def test_FCFS_compares_instants_across_timezone_offsets():
    first=job('z',site='AIDC01');later=job('a',site='AIDC01')
    first['submit_time']='2025-03-30T23:00:00+00:00'
    later['submit_time']='2025-03-30T18:00:00-06:00'
    rows,a=reference([later,first]);by_id={r['job_uid']:r for r in rows}
    assert by_id['z']['reference_start']==0 and by_id['a']['reference_start']==2


def test_offline_FAIL_is_diagnostic_and_never_operational_gate():
    r=receipt();r['converged']=False;r['PASS']=False
    replay_receipt(frozen(),r,actual=False)
    r['operational_gate']=True
    with pytest.raises(ValueError,match='OFFLINE_NOT_OPERATIONAL'):replay_receipt(frozen(),r,actual=False)


@pytest.mark.parametrize('field,value',[('DayAhead_power_arrays_copied',True),('IT_recomputed_from_actual_occupancy',False),
                                     ('realized_authority_verified',False)])
def test_actual_authority_and_recomputation_flags(field,value):
    r=receipt(True);r[field]=value
    with pytest.raises(ValueError):replay_receipt(frozen(),r,actual=True)


def test_alignment_identity_and_signed_directions():
    out=residuals(*curves(),[DAY])
    assert out[0]['r_up']==pytest.approx(.006) and out[0]['r_down']==0
    assert out[1]['r_down']==pytest.approx(.009) and out[1]['r_up']==0
    assert all(abs(r['e_total']-r['e_model']-r['e_forecast'])<=8*math.ulp(1.1) for r in out)


@pytest.mark.parametrize('field,value',[('node','other'),('phase','b'),('slot',4),('timestamp','different')])
def test_axis_mismatch_fails(field,value):
    p,d,a=curves();a[0][field]=value
    with pytest.raises(ValueError):residuals(p,d,a,[DAY])


def test_aligned_future_timestamp_is_not_April_evidence():
    p,d,a=curves()
    for rows in (p,d,a):rows[0]['timestamp']='2025-05-01T00:15:00+10:00'
    with pytest.raises(ValueError,match='TIMESTAMP_SLOT_ALIGNMENT'):residuals(p,d,a,[DAY])


def test_preregistered_date_cannot_silently_disappear():
    with pytest.raises(ValueError,match='FROZEN_DATE_MISSING'):residuals([],[],[],[DAY])


def test_duplicate_and_nonfinite_samples_rejected():
    p,d,a=curves()
    with pytest.raises(ValueError,match='DUPLICATE'):residuals(p+p[:1],d,a,[DAY])
    a[0]['voltage_pu']=float('nan')
    with pytest.raises(ValueError,match='FINITE'):residuals(p,d,a,[DAY])


def test_quantiles_fixed_reproducible_and_asymmetric():
    assert quantile([4,1,3,2],.95)==pytest.approx(3.85)
    rows=residuals(*curves(),[DAY]);a=quantiles(rows,'pointwise');b=quantiles(list(reversed(rows)),'pointwise')
    assert a==b and [r['q'] for r in a]==list(QUANTILES)
    assert a[1]['delta_up']!=a[1]['delta_down']
    assert a[1]['lower_candidate']==pytest.approx(.95+a[1]['delta_down'])


def test_day_worst_and_current_005_coverage_events():
    rows=residuals(*curves(),[DAY]);worst=day_worst(rows)
    assert worst[0]['r_up']==pytest.approx(.006) and worst[0]['r_down']==pytest.approx(.009)
    c=coverage(rows)
    assert c['pointwise']['up']['covered']==2 and c['pointwise']['down']['covered']==2
    assert c['day_worst']['up']['covered']==0 and c['exceedance_days']['down']==[DAY]
    assert c['exceedances'][0]['slot']==0 and c['exceedances'][1]['slot']==1


def test_no_empty_evidence_fabrication():
    assert quantile([],.95) is None
    assert all(r['delta_up'] is None and r['lower_candidate'] is None for r in quantiles([],'pointwise'))
    assert coverage([])['pointwise']['up']['fraction'] is None
    assert error_stats([],'e_model')['RMSE'] is None


def test_dominance_requires_all_metrics_consistent():
    a=dict(RMSE=2,MAE=2,P95_absolute=2,day_worst_P95=2)
    b=dict(RMSE=1,MAE=1,P95_absolute=1,day_worst_P95=1)
    assert dominance(a,b)=='MODEL'
    b['MAE']=3
    assert dominance(a,b)=='MIXED'
    b['RMSE']=None
    assert dominance(a,b)=='INCONCLUSIVE'


def test_S2_fail_does_not_mean_physical_infeasible():
    checks=sensitivity([{'voltage_pu':.951}])
    assert checks[0]['satisfies'] and not checks[2]['satisfies']
    assert checks[0]['label']=='B0_PHYSICAL_PLANNING_FEASIBLE'


@pytest.mark.parametrize('day',['2025-05-01','2024-04-01','2026-04-01'])
def test_May_and_wrong_year_forbidden(day):
    with pytest.raises(ValueError,match='APRIL_2025_ONLY'):april(day)


def test_no_native_coordinator_or_actual_modification():
    root=DOC.parents[1]
    tree=ast.parse((root/'v42_native/coordinator.py').read_text(encoding='utf8'))
    assert not any(isinstance(n,ast.Attribute) and n.attr=='fresh_ac' for n in ast.walk(tree))
    for path in (root/'v42_april_b0_v2').glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf8'))
        assert not any(isinstance(n,ast.Attribute) and n.attr in ('optimize','fresh_ac') for n in ast.walk(tree))


def test_persisted_current_authority_and_all_April_rows_preserved():
    a=evidence('V42_REFERENCE_MAPPING_AUDIT.json')
    assert a['total_snapshot_rows']==a['total_output_rows']==29350
    assert a['all_rows_retained'] and a['current_runtime_inference'] and not a['historical_mapping_fallback']
    assert len(a['days'])==30 and not a['scientific_B0_execution_dates']
    for row in a['days']:
        assert row['raw_forecast_available'] and row['raw_realized_available']
        assert row['realized_missing_GPU']>0 and row['input_jobs']==row['output_jobs']


def test_persisted_flags_May_holdout_and_null_numeric_results():
    validate_flags(evidence('FINAL_FLAGS.json'))
    assert evidence('MAY_HOLDOUT_RECEIPT.json')['May_result_payload_reads']==0
    assert evidence('CURRENT_005_MARGIN_COVERAGE.json')['pointwise']['up']['fraction'] is None
    assert evidence('B0_AIDC_PRESENCE_AUDIT.json')['physical_PASS'] is None
    assert evidence('FINAL_VERDICT.json')['mapping_file_absence_is_STOP'] is False
