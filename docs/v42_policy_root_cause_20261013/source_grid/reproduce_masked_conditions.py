"""Controlled frozen-code checks. No Production replay, model, solver or AC."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('D:/v42_policy_root_cause_20261013')
OUT = ROOT/'audit/source_grid'
sys.dont_write_bytecode = True
sys.path.insert(0,str(ROOT))
from v42_integration.sensitivity_policy import FrozenSensitivityPolicy,compile_sensitivity_policy
from v42_integration.policy import ReservationLedger
from v42_job_capability import Job,Option,Resources,ServiceBoundary,validate


def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')


path=Path('D:/v42_integration_validation_20261013/POLICY_V5_OFFLINE_FIXTURE/PLACEMENT_BENEFIT/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json')
policy=FrozenSensitivityPolicy.load(path)
metadata=dict(uid='CONTROLLED_OBSERVED_PLACEMENT_REQUEST',submit_seconds=0.,event_seconds=0.,state='PENDING',
    qos='normal',protected=False,batch_eligible=True,is_observed=True,gpu=1,t50_seconds=900.,
    nominal_service_seconds=900.,source_site='A',reference_site='A',compatible_sites=['A','B'],
    can_prestart_place=True,cumulative_migration_interruption_seconds=0.)
receipt=dict(uid=metadata['uid'],case_sha='FIXTURE_CASE',reference_start_seconds=0.,
             budget_seconds=0.,allowed_starts_seconds=[0.])
outcomes=[]
for protected,batch in [(False,True),(False,None),(False,False),(None,None),(True,None)]:
    observed=dict(metadata,protected=protected,batch_eligible=batch)
    candidates,reason=policy.candidates(observed,receipt,0.)
    selected=policy.select(observed,receipt,0.,ReservationLedger({'A':8,'B':8}),reserve=False)
    outcomes.append(dict(protected=protected,batch_eligible=batch,candidate_reason=reason,
        candidates=[{k:r[k] for k in ('action','site','start_seconds','additional_start_delay_seconds')} for r in candidates],
        selection=selected))
# Original physical validator independently allows a source-residency-authorized
# PENDING site choice at the exact reference start with zero temporal budget.
job=Job('SOURCE_CONTRACT_FIXTURE','PENDING',0,0,0,'A',1,1,initial_sites=('A','B'),
        protected=True,qos='high',qos_policy_id='FIXTURE_SHARED_ZERO_BUDGET',
        qos_allowed_starts=(0,),qos_budget_seconds=0,is_observed=True,qos_receipt_sha='c'*64,
        duration_authority='NAMED_SOURCE_CONTRACT_NOMINAL_FIXTURE')
boundary=ServiceBoundary('SOURCE_CONTRACT_FIXTURE',True,True,(0,),4)
resources=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},{},{},4,1,{},{},{})
validate(job,Option(0,'B',(('B',0,1),)),boundary,resources)
write('PREPLACE_ZERO_BUDGET_UNIVERSAL_MASK_REPRODUCTION.json',dict(
    scope='CONTROLLED_SOURCE_CAPABILITY_FIXTURE_ONLY;NOT_A_MAY_ACTION',source_policy=str(path),
    unchanged_policy_sha=policy.sha,unchanged_job_budget_seconds=0.,outcomes=outcomes,
    original_source_validator_accepts_zero_delay_preplacement=True,
    implementation_bug='FrozenSensitivityPolicy.lookup checks delay batch/protection authority before independent zero-delay placement capability.',
    current_May_causal_effect='MASKED_BY_COMPILER_ZERO_ORDERED_ACTIONS_AND_OBSERVED_RESOURCE_GUARD',
    production_actual_replayed=False,Native_Optimize_calls=0,AC_calls=0,source_edits=0))

spec=importlib.util.spec_from_file_location('frozen_policy_source_fixture',ROOT/'tests/test_v42_integration_sensitivity_policy.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
values=fixture.fixture(profile='placement',q90_extra=3.)
packet,envelope,q50,q90,kernel,prototype,bindings,authority=values
prototype=dict(prototype,time_slots=[2])
compiled=compile_sensitivity_policy(packet,envelope,q50,q90,kernel,[prototype],bindings,authority)
scores=compiled.document['templates'][0]['scenario_comparisons']
rejected=compiled.document['templates'][0]['rejected_candidates']
future_grid=packet.evaluate(__import__('numpy').zeros((96,2)),remaining_slot=2,
                            scenario_gpu=authority['stress_site_GPU'])
write('PAST_SLOT_CAPACITY_VETO_REPRODUCTION.json',dict(
    scope='CONTROLLED_FROZEN_CODE_FIXTURE_ONLY;NOT_A_MAY_ACTION',template_slot=2,
    stress_nonzero_only_slot0=True,past_slot0_B_GPU=13.,site_B_capacity=8.,
    all_current_future_slot_GPU_within_capacity=True,
    current_future_original_grid_replay=future_grid,
    serialized_candidate_scores=scores,serialized_rejections=rejected,
    ordered_actions=compiled.document['templates'][0]['ordered_actions'],
    implementation_bug='Compiler capacity test checks total[0:96] while grid test uses remaining_slot=2; historical stress overload vetoes current/future actions.',
    current_May_causal_effect='MASKED_BY_INDEPENDENT_FUTURE_SLOT95_STRESS_OVERLOAD',
    production_actual_replayed=False,Native_Optimize_calls=0,AC_calls=0,source_edits=0))
print(json.dumps(dict(zero_budget_source_PREPLACE_ACCEPTED=outcomes[0]['selection']['action'],
    unconfirmed_batch_reason=outcomes[1]['candidate_reason'],
    past_stress_future_grid_hard_feasible=future_grid['hard_feasible'],
    past_stress_compiler_approved=len(compiled.document['templates'][0]['ordered_actions']),
    evaluated_candidates=len(scores),Native_calls=0)))
