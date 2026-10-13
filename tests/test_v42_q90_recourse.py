"""Named synthetic source-row counterexamples, no optimizer or AC execution."""
from copy import deepcopy

import numpy as np
import pytest

from test_v42_integration_sensitivity_policy import fixture
from v42_integration.q90_recourse import load_nominal_service, evaluate_q90_recourse
from v42_integration.q90_recourse import _Admission


def inputs(**kwargs):
    packet, _, q50, _, _, _, bindings, _ = fixture(**kwargs)
    a = deepcopy(packet.aidc_plan)
    a.update(resource_sites=list(packet.sites), nominal_site_GPU={s:[1.]*96 for s in packet.sites},
             known_site_GPU={s:[0.]*96 for s in packet.sites},
             CC4_service={str((h,t)):.5 for h in range(24) for t in range(4*h,4*h+4)},
             CC4_carryout={str(h):0. for h in range(24)})
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=bindings['cc4_sha'],
                   kernel_sha='NAMED_FIXTURE_KERNEL_REFERENCE',timing_envelope_sha='NAMED_FIXTURE_CDF')
    lo=np.zeros(100);hi=np.ones(100)
    n=load_nominal_service(a,q50,lo,hi,source_authority=authority)
    return packet,n,q50,lo,hi,authority,a


def run(values, extra=20., **kwargs):
    p,n,q50,lo,hi,a,_=values
    q90=q50.copy();q90[0]+=extra
    return evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a,**kwargs)


def test_nominal_x_site_and_carry_are_reused_without_kernel_execution():
    values=inputs();before=deepcopy(values[1]);r=run(values)
    assert values[1]==before
    assert r['source_original_A2_nominal_unchanged']
    assert not r['kernel_is_fixed_execution_schedule']
    assert r['mass']['conservation_PASS']
    assert not r['job_QoS_certified'] and not r['whole_gang_schedulability_certified']


def test_capacity_overload_preserves_all_work_as_service_or_carry():
    r=run(inputs(),extra=18720.)
    assert r['original_Q90_GPUh']==pytest.approx(18768.)
    assert r['mass']['extra_arrived_GPUh']==pytest.approx(18720.)
    assert r['mass']['extra_served_GPUh']+r['extra_carryout_GPUh']==pytest.approx(18720.)
    assert r['extra_carryout_GPUh']>18000
    assert r['physical_hard_feasible']
    assert np.max(r['physical_site_GPU'])<=8+1e-9
    assert r['terminal_pending_GPUh']==0
    assert r['risk_total_unfinished_GPUh']==pytest.approx(r['extra_carryout_GPUh'])


def test_500_gpuh_arrival_200_gpu_headroom_is_queued_then_served_later():
    values=inputs(destination_slope=0.)
    values[0].capacities={'A':1.,'B':201.}
    r=run(values,extra=500.)
    extra=np.array(r['admitted_extra_site_GPU'])
    assert extra[0].sum()==pytest.approx(200.)
    assert extra[:4].sum()/4==pytest.approx(200.)
    assert r['backlog_GPUh_by_slot'][3]==pytest.approx(300.)
    assert extra[4:10].sum()/4==pytest.approx(300.)
    assert r['backlog_GPUh_by_slot'][9]==pytest.approx(0.)
    assert r['extra_carryout_GPUh']==pytest.approx(0.)
    assert r['mass']['extra_served_GPUh']==pytest.approx(500.)
    assert r['physical_hard_feasible']


def test_q90_source_24408_mass_and_original_nominal_5503_not_double_added():
    p,n,_,lo,hi,a,_=inputs()
    # Separate aggregate scale fixture; nominal remains the original 48GPUh.
    q90=np.full(24,24408./24)
    r=evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a)
    assert r['original_Q90_GPUh']==pytest.approx(24408.)
    assert r['extra_demand_GPUh']==pytest.approx(24408.-48.)
    assert r['original_Q50_GPUh']+r['extra_demand_GPUh']==pytest.approx(24408.)


