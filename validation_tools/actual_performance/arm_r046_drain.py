import v44_recovery_r045
from v44_recovery_r045 import operations as op
from v44.common import read,record,atomic,now
from v44.locks import alive
import json

state=read(op.STATE)
if op.seq.STOP.exists():raise PermissionError('EXISTING_USER_STOP_PRESERVED')
if state['phase']!='MAIN_ACTUAL_PARALLEL' or not alive(state['lease']):raise PermissionError('LIVE_CURRENT_ACTUAL_WAVE_REQUIRED')
auth=op.OPS/'R046_USER_ACTUAL_DRAIN_REQUEST.json'
atomic(auth,dict(UTC=now(),explicit_user_approved=True,
    user_instruction='2026-10-20 user: 오류 해결, 현재 Actual 끝나면 Planning 재개, Planning 끝나면 Actual 7worker 자동 실행, 계속 진행.',
    current_lease=state['lease'],current_actual=[dict(day=j['day'],arm=j['arm'],case_root=j['case_root']) for j in state['jobs'] if j['status']=='ACTUAL_RUNNING'],
    active_workers_interrupted=False,do_not_launch_remaining_prepared_until_repair_Planning_done=True))
atomic(op.seq.STOP,dict(UTC=now(),reason='R046_DRAIN_CURRENT_ACTUAL_THEN_REPAIR_PLANNING',
    operational_transition=True,user_stop=False,active_workers_interrupted=False,authorization=record(auth)))
print(json.dumps(dict(PASS=True,draining_current_actual=sum(j['status']=='ACTUAL_RUNNING' for j in state['jobs']),pending_actual_preserved=sum(j['status']=='PREPARED' for j in state['jobs']))))
