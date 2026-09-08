"""Downstream capacity rebase. This module cannot fit or predict an ML model."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import numpy as np
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.preflight import ROOT,record

OLD=Path('D:/codex_mobileess_workspace/MobileESS_v41r1_premay_voltage_security_margin')
OLD_RUN=OLD/'frozen_artifacts/v41r1_migration'
OUT=ROOT.parent/'MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase'
CAP=OUT/'V41R2_780GPU_CAPACITY_AUTHORITY.json'
RACK=OUT/'V41R2_LOGICAL_RACK_AUTHORITY.json'
VECTOR=(80,40,80,40,100,80,40,80,40,80,40,80)
OLD_VECTOR=(64,32,64,32,80,64,32,64,32,64,32,64)
SITES=tuple(f'AIDC{i:02}' for i in range(1,13))
DAY='2025-05-04'

def freeze():
    from dayahead.v39d.evaluate import _load_capacity
    old,details=_load_capacity(OLD)
    assert tuple(old.site_capacity[s] for s in SITES)==OLD_VECTOR
    assert sum(VECTOR)==780 and all(v%4==0 for v in VECTOR)
    data=dict(schema='V41R2_780GPU_CAPACITY_AUTHORITY_V1',status='FROZEN',
        transition='V41R1_624GPU -> V41R2_780GPU_CAPACITY_REBASE',old_vector=list(OLD_VECTOR),
        new_vector=list(VECTOR),site_capacity=dict(zip(SITES,VECTOR)),scale_factor=1.25,
        old_total=624,new_total=780,GPU_per_node=4,node_equivalents=dict(zip(SITES,[v//4 for v in VECTOR])),
        source_authority=record(OLD/'dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json'),
        no_measured_facility_claim=True,spatial_locations_unchanged=True,electrical_hosts_unchanged=True,
        code_config_locations_changed=['dayahead/v41r2/authority.py','dayahead/v41r2/reference.py',
        'dayahead/v41/data.py','dayahead/v41/snapshot.py','dayahead/v41/common.py','dayahead/v41/electrical.py',
        'dayahead/v39d/evaluate.py','dayahead/v39a/power.py','dayahead/v40e/electrical.py','dayahead/v41/execution.py',
        'dayahead/v40d_actual/capacity_audit.py'])
    data['canonical_SHA256']=digest(data)
    if CAP.exists():assert read(CAP)==data
    else:write_json(CAP,data)
    pools=[dict(aidc_id=p.aidc_id,rack_pool_id=p.rack_pool_id,compatibility_GPU_limit=dict(zip(SITES,VECTOR))[p.aidc_id],
        aggregate_capacity_contribution_GPU=0,semantics='NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE') for p in old.rack_pools]
    racks=dict(schema='V41R2_NONADDITIVE_LOGICAL_RACKS',status='FROZEN',capacity_authority=record(CAP),
        parent=record(OLD/'dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json'),
        logical_Rack_pools=pools,logical_Rack_pool_count=len(pools),logical_Rack_limits_are_additive_capacity=False,
        gang_splitting_allowed=False,measured_physical_Rack_census_claim=False,
        effective_Rack_deliverability_by_AIDC=dict(zip(SITES,VECTOR)),effective_Rack_deliverability_total=780,
        site_capacity_authority_file_SHA256=record(CAP)['sha256'],
        construction_rule='Retain all legacy logical Rack IDs; only rebind each non-additive single-gang compatibility ceiling to V41R2 site capacity')
    racks['rack_canonical_SHA256']=digest(racks)
    write_json(RACK,racks)
    write_json(OUT/'V41R2_RACK_CAPACITY_DEPENDENCY_RECEIPT.json',dict(status='PASS',
        dependency='CapacityAuthority.eligible_racks compares whole gang to historical_gpu_capacity; V39D ceiling equals site capacity',
        changed_only='Per-logical-label compatibility_GPU_limit',logical_labels_unchanged=True,
        additive_physical_rack_capacity=False,gang_indivisibility_unchanged=True,GPU_type_unchanged=True,
        old_source=racks['parent'],new_source=record(RACK),site_capacity_SHA=record(CAP),
        code=record(ROOT/'dayahead/v38/authority.py')))
    return data

def capacity():
    from dayahead.v39d.evaluate import _load_capacity
    old,details=_load_capacity(OLD)
    a=read(CAP); unsigned={k:v for k,v in a.items() if k!='canonical_SHA256'}
    assert digest(unsigned)==a['canonical_SHA256'] and tuple(a['new_vector'])==VECTOR
    sites=dict(zip(SITES,VECTOR))
    rack=read(RACK)
    assert rack['effective_Rack_deliverability_by_AIDC']==sites and rack['effective_Rack_deliverability_total']==780
    assert digest({k:v for k,v in rack.items() if k!='rack_canonical_SHA256'})==rack['rack_canonical_SHA256']
    pools=tuple(replace(p,historical_gpu_capacity=float(sites[p.aidc_id])) for p in old.rack_pools)
    new=replace(old,site_capacity=sites,rack_pools=pools,source_sha256=record(CAP)['sha256'])
    return new,dict(capacity_authority=a,capacity_certificate=record(CAP),rack_authority=read(RACK),rack_certificate=record(RACK))

def legacy_snapshot_not_used(day):
    from dayahead.v41.data import RUNTIME
    from dayahead.v41.reserve import cap_reserve,validate_snapshot
    from dayahead.v41.scalars import project
    assert day==DAY,'FULL_MAY_HOLD'
    folder=RUNTIME/'inputs'/day;path=folder/f'V41_ML_SNAPSHOT_{day}.json'
    oldpath=OLD_RUN/'inputs'/day/path.name
    old=read(oldpath);new=deepcopy(old);cap,_=capacity()
    grid=np.tile(VECTOR,(96,1))
    new.update(cap_reserve(old['H4_RAW_R85_B2_GPUh'],read(folder/'H4_CAP_POOL.json'),grid))
    new['future_service_capacity_gpu']=grid.tolist()
    new['future_service_eligibility_authority']=dict(source_variable='CapacityAuthority.site_capacity',
        eligible_sites=list(SITES),rack_limits_added_to_capacity=False,files=[record(CAP),record(RACK)])
    new['capacity_authority']=record(CAP)
    for key in ['model','preprocessing']:
        assert record(old[key]['path'])==old[key]
    changed={k for k in new if new[k]!=old.get(k)}
    assert changed<= {'H4_CAP_PHYS','H4_ACTIONABLE_RESERVE_GPUh','future_service_capacity_gpu','future_service_eligibility_authority','capacity_authority'}
    validate_snapshot(new,cap)
    if path.exists():assert read(path)==new
    else:write_json(path,new)
    seal=dict(snapshot=record(path),optimizer_scalar_sha256=project(new).sha256,
        policies=['B0','B1'],stages=['REFERENCE','A0'],policy_specific_forecasts=False,
        optimizer_probability_fields=[],actual_inputs_opened=False)
    write_json(folder/'ML_SNAPSHOT_RECEIPT.json',seal)
    write_json(OUT/'V41R2_ML_POSTPROCESSING_AUDIT.json',dict(status='PASS',
        ML_RETRAIN_COUNT=0,ML_RECALIBRATION_COUNT=0,ML_MODEL_CHANGE_COUNT=0,ML_PREDICTION_CALLS=0,
        old_snapshot=record(oldpath),new_snapshot=record(path),changed_fields=sorted(changed),
        raw_H4_equal=old['H4_RAW_R85_B2_GPUh']==new['H4_RAW_R85_B2_GPUh'],
        raw_H4_SHA=digest(old['H4_RAW_R85_B2_GPUh']),Q90_equal=old['PENDING_JOB_Q90_SECONDS']==new['PENDING_JOB_Q90_SECONDS'],
        frozen_model=old['model'],preprocessing=old['preprocessing'],H4_model_authority=old['H4_model_authority'],
        old_physical_GPUh=old['H4_CAP_PHYS'][0],new_physical_GPUh=new['H4_CAP_PHYS'][0],
        actionable_changed_windows=int(np.sum(np.asarray(old['H4_ACTIONABLE_RESERVE_GPUh'])!=new['H4_ACTIONABLE_RESERVE_GPUh'])),
        all_other_snapshot_fields_exactly_preserved=True))
    return path,seal

def aggregate_it(active,installed=780):
    from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU
    assert 0<=active<=installed
    return (Decimal(installed)*IDLE_W_PER_GPU+Decimal(str(active))*CENTER_SWING_W_PER_GPU)/1000

# V41R3 consumes the exact frozen V41R2 materialized snapshot.
from dayahead.v41r3.authority import snapshot
