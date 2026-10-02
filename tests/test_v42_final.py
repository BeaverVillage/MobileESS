from dataclasses import replace
from itertools import product
import ast
import math
import numpy as np
import pytest
import gurobipy as gp
from v42_final.common import OUT,ROOT,read,sha
from v42_final.runtime import FrozenQ50
from v42_final.state import EpisodeLedger,planning_remaining,conditional_wait,legacy_unassigned
from v42_final.workload import execution_lag_kernel,profile,ForecastBook
from v42_final.reserve import survival,risk_exposure,calibrate,bind_headroom
from v42_final.resource_certificate import bounds
from v42_final.gates import require_a1,require_next,require_kernel
from v42_job_capability import Job,Resources,ServiceBoundary,build_domain
from v42_native.solver import assert_milp
from v42_final.native import canonical_jobs


class ConstantProvider:
    def predict_total(self,metadata,**kwargs):return 900.


def ledger():
    x=EpisodeLedger({'A':4,'B':4})
    x.submit('j',0,0,4,{},ConstantProvider())
    return x


def book():return ForecastBook(tuple([10.]*24),tuple([15.]*24),0.)


@pytest.fixture(scope='module')
def provider():return FrozenQ50()


def test_provider_reproduction_sealed_and_no_training_api():
    r=read(OUT/'FROZEN_FOLD5_PROVIDER_REPRODUCTION.json')
    assert r['PASS']
    for p in (ROOT/'v42_final/inference').glob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf8'))
        assert not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('fit','train','fit_map','fit_model') for n in ast.walk(tree))
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('fit','train') for n in ast.walk(tree))


def test_provider_one_live_call_same_known_unknown(provider,monkeypatch):
    import lightgbm
    monkeypatch.setattr(lightgbm,'train',lambda *a,**k:pytest.fail('Runtime training invoked'))
    r=dict(num_gpus_req=1,num_nodes_req=1,num_cores_req=4,requested_memory_mib=1024,
           requested_seconds=3600,array_index=0,account='not-in-map',qos='normal',partition='gpu-a100')
    q=provider.predict_batch([r,r],submit_times=['2025-04-29T00:00:00Z','2025-05-01T00:00:00Z'],event_time='2025-05-01T00:00:00Z')
    assert np.isfinite(q).all() and q[0]>0 and q[0]==q[1]


@pytest.mark.parametrize('event,submit,reason',[
    ('2025-03-30T00:00:00Z','2025-03-29T00:00:00Z','EVENT_BEFORE'),
    ('2025-05-01T00:00:00Z','2025-05-02T00:00:00Z','NOT_YET_SUBMITTED')])
def test_runtime_availability_firewalls(provider,event,submit,reason):
    with pytest.raises(ValueError,match=reason):provider.predict_total({},submit_time=submit,event_time=event)


@pytest.mark.parametrize('key',['completion_time','elapsed_seconds','actual_remaining','state_at_issue'])
def test_runtime_rejects_outcome_or_state_features(provider,key):
    with pytest.raises(ValueError,match='FUTURE_OR_STATE'):provider.parameters([{key:1}])


def test_pending_zero_and_running_past_q50_full_gang():
    x=ledger();assert x.physical(0)=={'A':0,'B':0}
    x.start('j','A',0,'ep1');assert x.physical(100000)=={'A':4,'B':0}
    assert x.jobs['j']['latest_observed_state']=='RUNNING'


def test_q50_expired_planning_zero_future_nominal_but_hard_now():
    r=planning_remaining(900,1800,state='RUNNING')
    assert r['nominal_slots']==0 and r['observed_running_hard'] and r['overrun_uncertainty']
    assert not r['synthetic_completion'] and r['actual_runtime_reserve_GPU']==0
    assert planning_remaining(900,0,state='PENDING')['nominal_slots']==1


def test_actual_completion_releases_at_next_control_boundary():
    x=ledger();x.start('j','A',0,'ep1');x.complete('j',901,901)
    assert x.physical(1799)['A']==4 and x.physical(1800)['A']==0


def test_exact_boundary_completion_can_release_current_control():
    x=ledger();x.start('j','A',0,'ep1');x.complete('j',900,900)
    assert x.physical(900)['A']==0


