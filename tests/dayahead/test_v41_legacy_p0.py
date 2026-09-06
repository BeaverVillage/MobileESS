from copy import deepcopy
from types import SimpleNamespace
from datetime import timedelta
import pandas as pd
import pytest
from dayahead.paper_analysis.storage import write_json,read,digest
from dayahead.v41 import execution


@pytest.mark.parametrize('policy',['B0','B1','B2','B3'])
def test_p0_01_old_success_is_not_v41_execution(tmp_path,monkeypatch,policy):
    monkeypatch.setattr(execution,'RUNS',tmp_path)
    write_json(tmp_path/'2025-05-01'/policy/'dayahead/DAYAHEAD_RECEIPT.json',{'status':'COMPLETE','old_result':'PASS'})
    with pytest.raises(ValueError,match='LEGACY_DAYAHEAD_RECEIPT'): execution.verify_dayahead('2025-05-01',policy)


def test_p0_03_v41_snapshot_changes_all_cache_families(tmp_path):
    from dayahead.v40h.cache import ROLES,execution_identity,cache_identity,store_candidate,restore_candidate
    base={k:digest(k) for k in ROLES}; base['V41_ML_snapshot_SHA']='first'
    one=execution_identity(base); base['V41_ML_snapshot_SHA']='second'; two=execution_identity(base)
    for kind in ('STAGE','RESTRICTED','FULL_CHILD','MIPSTART'):
        old=cache_identity(one,kind=kind,candidate='c',parent_SHA='p',fixed_trajectory_SHA='t',step=1)
        new=cache_identity(two,kind=kind,candidate='c',parent_SHA='p',fixed_trajectory_SHA='t',step=1)
        assert old['identity_SHA']!=new['identity_SHA']
        if kind!='STAGE':
            path=tmp_path/(kind+'.json'); store_candidate(path,old,{'rho':.4})
            assert restore_candidate(path,new) is None


def proof():
    return dict(schema='V41_ELECTRICAL_CERTIFICATE_V1',generation_attestation='CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER',
        pre_generation_identity_completed_at='1',generation_started_at='2',generation_finished_at='3',post_generation_verification_completed_at='4',
        proof=dict(fresh_output_paths_were_absent=True,old_result_cache_reuse_count=0,
            fresh_generation_total_SolveSnap_calls=23234,measured_nonconverged_calls=0,measured_solve_calls={'voltage':11617,'current':11617}))


@pytest.mark.parametrize('fault',['legacy','posthoc','reused','no_solve','nonconverged','late_identity'])
def test_p0_04_v41_requires_actual_generation_proof(fault):
    from dayahead.v41.electrical import verify_generation_proof
    value=proof(); verify_generation_proof(value)
    if fault=='legacy': value['schema']='old'
    if fault=='posthoc': value['generation_attestation']='copied source hashes'
    if fault=='reused': value['proof']['old_result_cache_reuse_count']=1
    if fault=='no_solve': value['proof']['fresh_generation_total_SolveSnap_calls']=0
    if fault=='nonconverged': value['proof']['measured_nonconverged_calls']=1
    if fault=='late_identity': value['pre_generation_identity_completed_at']='9'
    with pytest.raises(ValueError): verify_generation_proof(value)


@pytest.mark.parametrize('field',['ML_snapshot','electrical','common_service_SHA'])
def test_p0_05_reuse_requires_current_generation_inputs(field):
    base=dict(ML_snapshot={'sha256':'ml'},electrical={'sha256':'electrical'},common_service_SHA='service')
    context=SimpleNamespace(v41_electrical_certificate=base['electrical']); common=dict(COMMON_DA_DURATION_SHA='service')
    execution.validate_reused_base(base,base['ML_snapshot'],common,context)
    changed=deepcopy(base); changed[field]='stale'
    with pytest.raises(ValueError): execution.validate_reused_base(changed,base['ML_snapshot'],common,context)


def test_p0_07_8749975_not_excluded_from_counterfactual_day():
    from tests.dayahead.test_v40h_integrity import regression_job
    from dayahead.v40g_segments.canonical import import_frozen
    from dayahead.v40d_actual.rack_dispatch import Rack
    from dayahead.v41.actual import replay_jobs
    issue,job,obs=regression_job('AIDC01'); job['Rack_label']='R'
    result=replay_jobs(import_frozen([job]),{'8749975':obs},issue_time=issue,site_capacity={'AIDC01':64},racks=[Rack('AIDC01','R',64)])
    row=result['job_ledger'][0]
    assert row['counterfactual_day_classification']['status']=='EXECUTION_INCLUDED'
    assert row['actual_execution_end']==pytest.approx(26.226666666666667)
    assert row['counterfactual_day_classification']['D_DAY_GPU_SERVICE']==pytest.approx(2004*4/3600)
    assert result['GPU'][:3,0].tolist()==[4,4,4]
    job.update(AIDC_site='UNASSIGNED',Rack_label=None)
    replay=replay_jobs(import_frozen([job]),{'8749975':obs},issue_time=issue,site_capacity={'AIDC01':64},racks=[Rack('AIDC01','R',64)])
    row=replay['job_ledger'][0]
    assert row['status']=='FROZEN_UNADMITTED_BACKLOG' and row['backlog_GPU_hours']==11904*4/3600
    assert not row['counterfactual_day_classification']['service_excluded']
    assert replay['pre_day_complete']==[]


def test_corrected_mapper_never_forwards_native_loads_to_duplicated_branch(monkeypatch):
    from dayahead.v40e.mapping import NativeAllocation,corrected_mapping
    from dayahead.v28r2 import opendss_mapping as mapping
    calls=[]
    def old(odd,adapter,*args):
        calls.append(adapter['loads']); assert adapter['loads']==[]
    monkeypatch.setattr(mapping,'apply_trajectory_slot',old)
    monkeypatch.setattr(NativeAllocation,'apply',lambda *args:None)
    adapter=dict(loads=[dict(load_name='one',bus='65',phases=[1],base_p_kw=1.,base_q_kvar=1.)])
    context=SimpleNamespace(legacy_context=(None,None,object()))
    with corrected_mapping(): mapping.apply_trajectory_slot(None,adapter,context,None,0)
    assert calls==[[]] and len(adapter['loads'])==1


def test_all_shared_bus_phase_load_groups_have_conserved_native_allocation():
    from dayahead.v40e.mapping import NativeAllocation
    loads=[dict(load_name=str(i),bus=bus,phases=[1,2,3],base_p_kw=p,base_q_kvar=q)
           for i,(bus,p,q) in enumerate([('65',30.,15.),('65',60.,30.),('76',15.,6.),('76',45.,18.)])]
    allocation=NativeAllocation.from_adapter({'loads':loads})
    p={(bus,ph):v for bus,v in [('65',37.),('76',19.)] for ph in 'ABC'}
    q={(bus,ph):v for bus,v in [('65',13.),('76',7.)] for ph in 'ABC'}
    totals,ledger,audit=allocation.allocate(p,q)
    for key in p:
        assert sum(r['allocated_P_kw'] for r in ledger if (r['bus'],r['phase'])==key)==pytest.approx(p[key])
        assert sum(r['allocated_Q_kvar'] for r in ledger if (r['bus'],r['phase'])==key)==pytest.approx(q[key])
    assert audit['BACKGROUND_DUPLICATION_KW']==0