def test_cdf_upper_releases_service_later_without_fixed_kernel():
    p,n,q50,lo,hi,a,_=inputs();hi[:4]=0
    # This modified fixture CDF applies to extra recourse only; nominal is frozen.
    q90=q50.copy();q90[0]+=1
    r=evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a)
    x=np.array(r['extra_x_GPUh'])
    assert x[0,:4].sum()==0 and x[0,4:].sum()==pytest.approx(1)
    assert r['CDF_timing_feasible']


def test_lower_infeasibility_is_explicit_timing_risk_with_safe_physical_profile():
    p,n,q50,lo,hi,a,_=inputs();lo[:]=1
    q90=q50.copy();q90[0]+=1000
    r=evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a)
    assert r['physical_hard_feasible']
    assert not r['CDF_timing_feasible']
    assert r['status']=='TIMING_INFEASIBLE'
    assert r['CDF_lower_max_deficit_GPUh']>900
    assert r['mass']['conservation_PASS']


@pytest.mark.parametrize('kind',['voltage','transformer_current','transformer_kva','line'])
def test_every_original_signed_hard_family_bounds_admitted_extra(kind):
    kwargs=dict(destination_slope=.6 if kind=='line' else 0.,
        voltage_slope=.3 if kind=='voltage' else 0.,
        transformer_slope=.6 if kind=='transformer_current' else 0.,
        kva_rating=.1 if kind=='transformer_kva' else None)
    values=inputs(**kwargs);r=run(values,extra=1000.)
    assert r['physical_hard_feasible']
    assert r['original_grid_score']['hard_feasible']
    extra=np.array(r['admitted_extra_site_GPU'])
    for t in range(96):assert not values[0]._at_slot(t,extra[t])[1]


def test_future_rebound_guard_is_retained_for_q50_candidate():
    values=inputs(destination_slope=0.);delta=np.zeros((96,2));delta[1,0]=1
    r=run(values,extra=0,candidate_gpu_delta=delta)
    assert not r['physical_hard_feasible']
    assert r['status']=='FIXED_Q50_PHYSICAL_HARD_INFEASIBLE'
    assert any(v['slot']==1 for v in r['original_grid_score']['violations'])


def test_candidate_changes_to_past_are_rejected():
    delta=np.zeros((96,2));delta[0,0]=1
    with pytest.raises(ValueError,match='PAST_PHYSICAL'):
        run(inputs(),candidate_gpu_delta=delta,remaining_slot=1)


def test_mid_cohort_requires_explicit_remaining_and_prior_mass():
    values=inputs();p,n,q50,lo,hi,a,_=values;q90=q50.copy();q90[0]+=10
    with pytest.raises(ValueError,match='EXPLICIT_REMAINING'):
        evaluate_q90_recourse(p,n,q90,lo,hi,begin=1,remaining_slot=1,source_authority=a)
    work=np.zeros(24);work[0]=8
    with pytest.raises(ValueError,match='HISTORY_REQUIRED'):
        evaluate_q90_recourse(p,n,q90,lo,hi,begin=1,remaining_slot=1,
            remaining_work_GPUh=work,source_authority=a)
    r=evaluate_q90_recourse(p,n,q90,lo,hi,begin=1,remaining_slot=1,
        remaining_work_GPUh=work,served_before={0:2},source_authority=a)
    assert np.array(r['extra_x_GPUh'])[:,:1].sum()==0
    assert r['prior_served_GPUh']==2
    assert r['mass']['extra_served_GPUh']+r['extra_carryout_GPUh']==pytest.approx(10)


def test_source_cdf_short_horizon_tail_is_carried_without_mass_loss():
    p,n,q50,_,_,a,_=inputs();lo=np.zeros(1);hi=np.ones(1)
    q90=q50.copy();q90[23]+=100
    r=evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a)
    assert r['extra_carryout_GPUh']>95
    assert np.array(r['extra_x_GPUh'])[23,:92].sum()==0
    assert r['mass']['conservation_PASS']


def test_explicit_prior_service_cannot_borrow_a_future_cohort():
    p,n,q50,lo,hi,a,_=inputs();q90=q50.copy();q90[1]+=10
    work=np.zeros(24);work[1]=8
    with pytest.raises(ValueError,match='PRECEDE_COHORT_ARRIVAL'):
        evaluate_q90_recourse(p,n,q90,lo,hi,begin=1,remaining_slot=1,
            remaining_work_GPUh=work,served_before={1:2},source_authority=a)