def test_preserve_overrun_and_reject_pending_start_without_capacity():
    x=ledger();x.start('j','A',0,'ep1');x.submit('k',1000,1000,1,{},ConstantProvider())
    with pytest.raises(ValueError,match='PHYSICAL_CAPACITY'):x.start('k','A',1000,'ep2')
    assert x.jobs['j']['latest_observed_state']=='RUNNING' and x.jobs['k']['latest_observed_state']=='PENDING'


def test_running_site_requires_verified_one_time_receipt():
    x=ledger();x.start('j','A',0,'ep1')
    with pytest.raises(ValueError,match='REQUIRES_RECEIPT'):x.observe_running('j','B',1800)
    receipt=dict(id='r1',job_id='j',episode_id='ep1',source='A',destination='B',completed_at=1800)
    with pytest.raises(ValueError,match='VALIDATION'):x.migrate('j','B',1800,receipt,lambda r,j:False)
    x.migrate('j','B',1800,receipt,lambda r,j:True)
    assert x.physical(1800)=={'A':0,'B':4} and x.jobs['j']['initial_site']=='A'
    with pytest.raises(ValueError,match='ONE_AUTHORIZED'):x.migrate('j','A',2700,receipt,lambda r,j:True)


def test_no_future_completion_or_time_reversal():
    x=ledger();x.start('j','A',0,'ep1')
    with pytest.raises(ValueError,match='OBSERVED_COMPLETION'):x.complete('j',2000,1000)
    x.observe_running('j','A',1000)
    with pytest.raises(ValueError,match='NONCAUSAL'):x.observe_running('j','A',900)


def test_unknown_submission_depletes_forecast_without_physical_work():
    f=book();x=EpisodeLedger({'A':4});x.submit('j',0,0,4,{},ConstantProvider(),f)
    assert x.physical(0)['A']==0
    r=f.row(0,0);assert r['remaining_CC4_Q50_GPUh']==9 and r['explicit_plus_anonymous_nominal_GPUh']==10


def test_lag_exact_partial_slot_mass_and_normalization():
    k,m=execution_lag_kernel([0],[450],[2250],[4])
    assert m.tolist()==[.5,1.,.5] and k.tolist()==[.25,.5,.25]
    assert k.sum()==1 and sum(m)==2


def test_gpu_hours_profile_full_tail_and_no_same_hour_binding():
    k=np.zeros(100);k[99]=1
    p=profile([10,20],k)
    assert p[:99].sum()==0 and p[99]==40 and p[103]==80
    assert p.sum()*.25==30


@pytest.mark.parametrize('args',[([0],[0,1],[2],[1]),([0],[2],[1],[1]),([0],[0],[1],[0])])
def test_lag_invalid_sources_fail(args):
    with pytest.raises(ValueError):execution_lag_kernel(*args)


def test_depletion_q50_q90_identity_and_overforecast():
    f=book();f.submit('j',0,0,4,7200)
    r=f.row(0,0);assert (r['remaining_CC4_Q50_GPUh'],r['remaining_CC4_Q90_GPUh'],r['remaining_CC4_reserve_GPUh'])==(2,7,5)
    f.submit('k',1,1,4,7200);r=f.row(0,1)
    assert r['remaining_CC4_Q50_GPUh']==r['remaining_CC4_Q90_GPUh']==0
    assert r['explicit_plus_anonymous_nominal_GPUh']==16


def test_depletion_duplicate_future_submission_and_closed_hour():
    f=book();f.submit('j',0,0,1,3600)
    with pytest.raises(ValueError,match='DUPLICATE'):f.submit('j',0,1,1,3600)
    with pytest.raises(ValueError,match='NONCAUSAL'):f.submit('k',100,50,1,3600)
    r=f.row(0,3600);assert r['remaining_CC4_Q50_GPUh']==r['remaining_CC4_Q90_GPUh']==0
    assert r['realized_submitted_nominal_work_GPUh']==1 and 'j' in f.submissions
    f.submit('late_observation',3599,3601,1,3600)
    assert f.row(0,3601)['remaining_CC4_Q50_GPUh']==0


