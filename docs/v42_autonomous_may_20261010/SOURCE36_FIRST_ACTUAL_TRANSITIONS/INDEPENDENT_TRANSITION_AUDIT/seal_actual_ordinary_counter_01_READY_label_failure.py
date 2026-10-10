from pathlib import Path
from datetime import datetime, timezone
import json, hashlib
O=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_bytes())
def record(p):
    p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
ordinary=O/'events/SOURCE36_BIRTH_fresh_b2_v36_01_82f2e213'
second=O/'events/SOURCE36_BIRTH_repair_b2_v36_01_s1_c0ce5d01'
event=read(ordinary/'EVENT_RECEIPT.json');cp=read(ordinary/'CHECKPOINT_RAW.json')
oldcp=read(second/'CHECKPOINT_RAW.json');q=read(ordinary/'QUEUE_RAW.json')
rows=[r for r in q['entries'] if r.get('repair_source_SHA')==event['original_manifest99_source']]
may3=[r for r in rows if r['arm']=='B2' and r['date']=='2025-05-03']
assert len(may3)==1
row=may3[0]
assert oldcp['first_sweep_retry_streak']['B2']==2 and cp['first_sweep_retry_streak']['B2']==0
assert row['verification_status']=='READY' and row['retry_priority']==1000 and row.get('new_worker_PID') is None
assert set(cp['workers'])=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-10'}
w=cp['workers']['B2/2025-05-10']
assert w['PID']==61988 and w['created']==event['process']['created'] and not w.get('recovery_queue_id')
assert event['first_sweep_ordinary_request'] is True and event['Native0_observed'] is True
assert event['previous_attempts_field_present'] is False and event['cold_manifest_day_has_no_prior_attempt'] is True
assert cp['dates']['B2/2025-05-03']['status']=='RETRY_PENDING'
ready=[r for r in rows if r['verification_status']=='READY']
assert max(r['retry_priority'] for r in ready)==1000
refs={name:record(p) for name,p in dict(second_retry_birth=second/'EVENT_RECEIPT.json',
    ordinary_birth=ordinary/'EVENT_RECEIPT.json',second_retry_checkpoint=second/'CHECKPOINT_RAW.json',
    ordinary_checkpoint=ordinary/'CHECKPOINT_RAW.json',queue=ordinary/'QUEUE_RAW.json',
    original_observer_failure=O/'events/READONLY_OBSERVATION_ERROR_error_1236ba19/OBSERVATION_ERROR_RECEIPT.json',
    canonical_supervisor=Path('D:/MobileESS_v42_autonomous/v42_autonomous/supervisor.py'),
    original_budget=Path('D:/v42run36/v42_b2_seed_recovery_v19/budget.py'),
    original_worker=Path('D:/v42run36/v42_autonomous_b2/worker.py'),current_external_observer=O/'observe_events.py').items()}
d=dict(schema='V42_ACTUAL_FIRST_SWEEP_TWO_RETRIES_THEN_ORDINARY_AND_PENDING_PRIORITY',
    UTC=datetime.now(timezone.utc).isoformat(),observed_dispatch_identity_and_counter_verified=True,
    counter_before_second_retry_observation=2,counter_after_ordinary_observation=0,
    actual_ordinary_worker=dict(day='2025-05-10',attempt_id='fresh_b2_v36_01',PID=61988,
        created=w['created'],request=event['current_request'],Native0_observed=True,
        remaining_Native_at_observation=5400,previous_attempts_field_present=False,
        cold_manifest_day_has_no_prior_attempt=True),
    current_worker_dates=['2025-05-01','2025-05-02','2025-05-10'],
    May03_actual_retry_queue_row=row,May03_checkpoint_current_record={k:v for k,v in cp['dates']['B2/2025-05-03'].items() if k!='attempt_history'},
    May03_retry_is_pending_not_activated=True,May03_priority_is_current_maximum_READY_priority=True,
    next_dispatch_or_next_free_slot_outcome_not_yet_observed=True,
    canonical_source_lines=dict(supervisor='147-156 ordinary request fields; 33-42 counters; 553-580 ordinary selection/dispatch',
        original_budget='16-23 prior derived from sealed manifest, absent prior means fresh0',worker='219-243 exact sealed request/source guards'),
    external_harness_correction='Original KeyError(previous_attempts) retained; only external observer distinguishes canonical ordinary omission from sealed repair previous_attempts=[].',
    raw_refs=refs,Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
    production_source_runtime_queue_lease_process_Git_changes=0,
    scientific_final_PASS_or_Source36_performance_claimed=False,
    limitations=['Checkpoint snapshots establish the two actual retries followed by ordinary dispatch and durable counter reset; no process memory bytecode inspection.',
        'May03 READY1000 remains pending. Its later dispatch or future outcome is not promised.'])
out=ordinary/'ACTUAL_TWO_RETRY_THEN_ORDINARY_AND_MAY03_PENDING_RECEIPT.json'
assert not out.exists();out.write_text(json.dumps(d,indent=2)+'\n',encoding='utf8')
print(json.dumps(record(out)))
