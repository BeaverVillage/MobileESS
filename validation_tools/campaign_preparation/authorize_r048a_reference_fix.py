"""Seal the reference adapter fix after the monthly worker naturally drains."""
import sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r048a as fix
from v44.common import read,record,verify,atomic,now

op=fix.op
for _ in range(120):
    state=read(op.STATE)
    if not op.alive(state['lease']) and not state['workers']:break
    time.sleep(1)
else:raise RuntimeError('R048A_NATURAL_DRAIN_NOT_FINISHED')
assert not fix.AUTH.exists()
repairs=[];failures=[];unstarted=[]
for job in state['jobs']:
    if job['day']=='2025-05-23' or job['status']=='BASELINE_QUEUED':continue
    old=Path(job['case_root'])
    if job['status']=='INFRASTRUCTURE_BLOCKED' and not old.exists():
        unstarted.append(job['day']);failures.append(record(op.HOME/'ERROR.json'));continue
    result=read(old/'RESULT.json')
    assert not (old/'ACTUAL').exists() and result['PASS'] is False
    assert 'RecursionError' in result.get('error','') or 'R048_REAL_PARENT' in result.get('error','')
    assert not op.alive(read(old/'START.json'))
    new=old.parent/'attempt002';assert not new.exists()
    failures.append(record(old/'RESULT.json'));repairs.append(dict(day=job['day'],old_case_root=str(old),new_case_root=str(new)))
from v44_week3 import preparation as prep
from v43_arms import reference
from v44.inputs import NATIVE_ROOT
audit=op.HOME/'R048A_NATIVE0_REFERENCE';audit.mkdir(exist_ok=True)
with prep.bindings(),prep.no_execution(),patch.object(reference,'project',op.project),patch('v44.execution.assert_current',return_value={'request':{'case_root':str(audit)}}):
    for p in repairs:
        native=read(NATIVE_ROOT/p['day']/'NATIVE_INPUT.json')
        result=op.project(native)
        assert result[2].shape==(96,12)
        assert fix.reference_helper._original_project is not op.project
val=op.HOME/'R048A_VALIDATION.json'
atomic(val,dict(PASS=True,UTC=now(),Native_calls=0,regressions=70,regression=record('D:/v44_r048a_regression_20261020.xml'),
    real_original_reference_projection_under_runtime_monkeypatch=True,dates=[p['day'] for p in repairs],
    immutable_original_capture=True,r046_Actual_preserved=True))
atomic(fix.AUTH,dict(UTC=now(),source=record(fix.__file__),previous_authorization=record(op.AUTH),validation=record(val),
    failed_results=failures,repairs=repairs,unstarted_admission_failures=unstarted,algorithm_changed=False,Native_calls=0,
    diagnosis='Lazy import first captured the already patched reference.project as its own original. Eagerly import the unchanged r045 reference helper before installing the adapter in every worker.'))
print(dict(PASS=True,repairs=repairs,old_month_owner_dead=True),flush=True)
