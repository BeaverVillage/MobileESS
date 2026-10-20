"""Prepare an independent r017; never edit the running or sealed sources."""
from pathlib import Path
import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,atomic,now,verify
from v44_recovery_r016.operations import OPS,validate

validate()
handoff=read(OPS/'CURRENT_HANDOFF.json')
assert handoff['active_revision']=='v44_recovery_r015' and handoff['pending_revision']=='v44_recovery_r016'
assert not (OPS/'R016_HANDOVER_APPLIED.json').exists(),'R016_ALREADY_DISPATCHED_RECHECK_BOUNDARY'
stop=read(OPS/'STOP_AUTONOMY.json')
assert stop['reason']=='R016_PERFORMANCE_VALIDATION_SAFE_HANDOVER_AFTER_HEALTHY_WORKER'
assert not stop.get('user_stop')
authorization=dict(UTC=now(),user_instruction='응 반영해서 r017로 B3끝나면 r017로 돌아가게 해.',
    improved_arms=['B0','B1','B3'],protected_case='2025-05-01/B3/attempt003',
    current_worker_interrupt_allowed=False,replace_pending_r016=True)
atomic(OPS/'R017_USER_AUTHORIZATION.json',authorization)
atomic(OPS/'R017_PREPARATION_PREVIOUS_HANDOFF.json',handoff)
atomic(OPS/'R017_PREPARATION_PREVIOUS_STOP.json',stop)
stop.update(UTC=now(),reason='R017_STRUCTURAL_PERFORMANCE_SAFE_HANDOVER_AFTER_HEALTHY_WORKER',
    authorization=record(OPS/'R017_USER_AUTHORIZATION.json'),
    policy='KEEP_CURRENT_R015_B3_ENTIRE_ACTUAL_AND_FRESH_THEN_R017_B0_B1_B3')
atomic(OPS/'STOP_AUTONOMY.json',stop)
guard=read(OPS/'R016_HANDOVER_GUARD.json')
guard.update(UTC=now(),authorization=record(OPS/'R017_USER_AUTHORIZATION.json'),
    superseded_pending_permit=record(OPS/'RECOVERY_R016_EXECUTION_PERMIT.json'))
atomic(OPS/'R017_HANDOVER_GUARD.json',guard)
target=Path('v44_recovery_r017');target.mkdir(exist_ok=False)
for source in Path('v44_recovery_r016').glob('*.py'):
    (target/source.name).write_text(source.read_text(encoding='utf8').replace('r016','r017').replace('R016','R017'),encoding='utf8',newline='\n')
for name in ('history.py','immutable.py'):
    (target/name).write_bytes((Path('v44_actual_prefix')/name).read_bytes())
for source in Path('tests').glob('test_v44_recovery_r016_*.py'):
    destination=source.with_name(source.name.replace('r016','r017'))
    assert not destination.exists()
    destination.write_text(source.read_text(encoding='utf8').replace('r016','r017').replace('R016','R017'),encoding='utf8',newline='\n')
source=Path('tests/test_v44_actual_prefix.py')
Path('tests/test_v44_recovery_r017_history.py').write_text(source.read_text(encoding='utf8').replace('v44_actual_prefix','v44_recovery_r017'),encoding='utf8',newline='\n')
print(dict(prepared=str(target),protected_case=guard['protected_case_root'],old_r016_waiter_will_exit_naturally=True))
