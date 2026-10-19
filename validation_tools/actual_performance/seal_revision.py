"""Seal only validated r016 sources and a precise natural-finish boundary."""
import sys,shutil,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44_recovery_r016 import operations as revision
from v44_recovery_r015 import operations as parent

ops=revision.OPS;dev=Path('D:/MobileESS_V44/development')
assert not revision.PERMIT.exists() and not (ops/'R016_CHANGE_AND_VALIDATION.json').exists()
parent.validate()
fresh_path=dev/'r016_three_arm_fresh_01/RESULT.json';fresh=read(fresh_path)
current_path=dev/'r016_integrated_current_01/RESULT.json';current=read(current_path)
assert fresh['PASS'] and current['PASS'] and fresh['Native_optimizer_calls']==current['Native_optimizer_calls']==0
assert {r['arm'] for r in fresh['checks']}=={'B0','B1','B3'}
assert all(r['PASS'] and r['wall_reduction_percent']>0 for r in fresh['checks'])
verify(current['baseline_sources']+current['candidate_sources'])
snapshot=dev/'r016_fresh_trial_source_snapshot'
math_pins=[]
for row in fresh['sources']:
    path=Path(row['path'])
    if path.parent==Path(revision.__file__).parent:
        saved=record(snapshot/path.name)
        assert saved['sha256']==row['sha256'] and saved['bytes']==row['bytes']
        if path.name not in ('operations.py','handover.py'):
            verify([row]);math_pins.append(row)
    else:verify([row])
assert record(Path(revision.__file__).parent/'b3_copy.py')['sha256']==record(Path(revision.__file__).parent.parent/'v44_actual_performance/memo_copy.py')['sha256']
suite=ET.parse(dev/'r016_final_regression.xml').getroot().find('testsuite')
assert int(suite.attrib['tests'])==168 and not any(int(suite.attrib[k]) for k in ['failures','errors','skipped'])
started=read(ops/'R015_USER_ACTUAL_STARTED.json')
assert alive(started['worker']) and alive(started['coordinator'])
case=revision.CAMPAIGN/'2025-05-01/B3/attempt003'
auth=ops/'R016_USER_AUTHORIZATION.json'
atomic(auth,dict(UTC=now(),user_instructions=[
    '응 r016으로 해서 B3 끝나면 그 다음부터 적용해.',
    '아니 B0과 B1 B3 모두에 개선 적용이 되어야돼.'],
    interpretation='Apply improvements to B0/B1/B3 after current B3 Actual and independent Fresh entire Case naturally ends. No restart or interruption.'))
guard=ops/'R016_HANDOVER_GUARD.json'
assert not guard.exists()
atomic(guard,dict(UTC=now(),authorization=record(auth),protected_case_root=str(case),
    protected_worker=started['worker'],protected_coordinator=started['coordinator'],
    protected_request=record(ops/'requests/2025-05-01_B3_attempt003.json'),
    previous_permit=record(parent.PERMIT),improved_arms=['B0','B1','B3'],
    boundary='TERMINAL_CASE_RESULT_AND_NATURAL_WORKER_AND_COORDINATOR_EXIT',
    current_case_interrupt_allowed=False,current_case_restart_allowed=False))
report=ops/'R016_CHANGE_AND_VALIDATION.json'
atomic(report,dict(UTC=now(),revision='v44_recovery_r016',PASS=True,
    predecessor=record(ops/'R015_CHANGE_AND_VALIDATION.json'),sources=revision.sources(),
    guard=record(guard),authorization=record(auth),tests_PASS=168,junit=record(dev/'r016_final_regression.xml'),
    improved_arms=['B0','B1','B3'],
    independent_Fresh=record(fresh_path),Fresh_timings=fresh['measurements'],Fresh_checks=fresh['checks'],
    Fresh_coverage='Every original120 chronological slot, every node and terminal, independent source-initial contexts, zero history or bank measurement reuse; physical_steps/Raw slots/TIME events SHA exact.',
    Fresh_measured_math_sources_unchanged_after_operational_handover_work=math_pins,
    Fresh_trial_source_snapshots=[record(p) for p in sorted(snapshot.glob('*.py'))],
    Current_AC=record(current_path),Current_checks=current['checks'],
    B3_copy_extended_timing=record(dev/'r016_final_b3_03/RESULT.json'),
    B1_Current_copy='Original r015 specialized graph clone retained; B1 gains the verified independent Fresh live-read optimization.',
    B0='Grid-blind event scheduling unchanged; independent Fresh live reads optimized.',
    Native_optimizer_calls_for_validation=0,physical_solves_removed=0,Fresh_measurements_removed=0,
    constraints_objectives_tolerances_Native_budgets_changed=False,
    scope_limit='Fixed diagnostic physical inputs and Current-P perturbations; no whole-controller/campaign speedup or service equivalence claim.',
    deployment='PENDING_CURRENT_B3_ENTIRE_CASE_NATURAL_FINISH',source_hotpatch=False))
snapshots=ops/'source_snapshots/r016';snapshots.mkdir(exist_ok=False)
for row in revision.sources():shutil.copyfile(row['path'],snapshots/Path(row['path']).name)
revision.make_permit();revision.validate()
atomic(ops/'R016_SEALED.json',dict(UTC=now(),PASS=True,permit=record(revision.PERMIT),validation=record(report),
    guard=record(guard),sources=revision.sources(),snapshots=[record(p) for p in sorted(snapshots.glob('*.py'))]))
print(dict(PASS=True,permit=record(revision.PERMIT),Fresh_checks=fresh['checks'],tests=168))
