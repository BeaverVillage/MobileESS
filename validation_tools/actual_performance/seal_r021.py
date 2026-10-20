from pathlib import Path
import sys,inspect,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44.common import read,record,atomic,now,digest
from v44_recovery_r021 import operations as ops
from v44_recovery_r019.operations import validate as validate19
from v44_recovery_r020.operations import validate as validate20
from v44_recovery_r020.phase_rebuild import Rebuild as PriorRebuild
from v44_recovery_r021.phase_rebuild import Rebuild
validate19();validate20()
assert inspect.getsource(Rebuild).replace('r021','r020').replace('R021','R020')==inspect.getsource(PriorRebuild)
tests=Path('D:/MobileESS_V44/development/r021_regressions_final.xml');tree=ET.parse(tests).getroot()
assert len(tree.findall('.//testcase'))==203 and not tree.findall('.//failure') and not tree.findall('.//error')
assert read(ops.OPS/'R021_CURRENT_A2_STOPPED.json')['Native_inflight'] is False
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r021',regressions=203,regression_receipt=record(tests),
    user_authorization=record(ops.OPS/'R021_USER_AUTHORIZATION.json'),old_interruption=record(ops.OPS/'R021_CURRENT_A2_STOPPED.json'),
    fresh_restart=dict(day='2025-05-02',arm='B3',completed_M1_preserved=True,new_A2_Native_start=0.,A2_total_native_budget=5400.,old_A2_time_and_point_not_imported=True),
    numerical_stability=dict(primary='Method1 NumericFocus3 ScaleFlag2 Aggregate0 Presolve1 LPWarmStart2',
        deterministic_repair='One Method0 Quad1 MarkowitzTol0.5 retry only after raw replay or dominance rejection, same shared native budget',
        prior_feasible_PStart=True,dominance_guard=True,all_original_primal_dual_zero_checks=True,
        tolerances_relaxed=False,native_matrices_or_objectives_changed=False,raw_values_rounded_or_clipped=False),
    original_rebuild_cache_implementation_identical=True,inherited_rebuild_validation=record(ops.OPS/'R020_CHANGE_AND_VALIDATION.json'),
    both_B1_B3_A2_improvements=True,previous_revisions_untouched=True,
    official_numerical_reference='https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/numeric_parameters.html',
    official_warm_start_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameterlpwarmstart',sources=ops.sources())
p=ops.OPS/'R021_CHANGE_AND_VALIDATION.json';assert not p.exists();atomic(p,report)
ops.make_permit()
out=ops.OPS/'source_snapshots/r021';out.mkdir(exist_ok=False)
for source in Path('v44_recovery_r021').glob('*.py'):(out/source.name).write_bytes(source.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(p)))
atomic(ops.OPS/'R021_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),permit=record(ops.PERMIT),validation=record(p)))
ops.validate();print(dict(PASS=True,regressions=203,new_A2_Native_start=0.))
