import v44_recovery_r046
from v44_recovery_r046 import operations as op
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from pathlib import Path
from collections import Counter
import json

with op.bindings():
    auth=op.authority();state=read(op.STATE);transition=read(op.OPS/'R046_TRANSITION_HEARTBEAT.json')
    assert alive(transition) and alive(state['lease'])
    stop=read(op.core.seq.STOP)
    assert stop['reason']==op.REASON and stop['authorization']==record(op.DRAIN) and stop['operational_transition']
    for p in auth['plan']:
        r=read(p['original_request']);r.update(case_root=p['case_root'],R046_authorization=record(op.AUTH),
            sequence_authorization=record(op.core.seq.AUTH),sequence_mode='MAIN' if op.core.seq.key(p) in op.core.seq.MAIN else 'BASELINE_FULL')
        op.request_authority(r)
    try:op.adopt({'preflight':True})
    except PermissionError as error:assert 'OLD_OWNER_OR_USER_STOP' in str(error)
    else:raise AssertionError('Planning must not adopt while Actual owner is alive')
    pending=[j for j in state['jobs'] if j['status']=='PREPARED']
    for j in pending:
        verify([j['handoff']]);h=read(j['handoff']['path']);r=read(j['prepare_request'])
        assert h['source_sha']==r['source_sha'] and h['sources']==r['sources'] and not (Path(j['case_root'])/'ACTUAL').exists()
    value=dict(PASS=True,UTC=now(),authorization=record(op.AUTH),transition_alive=True,
        current_Actual_worker_PIDs_preserved=transition['active_workers'],current_counts=dict(Counter(j['status'] for j in state['jobs'])),
        all_28_future_request_authorities_validated=True,Planning_cannot_start_while_current_Actual_owner_alive=True,
        pending_prepared_handoffs_unchanged=len(pending),repair_Planning_cases=[list(k) for k in op.REPAIRS],
        expected_next_Actual_wave=len(pending)+len(op.REPAIRS),actual_workers=7,baseline_followup_workers=1,
        actual_repair_execution_pending_current_Actual_completion=True)
    atomic(op.OPS/'R046_ARMED_SEQUENCE_VERIFIED.json',value);print(json.dumps(value,indent=2))
