from pathlib import Path
from v44.common import read,verify,record,digest
from v44.locks import alive
from v44_recovery_r015 import operations as performance

OPS=performance.OPS
PERMIT=OPS/'R015_USER_ACTUAL_RESTART_R001_PERMIT.json'
PARENT=performance.CAMPAIGN/'2025-05-01/B3/attempt002'
TARGET=performance.CAMPAIGN/'2025-05-01/B3/attempt003'

def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]

def validate():
    performance.validate();value=read(PERMIT)
    verify(value['sources']+[value['r015_permit'],value['authorization'],value['interruption']])
    if value['sources']!=sources() or value['policy_sha']!=digest(value['policy']):raise PermissionError('USER_ACTUAL_ENTRY_SOURCE_OR_POLICY_DRIFT')
    if value['policy']!=dict(day='2025-05-01',arm='B3',parent=str(PARENT),target=str(TARGET),restart='ACTUAL_120_THEN_INDEPENDENT_FRESH',A_M_optimization_calls=0,partial_context_reuse=False,performance_revision='v44_recovery_r015'):
        raise PermissionError('USER_ACTUAL_ENTRY_POLICY_NOT_EXACT')
    return value

def authorized_parent(parent):
    value=validate()
    if Path(parent).resolve()!=PARENT.resolve():raise PermissionError('ONLY_EXPLICIT_MAY01_B3_ATTEMPT002')
    auth=read(value['authorization']['path']);interruption=read(value['interruption']['path'])
    if auth['authorization']!='USER_20261017_STOP_CURRENT_AND_RESTART_MAY01_B3_ACTUAL_WITH_R015' or interruption!=auth:
        raise PermissionError('EXPLICIT_USER_RESTART_AUTHORIZATION_REQUIRED')
    if alive(read(PARENT/'START.json')):raise PermissionError('PARENT_WORKER_MUST_BE_DEAD')
    if auth['parent']!=str(PARENT) or not auth['no_native_optimizer_inflight'] or auth['A_M_reoptimization']:
        raise PermissionError('USER_INTERRUPTION_AXIS_OR_NATIVE_DRIFT')
    verify(auth['preserved']+[auth['completed_A2'],auth['completed_M2']])
    if read(PARENT/'RESULT.json').get('PASS'):raise PermissionError('ALREADY_COMPLETED_PASS_NO_REPLAY')
    return True

def validate_request(request):
    value=validate();authorized_parent(request['wall_resume_parent'])
    if (request['day'],request['arm'],Path(request['case_root']))!=('2025-05-01','B3',TARGET):raise PermissionError('ONLY_EXPLICIT_MAY01_B3_ATTEMPT003')
    if request['user_actual_restart_permit']!=record(PERMIT) or request['execution_permit']!=record(performance.PERMIT):raise PermissionError('R015_AND_USER_OPERATIONAL_PERMITS_REQUIRED')
    if request['source_sha']!=digest(request['sources']):raise PermissionError('REQUEST_SOURCE_DIGEST_DRIFT')
    verify(request['sources']);return value
