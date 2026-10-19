"""Hold new dispatch after the current healthy worker while diagnosing A2."""
import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,atomic,now
from v44_recovery_r017.operations import OPS,CAMPAIGN,workers
path=OPS/'STOP_AUTONOMY.json'
assert not path.exists(),'EXISTING_STOP_REQUIRES_REVIEW'
atomic(OPS/'MAY02_B3_CHECKPOINT_RESUME_USER_AUTHORIZATION.json',dict(UTC=now(),
    user_instruction='왜 5월 2일 B3 실패했어? 해결해서 체크포인트부터 재개해',
    target='2025-05-02/B3/attempt001',preserve_original_failure=True,checkpoint_resume=True))
atomic(OPS/'MAY02_B3_RECOVERY_PREVIOUS_HANDOFF.json',read(OPS/'CURRENT_HANDOFF.json'))
atomic(path,dict(UTC=now(),reason='MAY02_B3_CHECKPOINT_RECOVERY_PREPARATION',user_stop=False,
    authorization=record(OPS/'MAY02_B3_CHECKPOINT_RESUME_USER_AUTHORIZATION.json'),
    policy='FINISH_CURRENT_HEALTHY_WORKER_THEN_PRIORITY_MAY02_B3_VALIDATED_CHECKPOINT_RESUME',
    protected_workers=workers(),protected_coordinator=read(CAMPAIGN/'COORDINATOR_LEASE.json')))
print('FUTURE_DISPATCH_HELD_CURRENT_WORKER_NOT_INTERRUPTED')
