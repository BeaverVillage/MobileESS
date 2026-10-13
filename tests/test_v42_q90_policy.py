"""Regression for repeated PREPLACE delay evidence and risk semantics."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v42_integration.q90_policy import compile_queue_aware_policy
from v42_integration.sensitivity_policy import POLICY_ID


def sources():
    bindings={k:k for k in ('science_sha','qos_sha','case_sha','aidc_anchor','mess_anchor',
        'cc4_sha','runtime_sha','response_sha','initial_state_sha')}
    comparisons=[dict(action='PREPLACE',site='B',delay_seconds=d,
        scenario_scores={'NOMINAL_Q50':.6,'HIGH_DEMAND_Q90':1.1},hard_feasible=False) for d in (0,900)]
    rejected=[dict(action='PREPLACE',site='B',scenarios={
        'NOMINAL_Q50':dict(peak_score=.6,hard_feasible=allowed,runtime_bucket_piecewise_endpoints_seconds=[900]),
        'HIGH_DEMAND_Q90':dict(peak_score=1.1,hard_feasible=False)}) for allowed in (True,False)]
    template=dict(template_id='NAMED_FIXTURE',time_slot=0,state='PENDING',qos='normal',gpu=1,
        reference_site='A',service_seconds=900,runtime_lower_seconds=0,runtime_upper_seconds=900,
        ordered_actions=[],scenario_comparisons=comparisons,rejected_candidates=rejected)
    doc=dict(policy_version=POLICY_ID,bindings=bindings,templates=[template],
        metrics=dict(bounded_candidates=2),envelope=[],scenario_audit={},candidate_comparison_audit=[],
        begin_seconds=0,end_seconds=86400,site_axis=['A','B'],runtime_resource_baseline_GPU=[[0,0]]*96,
        runtime_resource_support=None)
    frozen=SimpleNamespace(document=doc,bindings=bindings)
    packet=SimpleNamespace(sites=('A','B'),capacities={'A':8,'B':8},begin_seconds=0)
    return frozen,packet


def recourse(*args,**kwargs):
    return dict(physical_hard_feasible=True,original_grid_score=dict(hard_feasible=True,peak_score=.8),
        mass=dict(extra_terminal_backlog_GPUh=1.),CDF_timing_status='MET',CDF_timing_violations=[],
        CDF_lower_max_deficit_GPUh=0.,queue_area_GPUh_hours=1.)


def test_preplacement_delays_bind_exact_frozen_variant_order_not_last_reject():
    frozen,packet=sources()
    with patch('v42_integration.q90_policy.evaluate_q90_recourse',recourse):
        result=compile_queue_aware_policy(frozen,packet,{},[0.]*24,[0.],[1.],
            bindings=frozen.bindings,source_authority={})
    assert result['new_approved']==1
    action=result['policy'].document['templates'][0]['ordered_actions'][0]
    assert action['delay_seconds']==0
    assert action['q90_queue_risk']['timing_risk'] is False
    assert result['funnel'][1]['q90_queue_aware_status']=='NOT_RUN_Q50_HARD_REJECTED'


@pytest.mark.parametrize('field,value',[('action','DELAY_15'),('site','A')])
def test_mismatched_frozen_ordinal_is_rejected(field,value):
    frozen,packet=sources();frozen.document['templates'][0]['rejected_candidates'][0][field]=value
    with pytest.raises(ValueError,match='ORDINAL'):
        compile_queue_aware_policy(frozen,packet,{},[0.]*24,[0.],[1.],
            bindings=frozen.bindings,source_authority={})


def test_changed_source_case_cannot_borrow_original_nominal_scores():
    frozen,packet=sources();bindings=dict(frozen.bindings,case_sha='CHANGED')
    with pytest.raises(ValueError,match='ANCHORS'):
        compile_queue_aware_policy(frozen,packet,{},[0.]*24,[0.],[1.],
            bindings=bindings,source_authority={})
