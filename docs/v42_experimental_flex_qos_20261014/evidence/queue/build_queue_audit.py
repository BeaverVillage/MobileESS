"""Native0 queue evidence; immutable PR223 inputs are read only."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path('D:/v42_experimental_flex_qos_20261014')
OUT=ROOT/'audit/queue'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from v42_integration.experimental_queue import fluid_queue,evaluate_q90_risk,rank_action_scores
from v42_integration.cc4_policy_inputs import _row


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def record(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def write(name,doc):
    (OUT/name).write_text(json.dumps(doc,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
def summary(queue):
    return {k:queue[k] for k in ('source_sha','arrived_GPUh','total_served_GPUh','remaining_work_GPUh',
        'carryout_GPUh','queue_at_day_end_GPUh','outside96_release_tail_GPUh','queue_GPUh_hours',
        'conservation_residual_GPUh','conservation_PASS','current_future_capacity_violation_cells')}


OUT.mkdir(parents=True,exist_ok=True)
started=perf_counter()
packet_path=Path('D:/v42_integration_validation_20261013/CC4_POLICY_SOURCE_AUDIT/CC4_SCENARIO_INPUTS.json')
source=read(packet_path)
for receipt in source['source_receipts']:
    observed=record(receipt['path'])
    if any(observed[key]!=receipt[key] for key in ('sha256','bytes')):
        raise ValueError('FROZEN_SOURCE_RECEIPT_DRIFT:'+receipt['path'])
prediction=next(r for r in source['source_receipts'] if r.get('role')=='prediction')
kernel_receipt=next(r for r in source['source_receipts'] if r.get('role')=='TRAIN_EXECUTION_LAG_KERNEL')
q,_shape=_row(prediction['path'],source['prediction_index'])
kernel=pd.read_csv(kernel_receipt['path'],usecols=['kappa']).kappa.to_numpy()
assert np.array_equal(q[:,1],source['q90_hourly_GPUh'])
assert np.array_equal(q[:,0],source['q50_hourly_GPUh'])
assert np.array_equal(kernel,source['kernel'])
native_path=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
native=read(native_path);caps=native['capacities'];sites=sorted(caps)
aidc_path=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/A2/A_RESULT.json')
aidc=read(aidc_path)
known=np.asarray([aidc['known_site_GPU'][s] for s in sites]).T
real=fluid_queue(source['q90_hourly_GPUh'],source['kernel'],caps,known_gpu=known,source_authority=source)
assert real['arrived_GPUh']==sum(source['q90_hourly_GPUh'])
empty_known=fluid_queue(source['q90_hourly_GPUh'],source['kernel'],caps,
    known_gpu=np.zeros_like(known),source_authority=source)
flat=np.full(24,24408./24)
fixture_source=dict(model_id='NAMED_SYNTHETIC_FLAT_24408_LIFETIME_KERNEL1',
    prediction_sha='a'*64,kernel_sha='b'*64,q90_hourly_GPUh=flat.tolist(),kernel=[1.],evidence_kind='FIXTURE')
overload=fluid_queue(flat,[1.],{'A':780},known_gpu=np.zeros((96,1)),source_authority=fixture_source)
assert overload['total_served_GPUh']==18720 and overload['carryout_GPUh']==5688
causal_source=dict(model_id='NAMED_OBSERVED_BACKLOG_RELEASE_FIXTURE',prediction_sha='a'*64,
    kernel_sha='b'*64,q90_hourly_GPUh=[0.]*24,kernel=[1.],evidence_kind='FIXTURE')
causal=fluid_queue([0.]*24,[1.],{'A':8,'B':8},known_gpu=np.zeros((96,2)),
    remaining_slot=90,causal_queue_start_slot=90,initial_backlog_gpu_h=100.,source_authority=causal_source)
assert causal['total_served_GPUh']==24 and causal['carryout_GPUh']==76
assert np.sum(np.asarray(causal['served_site_GPU'])[:90])==0
base=dict(policy_id='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',written_utc=datetime.now(timezone.utc).isoformat(),
    schema='Q90_QUEUE_CARRYOVER_REFORMULATION_V1',mode='NATIVE0_SOURCE_AND_OFFLINE_FLUID_RISK_ONLY',
    source_files=[record(ROOT/'v42_integration/experimental_queue.py'),record(ROOT/'tests/test_v42_experimental_queue.py')],
    source_receipts=[record(packet_path),record(native_path),record(aidc_path)]+source['source_receipts'],
    Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_runs=0,fit_calls=0,new_calibrator_calls=0,
    forecast_scaling_or_clipping=False,future_individual_UIDs=0,
    old_PR223_Artifact_Source_Science_unchanged=True,
    original_A_M_FULL_UB_LB_transfer_authorized=False,new_case_Science_SHA='PENDING_ROOT_FREEZE',
    phase_scope='CONDITIONAL_OFFLINE_FIXED_PR223_A2_REFERENCE;NEW_DECLARED_AGGREGATE_QUEUE_APPROXIMATION',
    original_A2_anchor=aidc['aidc_anchor'],model_id=source['model_id'],prediction_index=source['prediction_index'],
    prediction_sha=source['prediction_sha'],kernel_sha=source['kernel_sha'],runtime_sha=source['runtime_sha'])
write('Q90_ORIGINAL_SOURCE_CONSERVATION.json',dict(base,
    original_forecast_and_kernel_literal_bytewise=True,original_KERNEL_sum=float(kernel.sum()),
    no_kernel_renormalization=True,Q50_hourly_GPUh=source['q50_hourly_GPUh'],
    Q90_hourly_GPUh=source['q90_hourly_GPUh'],real_frozen_A2_known_headroom_queue=real,
    zero_known_capacity_reference_summary=summary(empty_known),
    synthetic_flat_kernel1_overload=overload,
    real_prediction_kernel_versus_fixture_scope='Production uses the literal6729-slot TRAIN kernel. Flat/kernel1 overload is a named unit fixture,not a modified production prediction/kernel.'))
write('Q90_QUEUE_CARRYOVER_REFORMULATION.json',dict(base,status='CONSERVATION_AND_GPU_HEADROOM_PASS;AGGREGATE_RISK_ONLY',
    source_Q50_GPUh=float(q[:,0].sum()),source_Q90_GPUh=float(q[:,1].sum()),
    installed_GPU=sum(caps.values()),installed_24h_GPUh=sum(caps.values())*24,
    real_kernel_slots=len(kernel),real_known_headroom=summary(real),
    zero_known_capacity_reference=summary(empty_known),
    controlled_flat_kernel1_24408_overload=summary(overload),
    causal_observed_backlog_release_fixture=dict(summary(causal),current_slot=90,
        observed_backlog_GPUh=100,initial_backlog_release_slot=90,past_service_GPUh=0,
        real_May_execution=False,default_offline_reconstruction_unchanged=True),
    service_conservation='Q90_forecast_lifetime_GPUh + initial_backlog = served_GPUh + eligible_backlog_at96 + outside96_service_release_tail',
    queue_and_release_proxy='OriginalTRAINexecution-lag service mass is explicitly reused as aggregate service-eligibility release;not a prediction of individual arrival/start/finish.',
    site_allocation='Frozen ascending site priority,fluidservicewithinunchangedGPUheadroom;no grid-dependent May tuning',
    Q50_Q90_semantics='Q50 remains primary P1 action score. FullQ90 queue served service replaces anonymousQ50 in its risk profile,never adds Q90raw lifetime demand or backlog to Actual occupancy.',
    reserved_profile_semantics='Only explicit physical/candidate reservations excluding anonymousQ50 forecast;Q90fullmass is not added on top of Q50.',
    Q90_backlog_blanket_veto=False,current_future_actual_and_Q50_hard_guards_required=True,
    original_signed_grid_rows_relaxed=False,Q90_grid_risk='Evaluated by unchanged OriginalGridPacket; violations remain hard_feasible=false riskdiagnostics,not erased or claimed ACsafe.',
    aggregate_fluid_not_whole_gang_rack_WAN_certificate=True,Q90_future_QoS_violation_estimate='NOT_ESTABLISHED_ANONYMOUS_FUTURE_CONTRACTS_UNKNOWN',
    risk_grid_real_May='NOT_RUN_IN_THIS_SOURCE_CONSERVATION_AUDIT',
    original_A2_target_versus_achieved='Preserved as historical PR223 evidence;new queue doesnot relabel arrival target as achievedreserve.',
    full96_Actual_or_AC_certification=False,B2_B3_M_and_31day_campaign_HOLD=True))

test_path=ROOT/'tests/test_v42_integration_sensitivity_policy.py'
spec=importlib.util.spec_from_file_location('queue_grid_evidence_fixture',test_path)
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
grid,envelope,*_=fixture.fixture()
anonymous=np.ones((96,2));zero=np.zeros(24)
zero_authority=dict(model_id='NAMED_SYNTHETIC_ZERO_QUEUE_GRID_FIXTURE',prediction_sha='a'*64,
    kernel_sha='b'*64,q90_hourly_GPUh=zero.tolist(),kernel=[1.],evidence_kind='FIXTURE')
zero_queue=fluid_queue(zero,[1.],grid.capacities,known_gpu=grid.known_gpu,source_authority=zero_authority)
risk=evaluate_q90_risk(grid,zero_queue,frozen_anonymous_gpu=anonymous)
stay=grid.evaluate(np.zeros((96,2)))
placement=np.zeros((96,2));placement[0]=[-1,1]
preplace=grid.evaluate(placement)
delay=np.zeros((96,2));delay[0,0]=-1;delay[1,0]=1
rebound=grid.evaluate(delay)
common_risk={key:risk[key] for key in ('carryout_GPUh','queue_GPUh_hours','peak_score','violation_count')}
ranked=rank_action_scores([dict(action=name,site='B' if name=='PREPLACE' else 'A',
    physical_feasible=True,q50_hard_feasible=score['hard_feasible'],q50_peak_score=score['peak_score'],
    q90_risk=common_risk,intentional_burden_seconds=900 if name=='DELAY' else 0,migration_count=0)
    for name,score in [('STAY',stay),('PREPLACE',preplace),('DELAY',rebound)]])
assert ranked['selected']['action']=='PREPLACE' and not rebound['hard_feasible']
write('Q90_RISK_REBOUND_RANK_FIXTURE.json',dict(base,evidence_kind='NAMED_SYNTHETIC_SIGNED_ORIGINAL_GRID_FIXTURE_ONLY',
    real_May_optimized_effect='NOT_ESTABLISHED',fixture_source=record(test_path),
    fixture_Q50_STAY=stay,fixture_Q50_PREPLACE=preplace,fixture_Q50_DELAY_rebound=rebound,
    Q90_admitted_only_original_grid_risk=risk,ranking=ranked,
    focused_test_run=dict(command='python -m pytest tests/test_v42_experimental_queue.py -q -p no:cacheprovider',
        passed=29,wall_seconds=.70,Native_Optimize_calls=0,AC_calls=0),
    native0_audit_wall_seconds=perf_counter()-started))
print(json.dumps(dict(real_known=summary(real),zero_known=summary(empty_known),
    fixture_rebound_peak=rebound['peak_score'],fixture_selected=ranked['selected']['action'],
    Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_runs=0),allow_nan=False))
