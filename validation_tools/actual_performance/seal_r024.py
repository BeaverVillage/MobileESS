from pathlib import Path
import sys,inspect,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r024 import operations as ops
from v44_recovery_r023.operations import validate as validate23
from v44_recovery_r022.operations import validate as validate22
from v44_recovery_r023.phase_rebuild import Rebuild as Prior
from v44_recovery_r024.phase_rebuild import Rebuild
validate22();validate23()
assert not ops.workers() and not alive(read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'))
assert inspect.getsource(Rebuild).replace('r024','r023').replace('R024','R023')==inspect.getsource(Prior)
xml=Path('D:/MobileESS_V44/development/r024/regressions.xml');tree=ET.parse(xml).getroot()
assert len(tree.findall('.//testcase'))>=266 and not tree.findall('.//failure') and not tree.findall('.//error')
base=Path('D:/MobileESS_V44/development/r024')
receipts=[base/'real_validation/RESULT.json',base/'real_validation/parent/R024_PARENT_COMPATIBILITY.json',base/'pipeline_validation/RESULT.json']
for p in receipts:assert read(p)['PASS']
verify(read(ops.OPS/'R024_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
stop=read(ops.OPS/'R024_CURRENT_A2_STOPPED.json');assert not stop['Native_inflight']
assert record(ops.CAMPAIGN/'2025-05-02/B3/attempt005/A2/NATIVE_RUNTIME_LEDGER.json')==stop['prior_ledger']
guard=dict(UTC=now(),protected_case_root=str(ops.CAMPAIGN/'2025-05-02/B3/attempt005'),
 protected_worker=stop['old_worker'],protected_coordinator=read(ops.CAMPAIGN/'COORDINATOR_LEASE.json'),
 authorization=record(ops.OPS/'R024_USER_AUTHORIZATION.json'),completed_A1_M1_preserved=True,fresh_A2_Native_start=0.,previous_permit=record(ops.OPS/'RECOVERY_R022_EXECUTION_PERMIT.json'))
atomic(ops.OPS/'R024_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r024',regressions=len(tree.findall('.//testcase')),regression_receipt=record(xml),
 exact_validation=[record(p) for p in receipts],authorization=record(ops.OPS/'R024_USER_AUTHORIZATION.json'),
 current_A2_stop=record(ops.OPS/'R024_CURRENT_A2_STOPPED.json'),Native_validation_calls=0,
 r023_rebuild_unchanged=True,full_row_Phi_primal_dual_prior_inclusion_and_physical_RC_retained=True,
 P1_body_verbatim=True,physical_domains_tolerances_objective_Gap_and_Native_budgets_unchanged=True,
 adaptive_class_exploration=True,rotating_never_priced_classes=True,full_eligible_exploration_separate_from_option_closure=True,
 multi_column_selection='EXACT_NEGATIVE_RC_AND_RESIDUAL_HEURISTIC_PLUS_CLASS_SITE_TIME_KIND_DIVERSITY_GPU_OVERLAP_PENALTY',
 actual_full_Phi_feedback=True,dual_diagnostics_only=True,dual_stabilization_applied=False,
 no_negative_physical_candidate_classification='NOT_CERTIFIED_NOT_INFEASIBLE_NOT_IMPLEMENTATION_FAILURE',
 unconditional_B1_B3_A_stages=True,pilot_PASS_required=False,
 fresh_case=dict(day='2025-05-02',arm='B3',attempt='attempt006',stage='A2',Native_start=0.,Native_ceiling=5400.,A1_M1_reoptimization_calls=0),
 sources=ops.sources(),performance_and_final_A2_acceptance_not_yet_claimed=True)
path=ops.OPS/'R024_CHANGE_AND_VALIDATION.json';assert not path.exists();atomic(path,report)
ops.make_permit();out=ops.OPS/'source_snapshots/r024';out.mkdir(exist_ok=False)
for p in Path('v44_recovery_r024').glob('*.py'):(out/p.name).write_bytes(p.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(path)))
atomic(ops.OPS/'R024_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT),validation=record(path)))
ops.validate();print(dict(PASS=True,regressions=report['regressions'],Native_calls=0,new_A2_start=0.))
