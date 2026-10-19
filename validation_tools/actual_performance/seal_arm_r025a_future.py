from pathlib import Path
import sys,os,subprocess,psutil,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025a
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r025.operations import validate as prior_validate
from v44_recovery_r025a import operations as ops
from v44_recovery_r025a.handover import REASON

prior_validate()
tree=ET.parse('D:/MobileESS_V44/development/r025a/regressions.xml').getroot()
assert len(tree.findall('.//testcase'))>=277 and not tree.findall('.//failure') and not tree.findall('.//error')
verify(read(ops.OPS/'R025_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
h=read(ops.OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r025' and h.get('pending_revision') is None
assert not (ops.OPS/'STOP_AUTONOMY.json').exists()
case=ops.CAMPAIGN/'2025-05-02/B3/attempt008';worker=read(case/'START.json');coordinator=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json')
atomic(ops.OPS/'R025A_USER_AUTHORIZATION.json',dict(UTC=now(),original_authorization=record(ops.OPS/'R025_USER_AUTHORIZATION.json'),
    instruction='User confirmed all B1/B3 A stages and asked to prevent incompatible validation gates; current r025 worker continues uninterrupted; future UB-only A1 physical cache ownership admitted only after original integer/physical proof verification.'))
guard=dict(UTC=now(),protected_case_root=str(case),protected_worker=worker,protected_coordinator=coordinator,
    authorization=record(ops.OPS/'R025A_USER_AUTHORIZATION.json'),completed_A1_M1_preserved=True,
    previous_permit=record(ops.OPS/'RECOVERY_R025_EXECUTION_PERMIT.json'),
    current_worker_must_finish_without_interruption=True,no_PASS_gate=True)
atomic(ops.OPS/'R025A_HANDOVER_GUARD.json',guard)
validation=dict(UTC=now(),PASS=True,revision='v44_recovery_r025a',regressions=len(tree.findall('.//testcase')),
    regression_receipt=record('D:/MobileESS_V44/development/r025a/regressions.xml'),
    original_validation=record(ops.OPS/'R025_CHANGE_AND_VALIDATION.json'),
    authorization=record(ops.OPS/'R025A_USER_AUTHORIZATION.json'),Native_validation_calls=0,
    repair='SAME_DATE_UB_ONLY_A1_CACHE_OWNER_ALLOWED_AFTER_ORIGINAL_INTEGER_PHYSICAL_REPLAY_PROOF',
    physical_domain_hash_source_date_ownership_and_input_checks_retained=True,
    current_r025_UB_parent_compatibility=True,current_worker_interrupted=False,
    applies_all_unstarted_B1_B3_A_stages_without_PASS_gate=True,
    total_Native_seconds=3600,Phase_I_Native_seconds=400,UB_only_null_LB_gap_preserved=True,sources=ops.sources())
atomic(ops.OPS/'R025A_CHANGE_AND_VALIDATION.json',validation)
ops.make_permit()
out=ops.OPS/'source_snapshots/r025a';out.mkdir(exist_ok=False)
for p in Path('v44_recovery_r025a').glob('*.py'):(out/p.name).write_bytes(p.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT)))
atomic(ops.OPS/'R025A_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT)))
ops.validate()
atomic(ops.OPS/'STOP_AUTONOMY.json',dict(UTC=now(),reason=REASON,user_stop=False,
    current_worker_continue=True,scope='STOP_OLD_COORDINATOR_AFTER_CURRENT_ENTIRE_CASE_FOR_VALIDATED_FUTURE_REVISION'))
h.update(UTC=now(),pending_revision='v44_recovery_r025a',pending_permit=record(ops.PERMIT),
    pending_validation=record(ops.OPS/'R025A_CHANGE_AND_VALIDATION.json'),pending_regressions=validation['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R025A',
    latest_user_instruction='All B1/B3 A1/A2 Native3600 Phase400 and verified UB freeze; current r025 worker continues; r025a also admits fully validated UB-only A1 cache owners for future B3 A2.',
    performance_revision_state='R025_ACTIVE_CURRENT_R025A_SEALED_UNCONDITIONAL_FUTURE_CASE_BOUNDARY',
    future_deployment_requires_current_PASS=False)
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
for name in ('collect_watchdog','audit_active_revision'):
    old=ops.OPS/(name+'_r025.py');new=ops.OPS/(name+'_r025a.py')
    text=old.read_text(encoding='utf-8-sig').replace('r025','r025a').replace('R025','R025A')
    # During pending handover the collector also accepts the current r025.
    text=text.replace("'v44_recovery_r025a'):","'v44_recovery_r025','v44_recovery_r025a'):")
    new.write_text(text,encoding='utf-8')
with (ops.OPS/'r025a_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r025a.operations','--handover'],
        cwd=Path(__file__).resolve().parents[2],stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(ops.OPS/'R025A_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(ops.PERMIT),protected_worker_interrupted=False))
print(dict(PASS=True,regressions=validation['regressions'],pending_revision='v44_recovery_r025a',current_worker_unchanged=worker['pid']))
