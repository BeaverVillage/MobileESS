from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import inspect
import numpy as np
import pytest
from dayahead.paper_analysis.storage import read,digest
from dayahead.v41.preflight import record
from dayahead.v41r2.authority import CAP,RACK,OUT,ROOT,OLD,OLD_RUN,DAY,VECTOR,SITES,capacity,aggregate_it
from dayahead.v41r2.reference import materialize
from dayahead.v38.authority import CapacityAuthority,RackPool

def test_exact_capacity_and_four_gpu_node_granularity():
    cap,_=capacity()
    assert sum(cap.site_capacity.values())==780
    assert tuple(cap.site_capacity[s] for s in SITES)==VECTOR
    assert all(v%4==0 for v in cap.site_capacity.values())
    assert read(CAP)['node_equivalents']==dict(zip(SITES,[v//4 for v in VECTOR]))

def test_per_gpu_power_and_conservation():
    from dayahead.v39a.power import validate_power_conservation
    from dayahead.v39a.contracts import C_REF_W_PER_GPU,IDLE_W_PER_GPU
    assert C_REF_W_PER_GPU>IDLE_W_PER_GPU>0
    assert aggregate_it(780)==780*C_REF_W_PER_GPU/1000
    cap=dict(zip(SITES,VECTOR))
    for fraction in (0,.25,.5,1):
        assert validate_power_conservation(cap,{s:int(v*fraction) for s,v in cap.items()})['status']=='PASS'
    assert aggregate_it(780)!=Decimal('406.775993813819')

def test_actual_power_audit_rebinds_capacity_and_rejects_old_anchor():
    from dayahead.v40d_actual.capacity_audit import check_it_power
    from dayahead.v40d_actual.contracts import ReplayError
    from dayahead.v39a.power import site_it_power_kw
    caps=dict(zip(SITES,VECTOR));gpu=np.tile(VECTOR,(96,1))
    it=np.tile([float(site_it_power_kw(v,v)) for v in VECTOR],(96,1))
    result=check_it_power(caps,gpu,it)
    assert result['status']=='PASS' and result['capacity_sum_GPU']==780
    with pytest.raises(ReplayError):check_it_power(caps,gpu,it*.8)

def test_models_and_raw_h4_unchanged():
    audit=read(OUT/'V41R2_ML_POSTPROCESSING_AUDIT.json')
    assert audit['ML_RETRAIN_COUNT']==audit['ML_RECALIBRATION_COUNT']==audit['ML_MODEL_CHANGE_COUNT']==audit['ML_PREDICTION_CALLS']==0
    assert audit['raw_H4_equal'] and audit['Q90_equal']
    assert record(audit['frozen_model']['path'])==audit['frozen_model']
    assert audit['old_physical_GPUh']==2496 and audit['new_physical_GPUh']==3120

def test_reproducible_from_original_causal_state():
    r=read(OUT/'V41R2_REFERENCE_REPRODUCIBILITY.json')
    assert r['exact_job_content_equal']
    assert record(r['first']['path'])['sha256']==record(r['second']['path'])['sha256']

def test_old624_reference_receipt_rejected(tmp_path):
    from dayahead.v41.common import build
    from dayahead.paper_analysis.storage import write_json
    from dayahead.v41.data import RUNTIME
    old=read(OLD_RUN/'inputs'/DAY/'common_q90_v3/COMMON_INPUT_RECEIPT.json')
    write_json(tmp_path/'COMMON_INPUT_RECEIPT.json',old)
    with pytest.raises(ValueError):build(DAY,RUNTIME/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json',capacity()[0],folder_override=tmp_path)

def sample(uid,state='PENDING',site='UNASSIGNED',duration=2,gpu=4,start=120):
    return dict(job_uid=uid,state_at_issue=state,AIDC_site=site,start_slot=start,end_slot=start+duration,
        safe_duration_slots=duration,requested_GPU=gpu,Rack_label='A_LP1' if site=='A' else 'UNASSIGNED')

def small(rows):
    c=CapacityAuthority({'A':4,'B':4},{},(RackPool('A','A_LP1',4),RackPool('B','B_LP1',4)),'test')
    scheduling=[SimpleNamespace(job_id=r['job_uid'],priority_key=(i,)) for i,r in enumerate(rows)]
    return materialize(rows,scheduling,c)

def test_queued_unassigned_is_readmitted_and_old_delay_is_not_release():
    rows=[sample('running','RUNNING','A',3,4,0),sample('queued'),sample('next')]
    out,_=small(rows)
    assert (out[1]['AIDC_site'],out[1]['start_slot'])==('B',0)
    assert (out[2]['AIDC_site'],out[2]['start_slot'])==('B',2)
    assert rows[1]['AIDC_site']=='UNASSIGNED' and rows[1]['start_slot']==120

def test_gang_not_split_and_no_physical_rack_summation():
    rows=[sample('oversize',gpu=8)]
    out,_=small(rows);assert out[0]['AIDC_site']=='UNASSIGNED'
    c,_=capacity();assert len(c.rack_pools)==48
    assert all(r.historical_gpu_capacity==c.site_capacity[r.aidc_id] for r in c.rack_pools)
    r=read(RACK)
    assert r['effective_Rack_deliverability_by_AIDC']==dict(c.site_capacity)
    assert r['effective_Rack_deliverability_total']==780
    assert 'frozen_V39C_site_capacity_total' not in r

def test_reference_firewall_and_running_source():
    assert tuple(inspect.signature(materialize).parameters)==('jobs','scheduling','capacity')
    rows=[sample('running','RUNNING','A',3,4,0),sample('pending')]
    out,a=small(rows);assert (out[0]['AIDC_site'],out[0]['start_slot'],out[0]['end_slot'])==('A',0,3)
    assert a['grid_reads']==a['Actual_reads']==a['optimizer_calls']==0

def test_pcc_installation_hard_limit_without_uprating():
    a=read(OUT/'V41R2_PCC_TRANSFORMER_CAPABILITY.json')
    assert a['status']=='PASS' and all(r['transformer_rating_kVA']==1500 and r['full_installation_utilization']<=1 for r in a['sites'])

def test_operating_point_coefficients_require_regeneration():
    a=read(OUT/'V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json')
    for k in ['B_Planning_voltage','C_Phase_line_current','E_Operating_point']:
        assert a['families'][k]['classification']=='REGENERATE_REQUIRED'

def test_accepted_search_and_domain_source_bytes_preserved():
    for p in ['dayahead/v41r1/early_stop.py','dayahead/v41r1/bounded_solver.py','dayahead/v40g/domain.py',
              'dayahead/v40g/optimizer.py','dayahead/v41r1/migration.py','dayahead/v40h/feedback.py']:
        assert (ROOT/p).read_bytes()==(OLD/p).read_bytes()

def test_new_b1_start_dimension_is_fixed():
    from dayahead.v41r1.migration import attach
    from dayahead.v40g.domain import options
    cap,_=capacity()
    r=dict(sample('p',site='AIDC01',duration=1,start=24),Rack_label='AIDC01_LP01')
    row=attach([r])[0]
    opts=options(row,cap,None,{})
    assert len(opts)==12 and {o.start for o in opts}=={24}

def test_full_may_guard_before_any_io():
    from dayahead.v41.execution import dayahead
    with pytest.raises(ValueError,match='FULL_MAY_HOLD'):dayahead('2025-05-05','B0')
