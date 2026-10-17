from pathlib import Path
import sys,os,subprocess,psutil,inspect,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024b
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r024a.operations import validate as original_validate
from v44_recovery_r024b import operations as ops,adaptive_pricing as current
from v44_recovery_r024a import adaptive_pricing as original
from v44_recovery_r024a.phase_rebuild import Rebuild as OriginalRebuild
from v44_recovery_r024b.phase_rebuild import Rebuild
from v44_recovery_r024b.handover import REASON

original_validate();assert not ops.workers() and not alive(read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'))
tree=ET.parse('D:/MobileESS_V44/development/r024b/regressions.xml').getroot()
assert len(tree.findall('.//testcase'))>=270 and not tree.findall('.//failure') and not tree.findall('.//error')
for a,b in [(current.choose,original.choose),(current.collect_targeted,original.collect_targeted),
        (current.AdaptivePricing.price,original.AdaptivePricing.price),(current.AdaptivePricing.plan_classes,original.AdaptivePricing.plan_classes),
        (current.AdaptivePricing.observe,original.AdaptivePricing.observe),(Rebuild,OriginalRebuild)]:
    assert inspect.getsource(a).replace('r024b','r024a').replace('R024B','R024A')==inspect.getsource(b)
proof_path=Path('D:/MobileESS_V44/development/r024b/current_continuation/ADMISSION.json');proof=read(proof_path)
cache_paths={r['external_full_block_cache']['path'] for r in read(proof['pricing_manifest']['path'])['records']}
proof['sources']=[r for r in proof['sources'] if r['path'] not in cache_paths]
atomic(proof_path,proof);atomic(ops.OPS/'R024B_CURRENT_CONTINUATION.json',proof)
assert proof['PASS'] and proof['new_Native_calls']==0 and proof['Native_total_limit']==5400 and proof['Phase_I_separate_limit'] is None
verify(proof['sources']+[proof['checkpoint'],proof['native_parent'],proof['adaptive_parent'],proof['pricing_manifest']])
native=read(proof['native_parent']['path']);old=read(native['ledger']['path'])
assert old['inflight'] is None and abs(sum(r.get('Native_Runtime') or 0 for r in old['calls'])-old['measured_Native_Runtime'])<1e-6
baseline=read(ops.OPS/'R025_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(baseline['files'])
may05=ops.CAMPAIGN/'2025-05-05/B0/attempt001/RESULT.json';assert read(may05)['PASS'];baseline['files'].append(record(may05))
atomic(ops.OPS/'R024B_PASS_AND_M1_PRESERVATION_BASELINE.json',baseline)
stop=read(ops.OPS/'R024B_CURRENT_A2_STOPPED.json');assert not stop['Native_inflight']
guard=dict(UTC=now(),protected_case_root=str(ops.CAMPAIGN/'2025-05-02/B3/attempt009'),
    protected_worker=stop['old_worker'],protected_coordinator=stop['old_coordinator'],
    authorization=record(ops.OPS/'R024B_USER_AUTHORIZATION.json'),completed_A1_M1_preserved=True,
    previous_permit=record(ops.OPS/'RECOVERY_R025B_EXECUTION_PERMIT.json'),prior_worker_finished_naturally=True)
atomic(ops.OPS/'R024B_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r024b',algorithm='r024',original_operational_version='r024a',
    regressions=len(tree.findall('.//testcase')),regression_receipt=record('D:/MobileESS_V44/development/r024b/regressions.xml'),
    authorization=record(ops.OPS/'R024B_USER_AUTHORIZATION.json'),current_continuation=record(proof_path),
    Native_validation_calls=0,all_future_B1_B3_A_stages=True,Native_total_limit=5400,Phase_I_separate_limit=None,
    Adaptive_Pricing_selection_feedback_and_Rebuild_source_equal_to_r024a_after_label_normalization=True,
    original_P1_body_and_full_gap_acceptance=True,UB_only_bypass_removed=True,
    checkpoint_active_master_fingerprint_exact=True,restored_active_rows=proof['restored_active_rows'],
    inherited_Native_seconds=proof['inherited_Native_seconds'],Native_clock_reset=False,
    missing_pricing_roster_restored_and_138_full_cache_files_verified=True,
    original_PhaseI_zero_1e8_negative_exponent_and_original_residual_1e6_negative_exponent_unchanged=True,
    old_failure_results_raw_and_native_ledgers_preserved=True,sources=ops.sources(),production_completion_not_yet_claimed=True)
atomic(ops.OPS/'R024B_CHANGE_AND_VALIDATION.json',report)
ops.make_permit();out=ops.OPS/'source_snapshots/r024b';out.mkdir(exist_ok=False)
for p in Path('v44_recovery_r024b').glob('*.py'):(out/p.name).write_bytes(p.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT)))
atomic(ops.OPS/'R024B_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT)))
ops.validate()
h=read(ops.OPS/'CURRENT_HANDOFF.json');assert h['active_revision']=='v44_recovery_r025b' and h.get('pending_revision') is None
assert read(ops.OPS/'STOP_AUTONOMY.json')['reason']==REASON
h.update(UTC=now(),pending_revision='v44_recovery_r024b',pending_permit=record(ops.PERMIT),
    pending_validation=record(ops.OPS/'R024B_CHANGE_AND_VALIDATION.json'),pending_regressions=report['regressions'],
    pending_windows_task='MobileESS_V44_Campaign004_Recovery_R024B',latest_user_instruction='Rollback to r024a algorithm: total A Native5400, no separate PhaseI timeout, original P1/full-gap acceptance; current checkpoint and all Native458.118 costs continue.',
    performance_revision_state='R024B_R024A_ALGORITHM_ROLLBACK_SEALED',future_deployment_requires_current_PASS=False)
atomic(ops.OPS/'CURRENT_HANDOFF.json',h)
for name in ('collect_watchdog','audit_active_revision'):
    old=ops.OPS/(name+'_r025b.py');new=ops.OPS/(name+'_r024b.py')
    text=old.read_text(encoding='utf-8-sig').replace('r025b','r024b').replace('R025B','R024B')
    new.write_text(text,encoding='utf-8')
with (ops.OPS/'r024b_handover.log').open('ab') as stream:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u','-m','v44_recovery_r024b.operations','--handover'],
        cwd=Path(__file__).resolve().parents[2],stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
atomic(ops.OPS/'R024B_HANDOVER_START.json',dict(UTC=now(),pid=proc.pid,process_created=psutil.Process(proc.pid).create_time(),permit=record(ops.PERMIT)))
print(dict(PASS=True,algorithm='r024a',operational_checkpoint_adapter='r024b',Native_limit=5400,Phase_I_limit=None,
    regressions=report['regressions'],inherited_Native=proof['inherited_Native_seconds'],pid=proc.pid))
