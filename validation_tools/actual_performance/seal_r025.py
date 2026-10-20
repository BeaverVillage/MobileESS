from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r025
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r025 import operations as ops
from v44_recovery_r024a.operations import validate as prior_validate

prior_validate()
assert not ops.workers() and not alive(read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'))
tree=ET.parse('D:/MobileESS_V44/development/r025/regressions.xml').getroot()
assert len(tree.findall('.//testcase'))>=274 and not tree.findall('.//failure') and not tree.findall('.//error')
verify(read(ops.OPS/'R025_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
stop=read(ops.OPS/'R025_CURRENT_A2_STOPPED.json');assert not stop['Native_inflight']
assert record(ops.CAMPAIGN/'2025-05-02/B3/attempt007/A2/NATIVE_RUNTIME_LEDGER.json')==stop['prior_ledger']
proof_path=Path('D:/MobileESS_V44/development/r025/current_continuation/ADMISSION.json')
proof=read(proof_path);assert proof['PASS'] and proof['new_Native_calls']==0 and not proof['Native_clock_reset']
verify(proof['sources']+[proof['checkpoint'],proof['native_parent']])
guard=dict(UTC=now(),protected_case_root=str(ops.CAMPAIGN/'2025-05-02/B3/attempt007'),
    protected_worker=stop['old_worker'],protected_coordinator=stop['old_coordinator'],
    authorization=record(ops.OPS/'R025_USER_AUTHORIZATION.json'),completed_A1_M1_preserved=True,
    fresh_A2_Native_start=proof['inherited_Native_seconds'],Native_clock_reset=False,
    previous_permit=record(ops.OPS/'RECOVERY_R024A_EXECUTION_PERMIT.json'))
atomic(ops.OPS/'R025_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r025',regressions=len(tree.findall('.//testcase')),
    regression_receipt=record('D:/MobileESS_V44/development/r025/regressions.xml'),
    authorization=record(ops.OPS/'R025_USER_AUTHORIZATION.json'),current_continuation=record(proof_path),
    Native_validation_calls=0,measured_Native_parent=proof['inherited_Native_seconds'],
    all_B1_B3_A1_A2_unconditional=True,total_measured_Native_seconds=3600.,Phase_I_measured_Native_seconds=400.,
    cutoff='SKIP_REMAINING_PHASE_I_AND_P1_RUN_ORIGINAL_INTEGER_MODEL_NO_ARTIFICIALS',
    timeout='FREEZE_BEST_ORIGINAL_ROWS_INTEGER_PHYSICAL_VERIFIED_UB_ALLOW_DOWNSTREAM',
    missing_UB='NO_FALSE_FEASIBILITY_OR_FREEZE_CONTINUE_NEXT_ELIGIBLE_DATE',
    UB_only_LB_and_gap_not_fabricated=True,A2_M2_UB_identity_gate_tested=True,
    physical_equations_domains_bounds_and_integrality_preserved=True,
    old_full_gap_contract_retained_for_certified_results=True,
    original_raw_and_ledgers_preserved=True,sources=ops.sources(),A2_solve_completion_not_yet_claimed=True)
atomic(ops.OPS/'R025_CHANGE_AND_VALIDATION.json',report)
ops.make_permit()
out=ops.OPS/'source_snapshots/r025';out.mkdir(exist_ok=False)
for p in Path('v44_recovery_r025').glob('*.py'):(out/p.name).write_bytes(p.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(ops.OPS/'R025_CHANGE_AND_VALIDATION.json')))
atomic(ops.OPS/'R025_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT)))
ops.validate();print(dict(PASS=True,regressions=report['regressions'],inherited_Native=proof['inherited_Native_seconds']))
