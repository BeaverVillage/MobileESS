from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
import numpy as np
import pandas as pd
import pytest
from v42_final.common import MODEL
from v42_final.workload import profile
from v42_job_capability import Job,Resources
from v42_native.service import boundary
from v42_may_campaign.bindings import _axis,check_a_cells,check_forecast,WORKER_PROOF


@pytest.fixture
def cells():
    issue=datetime(2025,5,1,18,tzinfo=timezone(timedelta(hours=10)))
    base=dict(planning_eligible=True,submit_time=(issue-timedelta(hours=2)).isoformat(),
        runtime_authority=MODEL,planning_site='S00',elapsed_seconds=0.,
        cohort='normal|partition|work|False|gpu|wall|nodes',can_checkpoint_migrate=False)
    p=dict(base,job_uid='pending',state='PENDING',GPU_gang=4,service_slots=3,
        reference_start_if_authorized=24,exact_service_seconds=2000.)
    r=dict(base,job_uid='expired',state='RUNNING',GPU_gang=8,service_slots=0,
        reference_start_if_authorized=0,exact_service_seconds=0.)
    bundle=dict(day='2025-05-02',issue_time=issue.isoformat(),known_population=[p,r],
        capacities={'S00':16,'S01':16},
        racks=[dict(aidc_id=s,compatibility_GPU_limit=16) for s in ('S00','S01')],
        WAN=dict(bytes_per_gpu=100,maximum_active_transfers=2,
            paths=[dict(source='S00',destination='S01',links=['l0'])],
            link_capacity_bytes_15min={'l0':list(range(1,97))}))
    windows=[dict(job_id='pending',can_timeshift=True,reference_start=24,latest_start=26,
        allowed_starts=[24,25,26]),dict(job_id='expired',can_timeshift=False,
        reference_start=0,latest_start=0,allowed_starts=[0])]
    job=Job('pending','PENDING',0,0,24,'S00',3,4,elapsed_seconds=0.,duration_authority=MODEL,
        initial_sites=('S00','S01'))
    bound=boundary(job,(24,25,26),'a'*64,'b'*64,H=120)
    raw={p['job_uid']:dict(p,can_timeshift=True,delay_budget_slots=2),
         r['job_uid']:dict(r,can_timeshift=False,delay_budget_slots=0)}
    resources=Resources(bundle['capacities'],{'S00':(16,),'S01':(16,)},
        {('l0',t):t-23 if t>=24 else 0 for t in range(120)},
        {('S00','S01'):('l0',)},120,100,{('S00',0):8},{},{},max_active_transfers=2)
    return bundle,windows,(bundle,{'pending':job},{'pending':bound},{'pending':2000.},resources,raw)


def test_original_native_cells_include_expired_issue_gang_and_untruncated_tail(cells):
    receipt=check_a_cells(*cells)
    assert receipt['PASS'] and receipt['raw_eligible_jobs']==2
    assert receipt['positive_service_native_jobs']==1 and receipt['zero_future_service_rows']==1
    assert receipt['latest_completion_is_representation_tail_not_new_deadline']
    assert receipt['DDAY_offset']==24 and receipt['issue_relative_axis']==120
    assert WORKER_PROOF=='WORKER_REQUIRED_BEFORE_FIRST_NATIVE_EVERY_DATE'


@pytest.mark.parametrize('which',['raw_gang','native_gang','seconds','window','tail','WAN_offset','issue_gang','resource_capacity','initial_sites','protected','raw_metadata'])
def test_original_native_cell_mutations_rejected(cells,which):
    b,w,data=deepcopy(cells);loaded,jobs,bounds,seconds,resources,raw=data
    if which=='raw_gang':raw['pending']['GPU_gang']=3
    if which=='native_gang':jobs['pending']=replace(jobs['pending'],gpu=3)
    if which=='seconds':seconds['pending']=1999.
    if which=='window':bounds['pending']=replace(bounds['pending'],allowed_starts=(24,26))
    if which=='tail':bounds['pending']=replace(bounds['pending'],latest_completion=96)
    if which=='WAN_offset':resources.wan_capacities['l0',23]=1
    if which=='issue_gang':resources.fixed_gpu.clear()
    if which=='resource_capacity':resources.capacities=dict(resources.capacities,S00=32)
    if which=='initial_sites':jobs['pending']=replace(jobs['pending'],initial_sites=('S00',))
    if which=='protected':jobs['pending']=replace(jobs['pending'],protected=True)
    if which=='raw_metadata':raw['expired']['elapsed_seconds']=1.
    with pytest.raises(ValueError,match='MAY31_DATE_BINDING_'):check_a_cells(b,w,data)


def test_original_finite_boundary_requires_source_lineage(cells):
    b,w,data=deepcopy(cells)
    data[2]['pending']=replace(data[2]['pending'],window_authority_sha256='')
    with pytest.raises(ValueError,match='SERVICE_INPUT_LINEAGE'):check_a_cells(b,w,data)


def test_issue_timezone_is_absolute_instant_not_offset_string():
    b=dict(day='2025-05-02',issue_time='2025-05-01T08:00:00+00:00')
    issue,midnight=_axis(b)
    assert issue==midnight-timedelta(hours=6)
    for issue_time in ('2025-05-01T18:00:00','2025-05-01T18:00:00+00:00'):
        with pytest.raises(ValueError,match='D1_CAUSAL_ISSUE'):_axis(dict(b,issue_time=issue_time))