def test_survival_and_site_local_selected_exposure():
    s=survival([900,1800,3600],[900,900,900],5)
    assert np.all(np.diff(s)<=0) and s[0]==pytest.approx(2/3) and s[-1]==0
    a=risk_exposure(4,2,'B',s,range(7),current_hard_slot=2)
    assert set(k[0] for k in a)=={'B'} and ('B',1) not in a and ('B',2) not in a
    assert a['B',3]==pytest.approx(4/3)


def test_reserve_scale_cal_only_and_unseen_support_fail():
    kw=dict(role='CAL',event_times=[0,1],prediction_available_times=[0,0],observation_cutoff=2)
    assert calibrate([1,2],[1,1],**kw)['gamma_90']==2
    with pytest.raises(ValueError,match='ZERO_EXPOSURE'):calibrate([1,2],[0,1],**kw)
    with pytest.raises(ValueError,match='ONLY_CAL'):calibrate([1,2],[1,1],**dict(kw,role='VALID'))
    with pytest.raises(ValueError,match='FUTURE'):calibrate([1,2],[1,1],**dict(kw,prediction_available_times=[1,1]))
    with pytest.raises(ValueError,match='TIME_AXIS'):calibrate([1,2],[1,1],**dict(kw,event_times=[0]))


def test_frozen_gamma_holdout_not_retuned_or_retrospective():
    r=read(OUT/'RUNTIME_RESERVE_HOLDOUT_RECEIPT.json');c=read(OUT/'RUNTIME_RESERVE_CALIBRATION.json')
    assert r['calibration_sha_before']==r['calibration_sha_after']==sha(OUT/'RUNTIME_RESERVE_CALIBRATION.json')
    assert r['gamma_90']==c['gamma_90'] and r['validation_executions']==1 and not r['gamma_changed']
    a=read(OUT/'RUNTIME_OOF_CAUSALITY_AUDIT.json');assert a['PASS'] and a['March31_retrospective_predictions']==0


def test_linear_reserve_headroom_separate_shortfalls_and_no_energy():
    m=gp.Model();m.Params.OutputFlag=0
    try:
        x=bind_headroom(m,{('A',0):3},{('A',0):1},{('A',0):2},{('A',0):3},{'A':5},[0])
        m.setObjective(x['CC4_shortfall']+x['runtime_shortfall']);m.optimize()
        assert m.ObjVal==pytest.approx(4) and x['reserve_is_electrical_load'] is False
        assert x['P1_modified'] is False and x['objective_layer']=='P2_ONLY'
        assert_milp(m)
    finally:m.dispose()


@pytest.mark.parametrize('state,protected',[('RUNNING',False),('PENDING',True)])
def test_timeshift_state_and_protected_failclosed(state,protected):
    assert conditional_wait(state,protected,0,[3600]*100)[:2]==(False,0)


def test_conditional_wait_is_strict_age_filtered_and_floored():
    assert conditional_wait('PENDING',False,1800,[1800]*100+[3599]*99)[:3]==(False,0,99)
    assert conditional_wait('PENDING',False,1800,[1800]*100+[3599]*100)[:3]==(True,1,100)
    assert conditional_wait('PENDING',False,1800,[2699]*100)[:2]==(False,0)
    # No runtime, QoS standby shortcut, or target share is an argument.


