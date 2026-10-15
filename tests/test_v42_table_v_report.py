"""Read-only report fixtures; no native modules or raw model cache needed."""
import csv
import json

from tools.report_v42_table_v import report, stage_native, planning_actions, mess_gap_fields, aidc_gap_fields


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')


def test_missing_arm_results_remain_not_run_and_no_native_is_inferred(tmp_path):
    source = tmp_path/'raw'; source.mkdir()
    result = report(source, output=tmp_path/'report')
    assert result['arm_statuses'] == dict.fromkeys(('B0','B1','B2','B3'), 'NOT_RUN')
    assert result['independently_replayed_Full96_PASS_arms'] == 0
    with (tmp_path/'report/TABLE_V_NATIVE_WALL_RAM_REPORT.csv').open(encoding='utf-8-sig') as stream:
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
    with (tmp_path/'report/TABLE_V_FOUR_ARM_EXECUTION_LEDGER.csv').open(encoding='utf-8-sig') as stream:
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


def test_mess_report_reassesses_legacy_target_without_editing_raw_evidence(tmp_path):
    source = tmp_path/'raw'; source.mkdir()
    current = dict(stage_case_sha='M1-current', aidc_anchor='fixed-current-A')
    k = dict(source=current,status='PARTIAL_ORIGINAL_K_SEQUENCE',K_reached=32,
        current_FULL_UB=.6,Global_LB=.59,relative_global_gap=(.6-.59)/.6,global_gap_target=.005,global_gap_certified=False,
        history=[dict(source=current,K=16,Global_LB=.59,numerical_global_bound_contract=True)])
    entry = dict(result=dict(FULL_validated=True,BEST_GLOBAL_UB=.6,native_call=dict(
        current_pool_ObjVal=.6,restricted_ObjBound_diagnostic=.599)),
        acceptance=dict(status='FULL_PASS',global_optimality_status='K48_NOT_RUN'),K48=k)
    path = source/'B2/PLANNING_STAGE_RESULTS.json'; write(path,dict(M1=entry))
    before = path.read_bytes()
    report(source,output=tmp_path/'report')
    with (tmp_path/'report/TABLE_V_MESS_UB_K48_GAP.csv').open(encoding='utf-8-sig') as stream:
        row = next(r for r in csv.DictReader(stream) if r['arm']=='B2')
    assert row['global_gap_target']=='0.03' and row['raw_global_gap_target']=='0.005'
    assert row['global_gap_certified']=='True' and row['raw_global_gap_certified']=='False'
    assert row['K_reached']=='32' and row['K_solved']=='16' and row['Global_LB_valid_K']=='[16]'
    assert row['K48_Global_LB_valid']=='False' and row['restricted_joint_gap_is_global']=='False'
    with (tmp_path/'report/TABLE_V_FOUR_ARM_PLANNING_RESULTS.csv').open(encoding='utf-8-sig') as stream:
        row = next(r for r in csv.DictReader(stream) if r['arm']=='B2')
    assert row['optimality_status']=='TARGET_MET' and path.read_bytes()==before


def test_uncertified_global_gap_cannot_be_filled_by_zero_or_restricted_gap():
    row = mess_gap_fields(dict(Global_LB=.6,relative_global_gap=0.,global_gap_certified=True))
    assert row['global_gap'] is None and not row['global_gap_certified']
    a = aidc_gap_fields(dict(AIDC_Global_LB=.6,AIDC_Global_UB=.6,gap=0.,relative_global_gap=0.,
        FULL_feasible=True,FULL_point_replay={'PASS':True},DW={'LB_certified':False}))
    assert a['AIDC_global_gap'] is None and a['AIDC_Global_LB'] is None
    assert a['AIDC_Global_UB']==.6 and a['AIDC_global_gap_target']==.005


def test_a_stage_failure_status_and_native_solver_fields_are_preserved(tmp_path):
    source = tmp_path/'raw'; source.mkdir()
    write(source/'B1/PLANNING_STAGE_RESULTS.json',dict(A1=dict(result=dict(FULL_feasible=False,
        Gurobi_Status=11,SolCount=0,objective=None,bound=.12,gap=None,case_sha='stopped-current-case'))))
    write(source/'B1/ARM_OUTCOME.json',dict(status='NOT_CERTIFIED',failed_stage='A1',error='interrupted source'))
    summary = report(source,output=tmp_path/'report')
    with (tmp_path/'report/TABLE_V_FOUR_ARM_PLANNING_RESULTS.csv').open(encoding='utf-8-sig') as stream:
        row = next(r for r in csv.DictReader(stream) if r['arm']=='B1')
    assert row['status']=='INTERRUPTED_NO_FEASIBLE' and row['Gurobi_Status']=='11' and row['SolCount']=='0'
    assert row['bound']=='0.12' and row['stage_case_sha']=='stopped-current-case'
    assert row['AIDC_global_gap']==''
    assert summary['arm_statuses']['B1']=='INTERRUPTED_NO_FEASIBLE'


def test_generic_date_contract_is_preferred_and_other_day_never_gets_may01_alias(tmp_path):
    source=tmp_path/'raw';source.mkdir()
    write(source/'TABLE_V_FOUR_ARM_CONTRACT.json',{'day':'2025-05-31','source_sha':'current-day'})
    write(source/'TABLE_V_COMMON_INITIAL_STATE_CERTIFICATE.json',{'day':'2025-05-31'})
    write(source/'TABLE_V_FLEXIBILITY_POLICY_FREEZE.json',{'policy_id':'current-policy'})
    write(source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json',{'day':'2025-05-01','source_sha':'stale'})
    result=report(source,output=tmp_path/'report')
    assert result['day']=='2025-05-31' and not list((tmp_path/'report').glob('MAY01*'))
    assert '2025-05-31 Table V' in (tmp_path/'report/TABLE_V_COMPARISON_KO.md').read_text(encoding='utf8')
    with (tmp_path/'report/TABLE_V_FOUR_ARM_EXECUTION_LEDGER.csv').open(encoding='utf-8-sig') as stream:
        assert all(r['source_sha']=='current-day' for r in csv.DictReader(stream))
    assert any(r['path'].endswith('TABLE_V_FOUR_ARM_CONTRACT.json') for r in result['raw_inputs'])


def test_legacy_may01_reader_keeps_exact_compatibility_aliases(tmp_path):
    source=tmp_path/'raw';source.mkdir()
    write(source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json',{'day':'2025-05-01'})
    result=report(source,output=tmp_path/'report')
    assert result['day']=='2025-05-01'
    assert (tmp_path/'report/MAY01_FOUR_ARM_PLANNING_RESULTS.csv').read_bytes()==(tmp_path/'report/TABLE_V_FOUR_ARM_PLANNING_RESULTS.csv').read_bytes()
    assert (tmp_path/'report/MAY01_TABLE_V_COMPARISON_KO.md').read_bytes()==(tmp_path/'report/TABLE_V_COMPARISON_KO.md').read_bytes()
