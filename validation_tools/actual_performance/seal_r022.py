"""Seal adapter sources only after exact offline and inherited regressions."""
from pathlib import Path
import sys,inspect,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r022 import operations as ops
from v44_recovery_r021.operations import validate as validate21
from v44_recovery_r021.phase_rebuild import Rebuild as PriorRebuild
from v44_recovery_r022.phase_rebuild import Rebuild
validate21();assert not ops.workers() and not alive(read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'))
assert inspect.getsource(Rebuild).replace('r022','r021').replace('R022','R021')==inspect.getsource(PriorRebuild)
tests=Path('D:/MobileESS_V44/development/r022/regressions.xml');tree=ET.parse(tests).getroot()
assert len(tree.findall('.//testcase'))>=218 and not tree.findall('.//failure') and not tree.findall('.//error')
validation=Path('D:/MobileESS_V44/development/r022')
receipts=[validation/'parent_validation/R022_PARENT_COMPATIBILITY.json',validation/'class_validation/ROW_MAPPING_RESULT.json',validation/'real_validation_02/RESULT.json']
for path in receipts:assert read(path)['PASS']
verify(read(ops.OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
stopped=read(ops.OPS/'R022_CURRENT_A2_STOPPED.json');assert stopped['Native_inflight'] is False
guard=dict(UTC=now(),protected_case_root=str(ops.CAMPAIGN/'2025-05-02/B3/attempt004'),protected_worker={k:stopped['old_worker'][k] for k in ('pid','process_created')},
    protected_coordinator=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'),authorization=record(ops.OPS/'R022_USER_AUTHORIZATION.json'),
    completed_A1_M1_preserved=True,fresh_A2_Native_start=0.,previous_permit=record(ops.OPS/'RECOVERY_R021_EXECUTION_PERMIT.json'))
atomic(ops.OPS/'R022_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r022',regressions=len(tree.findall('.//testcase')),regression_receipt=record(tests),
    exact_validation=[record(p) for p in receipts],authorization=record(ops.OPS/'R022_USER_AUTHORIZATION.json'),
    previous_A2_interruption=record(ops.OPS/'R022_CURRENT_A2_STOPPED.json'),
    all_PASS_and_M1_bytes_preserved=record(ops.OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json'),
    full_row_promotion_removed=True,semantic_active_row_mapping=True,all_new_local_hard_rows_retained=True,
    full_Phi_not_restricted_Phi_certifies_zero=True,original_zero_and_primal_dual_inclusion_proofs_preserved=True,
    adaptive_batch=True,scaling_revision=False,tolerances_or_domains_relaxed=False,
    original_rebuild_implementation_identical=True,separate_source_worktree=str(Path(__file__).resolve().parents[2]),
    fresh_case=dict(day='2025-05-02',arm='B3',attempt='attempt005',start='A2',Native_start=0.,Native_total=5400.,completed_M1_reused=True),
    end_to_end_speedup_not_yet_measured=True,sources=ops.sources())
p=ops.OPS/'R022_CHANGE_AND_VALIDATION.json';assert not p.exists();atomic(p,report)
ops.make_permit();out=ops.OPS/'source_snapshots/r022';out.mkdir(exist_ok=False)
for source in Path('v44_recovery_r022').glob('*.py'):(out/source.name).write_bytes(source.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(p)))
atomic(ops.OPS/'R022_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT),validation=record(p)))
ops.validate();print(dict(PASS=True,regressions=report['regressions'],new_A2_Native_start=0.))