def test_legacy_44_source_authorized_external_only():
    b=read(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json')
    assert len(legacy_unassigned(b['known_population']))==44
    bad=[dict(legacy_unassigned(b['known_population'])[0],reference_end=25)]
    with pytest.raises(ValueError,match='UNASSIGNED_OVERLAPPING'):legacy_unassigned(bad)


def test_canonical_native_view_uses_q50_mass_and_expired_running_truth():
    b=read(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');rows=canonical_jobs(b)
    assert len(rows)==1605
    for r in rows:
        assert r['nominal_reserved_GPUh']==r['nominal_slots']*r['GPU_gang']/4
        assert r['nominal_slots']==math.ceil(r['exact_compute_seconds']/900)
        assert r['current_physical_GPU']==(r['GPU_gang'] if r['state']=='RUNNING' else 0)
        if not r['nominal_slots']:assert not r['can_checkpoint_migrate'] and r['current_physical_GPU']>0
    assert sum(r['can_checkpoint_migrate'] for r in rows)==1122


def test_runtime_bundle_tampering_fails_before_model_load(tmp_path):
    import shutil
    target=tmp_path/'bundle';shutil.copytree(ROOT/'v42_final/runtime_bundle',target)
    with (target/'model/model.json').open('ab') as f:f.write(b' ')
    with pytest.raises(ValueError,match='FROZEN_PROVIDER_SHA'):FrozenQ50(target)


@pytest.mark.parametrize('restart,active',[(1,1),(2,1),(1,2)])
def test_resource_bound_against_exhaustive_complete_options(restart,active):
    H=7
    r=Resources({'A':100,'B':100},{'A':(100,),'B':(100,)},
        {('L',t):100 for t in range(H)},{('A','B'):('L',),('B','A'):('L',)},H,1,{}, {}, {},restart_slots=restart,max_active_transfers=active)
    js=[Job(str(i),'PENDING',0,0,0,'A',6,g,initial_sites=('A','B'),checkpoint_authorized=True,duration_authority='SYNTHETIC_TEST') for i,g in enumerate((1,2,4))]
    domain=[build_domain(j,ServiceBoundary('TEST',True,True,(0,),H+6),r)[0] for j in js]
    rows=bounds([dict(job_uid=j.uid,can_timeshift=False,reference_start_if_authorized=0,reference_end=6,service_slots=6,GPU_gang=j.gpu) for j in js],
                [0]*H,r.capacities,begin=0,end=H,max_active=active)
    count=0
    for options in product(*domain):
        if any(sum(o.migrated and o.transfer_start<=t<o.transfer_end for o in options)>active for t in range(H)):continue
        count+=1
        for t,row in enumerate(rows):
            physical=sum(j.gpu for j,o in zip(js,options) if any(a<=t<b for _,a,b in o.segments))
            assert physical>=row['known_GPU_lower_bound']
            suspended=[o for o in options if o.migrated and o.checkpoint<=t<o.restart_end]
            assert len(suspended)<=active*(H-t-1)
    assert count>100


def test_native_certificate_recomputed_independently_and_gate_stops():
    b=read(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');r=read(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json')
    live=[j for j in b['known_population'] if j['planning_eligible'] and j['reference_start_if_authorized']<=44<j['reference_end']]
    g=sorted((j['GPU_gang'] for j in live),reverse=True)
    assert len(g)==416 and sum(g)==443 and sum(g[:75])==102
    assert sum(g[75:])+b['unknown_nominal_GPU'][20]==pytest.approx(795.2690275946557)
    assert r['full_A1_infeasible_proven']
    with pytest.raises(ValueError,match='STOP_BEFORE_A1'):require_a1(r)
    require_a1(dict(PASS=True,full_A1_authorized_after_this_PASS=True))


def test_resource_bound_rejects_changed_timeshift_assumption():
    with pytest.raises(ValueError,match='ZERO_TS'):bounds([{'can_timeshift':True}],[0],{'A':1},begin=0,end=1)


def test_canonical_stages_and_fresh_ac_before_kernel():
    require_next('A1',{})
    with pytest.raises(ValueError,match='PRIOR_NATIVE'):require_next('M1',{})
    with pytest.raises(ValueError,match='PRIOR_NATIVE'):require_next('M2',{'A1':{'accepted_native_plan':True}})
    plan=dict(stage='M2',accepted_native_plan=True,sha256='a'*64)
    upstream={k:'b'*64 for k in ('workload','placement','runtime','MESS_PQ','grid_anchor')}
    with pytest.raises(ValueError,match='FRESH_AC'):require_kernel(plan,{'PASS':False},upstream)
    with pytest.raises(ValueError,match='FRESH_AC'):require_kernel(plan,{'PASS':True,'plan_sha':'c'*64},upstream)
    with pytest.raises(ValueError,match='FRESH_AC'):
        require_kernel(plan,{'PASS':True,'plan_sha':'a'*64},upstream)
    assert require_kernel(plan,{'PASS':True,'plan_sha':'a'*64,'execution_layer':'DDAY_ACTUAL'},upstream)
    assert not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists()