def test_frozen_known_and_literal_source_quantiles_cannot_drift():
    values=inputs();p,n,q50,lo,hi,a,_=values
    n=deepcopy(n);n['known_site_GPU'][0][0]=1
    with pytest.raises(ValueError,match='KNOWN_PROFILE_DRIFT'):
        evaluate_q90_recourse(p,n,q50,lo,hi,source_authority=a)
    a=dict(a,q50_hourly_GPUh=q50.tolist());changed=q50.copy();changed[0]+=1
    with pytest.raises(ValueError,match='LITERAL_SOURCE'):
        load_nominal_service(values[6],changed,lo,hi,source_authority=a)


def test_nominal_frozen_receipt_cannot_be_rewritten_between_candidates():
    values=inputs();p,n,q50,lo,hi,a,_=values
    changed=deepcopy(n);changed['x_GPUh'][0][0]+=1
    with pytest.raises(ValueError,match='NOMINAL_SERVICE_RECEIPT_CHANGED'):
        evaluate_q90_recourse(p,changed,q50,lo,hi,source_authority=a)


def test_vectorized_guard_matches_literal_original_scalar_for_signed_rows():
    for kwargs in (dict(destination_slope=.6),dict(voltage_slope=.3),
                   dict(transformer_slope=.6),dict(kva_rating=.1)):
        p=inputs(**kwargs)[0];a=_Admission(p)
        for t in (0,1,95):
            for delta in ([0,0],[1,-1],[0,.05],[0,2],[-1,0]):
                vector=np.array(delta,float)
                assert a.safe(t,vector)==(not p._at_slot(t,vector)[1])


def test_recourse_cache_is_bound_to_caps_event_delta_cdf_and_output_is_isolated():
    values=inputs();first=run(values);again=run(values)
    assert not first['runtime_cache']['hit'] and again['runtime_cache']['hit']
    again['admitted_extra_site_GPU'][0][0]=999
    assert run(values)['admitted_extra_site_GPU'][0][0]!=999
    changed=run(values,remaining_slot=1)
    assert not changed['runtime_cache']['hit']
    values[0].capacities['A']=2
    changed=run(values)
    assert not changed['runtime_cache']['hit']
    p,n,q50,lo,hi,a,_=values;q90=q50.copy();q90[0]+=20
    hi=hi.copy();hi[:2]=0
    changed=evaluate_q90_recourse(p,n,q90,lo,hi,source_authority=a)
    assert not changed['runtime_cache']['hit']


def test_original_nominal_mass_cdf_or_site_projection_failure_is_not_regenerated():
    values=inputs();_,_,q50,lo,hi,a,plan=values
    for mutation in ('mass','site','cdf'):
        changed=deepcopy(plan);low=lo.copy()
        if mutation=='mass':changed['CC4_carryout']['0']=1
        if mutation=='site':changed['nominal_site_GPU']['A'][0]=2
        if mutation=='cdf':low[:]=1
        with pytest.raises(ValueError,match='SOURCE_REPLAY_FAILED'):
            load_nominal_service(changed,q50,low,hi,source_authority=a)


def test_nonzero_nominal_carry_reported_separately_from_extra_carry():
    values=inputs();p,_,q50,lo,hi,a,plan=values
    for t in range(4):plan['CC4_service'][str((0,t))]=0.;plan['nominal_site_GPU']['A'][t]=0.;plan['nominal_site_GPU']['B'][t]=0.
    plan['CC4_carryout']['0']=2.
    n=load_nominal_service(plan,q50,lo,hi,source_authority=a)
    # Physical packet still frozen to the source fixture: no fake conversion
    # into a fresh A2 control; test only carry accounting with zero extra.
    r=evaluate_q90_recourse(p,n,q50,lo,hi,source_authority=a)
    assert r['nominal_carryout_GPUh']==2
    assert r['extra_carryout_GPUh']==0
    assert r['risk_total_unfinished_GPUh']==2
