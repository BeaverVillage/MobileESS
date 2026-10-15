"""Read-only report fixtures; no native modules or raw model cache needed."""
import csv
import json

from tools.report_v42_table_v import report, stage_native, planning_actions


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')


def test_missing_arm_results_remain_not_run_and_no_native_is_inferred(tmp_path):
    source = tmp_path/'raw'; source.mkdir()
    result = report(source, output=tmp_path/'report')
    assert result['arm_statuses'] == dict.fromkeys(('B0','B1','B2','B3'), 'NOT_RUN')
    assert result['independently_replayed_Full96_PASS_arms'] == 0
    with (tmp_path/'report/MAY01_NATIVE_WALL_RAM_REPORT.csv').open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert all(r['Native_seconds'] == '' and r['Native_runtime_known'] == 'False' for r in rows)


def test_independent_arm_failures_preserved_and_raw_bytes_unchanged(tmp_path):
    source = tmp_path/'raw'; source.mkdir()
    for arm, stage in [('B0','ACTUAL96'), ('B2','M1')]:
        write(source/arm/'ARM_OUTCOME.json', dict(status='NOT_CERTIFIED',failed_stage=stage,error='exact source failure',P2_calls=0))
    before = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
    result = report(source, output=tmp_path/'report')
    assert result['arm_statuses']['B2'] == 'NOT_CERTIFIED' and result['arm_statuses']['B3'] == 'NOT_RUN'
    assert all(p.read_bytes() == content for p, content in before.items())
    with (tmp_path/'report/MAY01_FOUR_ARM_EXECUTION_LEDGER.csv').open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    failed = [r for r in rows if r['status'] == 'EXECUTION_FAILED']
    assert {(r['arm'],r['stage']) for r in failed} == {('B0','ACTUAL96'),('B2','M1')}


def test_native_runtime_not_added_to_nested_wall_or_external_costs():
    calls = [dict(solver='GUROBI',Native_Runtime=20.,wall_seconds=22.,stage_context=dict(arm='B2',stage='M1')),
             dict(solver='HIGHS',measured_seconds=8.,stage_context=dict(arm='B2',stage='M1')),
             dict(solver='BUILD',measured_seconds=30.,stage_context=dict(arm='B2',stage='M1'))]
    row = stage_native(calls,'B2','M1')
    assert row['Native_seconds'] == 20. and row['Native_optimize_wall_seconds'] == 22.
    assert row['HiGHS_wall_seconds'] == 8. and row['logged_build_wall_seconds'] == 30.


def test_planning_time_shift_is_not_claimed_as_actual_action():
    ref = dict(selected_jobs={'u':dict(start=24,initial_site='IDC00')})
    result = dict(selected_jobs={'u':dict(start=26,initial_site='IDC01',segments=[['IDC01',26,30]],migration_count=0)})
    row = planning_actions(result,ref,{})
    assert row['timeshift_UIDs'] == 1 and row['timeshift_total_minutes'] == 30.
    assert row['planning_prestart_site_changes'] == 1 and row['planning_action_is_Actual_action'] is False