@pytest.fixture
def forecasts(tmp_path):
    kernel=tmp_path/'kernel.csv';pd.DataFrame({'kappa':[.125]*8}).to_csv(kernel,index=False)
    k=pd.read_csv(kernel).kappa.to_numpy();q50=[1.]*24;q90=[2.]*24
    nominal=profile(q50,k);reserve=profile(np.array(q90)-q50,k)
    bundle=dict(day='2025-05-02',issue_time='2025-05-01T18:00:00+10:00',C0_Q50=q50,C0_Q90=q90,
        unknown_nominal_GPU=nominal.tolist(),CC4_reserve_GPU=reserve.tolist())
    cc=dict(target_day=bundle['day'],issue_time=bundle['issue_time'],future_job_ids=[],
        Q50_GPUh=q50,Q90_GPUh=q90,nominal_unknown_GPU_96=nominal[:96].tolist(),
        spread_headroom_GPU_96=reserve[:96].tolist())
    return bundle,dict(forecast_inputs={'current_CC4':cc}),kernel


def test_all_original_full_CC4_tail_preserved(forecasts):
    r=check_forecast(*forecasts)
    assert r['PASS'] and r['nominal_full_slots']==100 and r['reserve_full_slots']==100
    assert r['stored_profile_authority']['recomputation_from_serialized_kernel_bit_exact']
    assert r['actual_current_loader_profile_bit_exact'] and not r['reserve_entered_electrical_load']


@pytest.mark.parametrize('which',['tail','prefix','Q90','future','day','issue'])
def test_full_CC4_and_causality_mutations_rejected(forecasts,which):
    b,o,k=deepcopy(forecasts);cc=o['forecast_inputs']['current_CC4']
    if which=='tail':b['unknown_nominal_GPU'][-1]=np.nextafter(b['unknown_nominal_GPU'][-1],np.inf)
    if which=='prefix':cc['nominal_unknown_GPU_96'][0]+=1
    if which=='Q90':cc['Q90_GPUh'][0]+=1
    if which=='future':cc['future_job_ids']=['future_job']
    if which=='day':cc['target_day']='2025-05-03'
    if which=='issue':cc['issue_time']='2025-05-01T19:00:00+10:00'
    with pytest.raises(ValueError,match='MAY31_DATE_BINDING_'):check_forecast(b,o,k)


def may01_serialized(forecasts,tmp_path):
    b,o,k=deepcopy(forecasts);b.update(day='2025-05-01',issue_time='2025-04-30T18:00:00+10:00')
    cc=o['forecast_inputs']['current_CC4'];cc.update(target_day=b['day'],issue_time=b['issue_time'])
    # The archived producer serializes a profile generated before its kernel
    # was serialized.  Preserve that different input exactly; never tolerate
    # mutation in the stored arrays or the actual current loader's prefix.
    b['unknown_nominal_GPU'][0]=np.nextafter(b['unknown_nominal_GPU'][0],np.inf)
    path=tmp_path/'original_profile.csv'
    pd.DataFrame(dict(slot=range(100),nominal_GPU=b['unknown_nominal_GPU'],
        CC4_uncertainty_headroom_target_GPU=b['CC4_reserve_GPU'])).to_csv(path,index=False)
    source=pd.read_csv(path)
    b['unknown_nominal_GPU']=source.nominal_GPU.tolist()
    b['CC4_reserve_GPU']=source.CC4_uncertainty_headroom_target_GPU.tolist()
    original=tmp_path/'original_bundle.json';original.write_text(json.dumps(b),encoding='utf-8')
    return b,o,k,dict(may01_profile_path=path,may01_bundle_path=original)


def test_may01_original_serialized_input_exact_and_current_loader_separately_exact(forecasts,tmp_path):
    b,o,k,kwargs=may01_serialized(forecasts,tmp_path)
    r=check_forecast(b,o,k,**kwargs)
    authority=r['stored_profile_authority']
    assert authority['stored_profile_bit_exact']
    assert authority['recomputation_difference_is_not_a_tolerance_acceptance']
    assert not authority['recomputation_from_serialized_kernel_bit_exact']
    assert r['actual_current_loader_profile_bit_exact']


def test_may01_even_one_binary64_input_mutation_rejected(forecasts,tmp_path):
    b,o,k,kwargs=may01_serialized(forecasts,tmp_path)
    b['unknown_nominal_GPU'][-1]=np.nextafter(b['unknown_nominal_GPU'][-1],np.inf)
    with pytest.raises(ValueError,match='ORIGINAL_FULL_CC4_PROFILE_AND_TAIL'):check_forecast(b,o,k,**kwargs)


def test_checker_source_mutation_during_actual_audit_rejects_receipt(tmp_path,monkeypatch):
    import v42_may_campaign.bindings as audit
    monkeypatch.setattr(audit,'DAYS',('2025-05-01',))
    monkeypatch.setattr(audit,'check_day',lambda *a:dict(PASS=True))
    monkeypatch.setattr(audit,'sha',lambda path:'CHANGED_SOURCE_BYTES')
    with pytest.raises(ValueError,match='CHECKER_SOURCE_CHANGED_DURING_AUDIT'):audit.audit_all(tmp_path)
    assert not (tmp_path/'MAY31_ACTUAL_INPUT_LOADER_BINDING_AUDIT.json').exists()
