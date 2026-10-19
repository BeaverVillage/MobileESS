from pathlib import Path
import sys,os,subprocess,psutil,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025b
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r025a.operations import validate as prior_validate
from v44_recovery_r025b import operations as ops
from v44_recovery_r025b.handover import REASON
prior_validate()
assert not ops.workers() and not alive(read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'))
tree=ET.parse('D:/MobileESS_V44/development/r025b/regressions.xml').getroot()
assert len(tree.findall('.//testcase'))>=281 and not tree.findall('.//failure') and not tree.findall('.//error')
verify(read(ops.OPS/'R025_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
case=ops.CAMPAIGN/'2025-05-02/B3/attempt008';stage=read(case/'A2/RESULT.json')
assert not stage['PASS'] and stage['native_status']==3 and stage['classification']=='NO_VALID_INCUMBENT'
proof=read(ops.OPS/'R025B_CURRENT_CONTINUATION.json');assert proof['PASS'] and proof['saved_active_master_fingerprint_exact']
verify(proof['sources']+[proof['checkpoint'],proof['native_parent'],proof['adaptive_parent']])
h=read(ops.OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r025a' and h.get('pending_revision') is None
assert read(ops.OPS/'STOP_AUTONOMY.json')['reason']==REASON
atomic(ops.OPS/'R025B_USER_AUTHORIZATION.json',dict(UTC=now(),original_authorization=record(ops.OPS/'R025_USER_AUTHORIZATION.json'),
    instruction='Latest user explicitly increased Phase I Native limit400 to1000, retained total3600, requested May02 B3 A2 checkpoint resume and fixing UB failure/error classification. Preserve all prior Native costs and original constraints, restore active rows/candidates/prior/coverage. Apply all B1/B3 A stages.'))
guard=dict(UTC=now(),protected_case_root=str(case),protected_worker=read(case/'START.json'),
    protected_coordinator=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'),authorization=record(ops.OPS/'R025B_USER_AUTHORIZATION.json'),
    completed_A1_M1_preserved=True,previous_permit=record(ops.OPS/'RECOVERY_R025A_EXECUTION_PERMIT.json'),
    prior_worker_finished_naturally=True,Native_clock_reset=False)
atomic(ops.OPS/'R025B_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r025b',regressions=len(tree.findall('.//testcase')),
    regression_receipt=record('D:/MobileESS_V44/development/r025b/regressions.xml'),
    authorization=record(ops.OPS/'R025B_USER_AUTHORIZATION.json'),current_continuation=record(ops.OPS/'R025B_CURRENT_CONTINUATION.json'),
    Native_validation_calls=0,all_unstarted_B1_B3_A1_A2=True,total_Native_limit=3600,Phase_I_Native_limit=1000,
    restored_active_master_fingerprint_exact=True,restored_active_rows=proof['restored_active_rows'],
    prior_primal_and_frozen_weights_and_adaptive_feedback_preserved=True,
    inherited_Native=proof['inherited_Native_seconds'],inherited_Phase_I_Native=proof['inherited_Phase_I_Native_seconds'],
    phase_counter_excludes_old_integer_attempt=True,Native_clock_reset=False,
    UB_failure_classification='CURRENT_SUPPORT_INFEASIBLE_OR_NO_VALID_UB_NOT_FULL_DOMAIN_INFEASIBLE_NOT_LEGACY_GAP_ERROR',
    wrapped_budget_stop_incumbent_preserved=True,UB_only_A1_cache_and_A2_M2_gate_compatible=True,
    physical_domains_equations_bounds_and_integer_replay_unchanged=True,
    no_valid_UB_does_not_create_false_PASS=True,sources=ops.sources(),production_completion_not_yet_claimed=True)
atomic(ops.OPS/'R025B_CHANGE_AND_VALIDATION.json',report)
ops.make_permit();out=ops.OPS/'source_snapshots/r025b';out.mkdir(exist_ok=False)
for p in Path('v44_recovery_r025b').glob('*.py'):(out/p.name).write_bytes(p.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT)))
atomic(ops.OPS/'R025B_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT)))
ops.validate()
h.update(UTC=now(),pending_revision='v44_recovery_r025b',pending_permit=record(ops.PERMIT),
    pending_validation=record(ops.OPS/'R025B_CHANGE_AND_VALIDATION.json'),pending_regressions=report['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R025B',
    latest_user_instruction='All B1/B3 A1/A2 Native3600 Phase I cumulative1000; May02 B3 attempt009 active-row/support/prior/coverage checkpoint and Native414.457 resume, zero clock reset.',
    performance_revision_state='R025B_SEALED_PHASE1000_CHECKPOINT_READY',future_deployment_requires_current_PASS=False)
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
for name in ('collect_watchdog','audit_active_revision'):
    old=ops.OPS/(name+'_r025a.py');new=ops.OPS/(name+'_r025b.py')
    text=old.read_text(encoding='utf-8-sig').replace('r025a','r025b').replace('R025A','R025B')
    new.write_text(text,encoding='utf-8')
with (ops.OPS/'r025b_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r025b.operations','--handover'],
        cwd=Path(__file__).resolve().parents[2],stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(ops.OPS/'R025B_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(ops.PERMIT)))
print(dict(PASS=True,regressions=report['regressions'],inherited_Native=proof['inherited_Native_seconds'],
    inherited_Phase_I_Native=proof['inherited_Phase_I_Native_seconds'],new_phase_limit=1000,pid=proc.pid))
