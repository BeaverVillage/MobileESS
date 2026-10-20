"""Separate immutable checkpoint recovery revision; preserve sealed r017."""
from pathlib import Path
import sys
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,atomic,now
from v44_recovery_r017.operations import OPS,validate
validate()
target=Path('v44_recovery_r018');target.mkdir(exist_ok=False)
for source in Path('v44_recovery_r017').glob('*.py'):
    (target/source.name).write_text(source.read_text(encoding='utf8').replace('r017','r018').replace('R017','R018'),encoding='utf8',newline='\n')
for source in Path('tests').glob('test_v44_recovery_r017_*.py'):
    (source.with_name(source.name.replace('r017','r018'))).write_text(source.read_text(encoding='utf8').replace('r017','r018').replace('R017','R018'),encoding='utf8',newline='\n')
stop=read(OPS/'STOP_AUTONOMY.json');assert stop['reason']=='MAY02_B3_CHECKPOINT_RECOVERY_PREPARATION'
worker=stop['protected_workers'][0]
request=read(worker['cmdline'][-1])
guard=dict(UTC=now(),authorization=record(OPS/'MAY02_B3_CHECKPOINT_RESUME_USER_AUTHORIZATION.json'),
    protected_case_root=request['case_root'],protected_worker=dict(pid=worker['pid'],process_created=worker['create_time']),
    protected_coordinator=stop['protected_coordinator'],protected_request=record(worker['cmdline'][-1]),
    previous_permit=record(OPS/'RECOVERY_R017_EXECUTION_PERMIT.json'),improved_arms=['B0','B1','B3'],
    boundary='TERMINAL_CASE_RESULT_AND_NATURAL_WORKER_AND_COORDINATOR_EXIT',
    current_case_interrupt_allowed=False,current_case_restart_allowed=False)
atomic(OPS/'R018_HANDOVER_GUARD.json',guard)
print('R018_PREPARED')
