"""Summarize exact diagnostic evidence without claiming campaign speedup."""
import sys,statistics,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now

root=Path('D:/MobileESS_V44/development')
trial=read(root/'history_reuse_trial_02/RESULT.json')
boundaries=read(root/'history_reuse_boundaries_01/RESULT.json')
assert trial['PASS'] and boundaries['PASS']
verify(boundaries['sources'])
for row in trial['sources']:
    snapshot=root/'history_reuse_trial_02/source_snapshot'/Path(row['path']).name
    assert record(snapshot)['sha256']==row['sha256']
suite=ET.parse(root/'history_reuse_regressions.xml').getroot()
assert not suite.findall('.//failure') and not suite.findall('.//error')
timings=[]
for arm in ('B0','B1','B3'):
    data=boundaries['measurements'] if arm=='B0' else trial['measurements']
    selected=[v for v in data if v['arm']==arm and
        (v.get('label','').startswith('fixed120_delta_') if arm=='B0' else True)]
    by_mode={}
    for mode in ('r016','history'):
        values=[v for v in selected if v['mode']==mode]
        steady=[v for v in values if not (v['label'].endswith('_0.0') if arm=='B0' else v['warmup'])]
        warm=[v for v in values if v not in steady]
        by_mode[mode]=dict(steady_samples=len(steady),steady_mean_wall_seconds=statistics.mean(v['wall_seconds'] for v in steady),
            steady_mean_CPU_seconds=statistics.mean(v['CPU_seconds'] for v in steady),
            warmup_wall_seconds=warm[0]['wall_seconds'])
    reduction=100*(1-by_mode['history']['steady_mean_wall_seconds']/by_mode['r016']['steady_mean_wall_seconds'])
    timings.append(dict(arm=arm,**by_mode,steady_wall_reduction_percent=reduction,
        evidence=record(root/('history_reuse_boundaries_01/RESULT.json' if arm=='B0' else 'history_reuse_trial_02/RESULT.json'))))
from v44_recovery_r015.operations import validate as validate15
from v44_recovery_r016.operations import validate as validate16
validate15();validate16()
handoff=read(Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/CURRENT_HANDOFF.json'))
result=dict(UTC=now(),implementation='ISOLATED_STRUCTURAL_ACTUAL_HISTORY_AUDIT_ADAPTER',PASS=True,
    production_applied=False,active_revision=handoff['active_revision'],pending_revision=handoff.get('pending_revision'),
    existing_R015_and_R016_seals_verified=True,
    changes=['Immutable physical evidence graphs replace repeated deep copies.',
        'Historical control audit certificates reused only on full input-prefix, hardware, MESS, exact taps/caps/native queue/time, all complex voltages and native solution counters.',
        'Historical slots keep first and final complete live control and equipment guards plus unchanged outer inventories; repeated equipment audits within the same slot are consolidated.',
        'Low-cost historical slots take the unchanged r016 settle path.',
        'Current candidate remains fully checked; independent Fresh bypasses the adapter and keeps full measurements.'],
    tests=dict(regressions=len(suite.findall('.//testcase')),unit_source=record('tests/test_v44_actual_prefix.py'),
        receipt=record(root/'history_reuse_regressions.xml'),real_exact_pairs=len(trial['checks'])+len(boundaries['checks']),
        all_real_pairs_exact_Physics_Raw_slots_Raw_events_and_solve_counts=True,
        advancing_prefix_and_changed_observed_past=['B1','B3'],independent_Fresh120=['B0','B1','B3']),
    timing_scope='Three alternating repeated120-slot CurrentAC diagnostic candidates per arm, after warmup. B1/B3 timing sources archived in trial02; final boundary suite also validates added arm/clock identity and dynamic Fresh-copy bypass.',
    timings=timings,native_solves_removed=0,current_candidate_checks_skipped=0,
    hidden_native_snapshot_restored=False,constraints_objectives_tolerances_and_Native_budgets_changed=False,
    limitations=['This is not an end-to-end campaign runtime measurement.',
        'First probe builds proofs and may be slower; historical native chronological replay remains.',
        'Per-event historical live audit getter cadence changes: exact stored audit values are used between full live slot boundaries. This is not a pure no-value-cache r016 change.',
        'Deployment needs a separately sealed revision and execution policy for historical audit reuse; existing queued r016 is unchanged.'],
    sources=boundaries['sources'],validation_sources=[record('validation_tools/actual_performance/validate_history.py'),
        record('validation_tools/actual_performance/validate_history_boundaries.py'),record(__file__)],
    evidence=[record(root/'history_reuse_trial_02/RESULT.json'),record(root/'history_reuse_boundaries_01/RESULT.json')])
destination=root/'ACTUAL_STRUCTURAL_HISTORY_VALIDATION.json'
atomic(destination,result)
print(dict(report=str(destination),PASS=True,tests=result['tests']['regressions'],exact_pairs=result['tests']['real_exact_pairs'],timings=timings))
