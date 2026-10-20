"""Summarize verified isolated measurements without changing production."""
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import atomic,read,record,verify,now

dev=Path('D:/MobileESS_V44/development')
trial=dev/'r016_final_b3_03/RESULT.json'
result=read(trial)
assert result['PASS'] and result['Native_optimizer_calls']==0
verify(result['baseline_sources']+result['candidate_sources'])
suite=ET.parse(dev/'r016_final_unit.xml').getroot().find('testsuite')
assert int(suite.attrib['tests'])==45 and not any(int(suite.attrib[k]) for k in ['failures','errors','skipped'])
timing={}
for mode in ['r015','candidate']:
    rows=[r for r in result['measurements'] if r['mode']==mode and not r['warmup']]
    timing[mode]=dict(samples=len(rows),mean_wall_seconds=statistics.mean(r['wall_seconds'] for r in rows),mean_CPU_seconds=statistics.mean(r['CPU_seconds'] for r in rows),wall_samples=[r['wall_seconds'] for r in rows])
baseline=timing['r015'];candidate=timing['candidate']
ops=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY')
handoff=read(ops/'CURRENT_HANDOFF.json')
atomic(dev/'R016_ACTUAL_BOTTLENECK_SUMMARY.json',dict(
    UTC=now(),PASS=True,timing=timing,
    mean_wall_reduction_percent=100*(1-candidate['mean_wall_seconds']/baseline['mean_wall_seconds']),
    mean_CPU_reduction_percent=100*(1-candidate['mean_CPU_seconds']/baseline['mean_CPU_seconds']),
    equivalence='All four paired B3 real120-slot probes: exact PASS, physical_steps SHA, Raw slots SHA and Raw TIME events SHA; three timed diagnostic current-P perturbations after warmup.',
    tests_PASS=45,tests=record(dev/'r016_final_unit.xml'),benchmark=record(trial),
    profile=record(dev/'r016_profile_current_01/profile.txt'),
    profiling_limit='cProfile adds substantial Python-call overhead; use unprofiled alternating trials for timing claims.',
    bottlenecks='Per-candidate chronological prefix replay; repeated live inventory/equipment reads; physical record graph copying. In profiled120-slot probe: total22.337s, native SolveSnap0.335s, deepcopy4.756s; nested cumulative categories must not be summed.',
    existing_cache_diagnosis=record(dev/'r016_cache_duplicates.json'),
    candidate_sources=result['candidate_sources'],
    B1='Excluded: previous experimental alternative was slower. Final scope retains r015 B1 copy implementation.',
    Fresh='Bypassed entirely; no candidate scope patches for independent Fresh; covered by scope restoration/bypass tests. No new whole-event or whole-campaign equivalence claim.',
    Native_optimization_added=0,physical_solves_removed=0,limits_or_tolerances_changed=False,
    active_revision=handoff['active_revision'],production_deployment='NOT_APPLIED_DIAGNOSTIC_ONLY',
    running_case_interrupted=False,production_permit_changed=False,
    limitation='Fixed120-slot prefix diagnostics while original campaign continued on a different reserved physical core. No whole-Actual runtime speedup or completion ETA established.',
    next_substantial_work='Reduce repeated prefix validation/data handling with exact native-state and audit equivalence; current measurements do not establish a safe complete DSS state clone.'
))
print(json.dumps(dict(timing=timing,wall_reduction_percent=100*(1-candidate['mean_wall_seconds']/baseline['mean_wall_seconds']),tests=45,production_deployment='NOT_APPLIED_DIAGNOSTIC_ONLY'),indent=2))
