"""Receipt aggregation fixtures: no native model is imported, built or solved."""
from v42_a_stage_domain_v2 import stress_report as report


def write(path, value):
    report.write(path, value)


def active_receipts(folder, integer=False, full=False):
    stages = []
    for component in report.LEX:
        stage = dict(component=component, status=2, objective=0,
                     active_domain_global_bound=0, gap=0, native_seconds=1,
                     independently_verified=True, active_domain_objective_proven=True,
                     model_census=dict(rows=10, cols=5, binaries=1, integer_counts=2, nnz=15))
        stages.append(stage)
        write(folder/component/'PASS_RESULT.json', stage)
        write(folder/component/'INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json', {'PASS':True})
    closure = dict(ACTIVE_DOMAIN_SOLVED=True, STAY_DOMAIN_COMPLETE=True,
                   MIGRATION_PRICING_CLOSED=True, LP_PRICING_CLOSED=True,
                   INTEGER_DOMAIN_CLOSURE_PROVEN=integer, PRODUCTION_DOMAIN_ACCEPTED=full,
                   HARD_PHYSICAL_DOMAIN_DEFINED=True, ACTIVE_DOMAIN_SUBSET=True, FEASIBILITY_CLOSED=True,
                   independent_physical_PASS=True, all_scientific_objectives_certified=True,
                   integer_domain_certificate=dict(kind='COMPLETE_FINITE_DOMAIN_ACTIVATION',
                        independent_verification_PASS=True, full_scientific_domain_covered=True,
                        authority_sha256='a'*64, evidence_sha256='b'*64,
                        independent_verification={'PASS':True}) if integer else None)
    write(folder/'DOMAIN_CLOSURE_RESULT.json', closure)
    return dict(day='2025-05-17', passes=stages, A1_active_domain_feasible=True,
                A1_full_domain_accepted=full, integer_domain_closure_proven=integer,
                migration_pricing_closed=True, domain_status=closure)


def test_lp_pricing_and_active_optimality_never_become_integer_closure(tmp_path):
    result = active_receipts(tmp_path)
    summary, errors = report.summarize_date('2025-05-17', result, tmp_path, {})
    assert not errors
    assert summary['A1_active_domain_feasible'] and summary['ACTIVE_DOMAIN_SOLVED']
    assert summary['migration_pricing_closed']
    assert not summary['integer_domain_closure_proven']
    assert not summary['A1_full_domain_accepted']
    assert summary['final_classification'] == 'A1_ACTIVE_DOMAIN_SOLVED_DOMAIN_CLOSURE_UNRESOLVED'
    assert report.overall_classification([summary]*4) == 'A_STAGE_V2_STRESS4_UNRESOLVED'


def test_false_full_acceptance_fails_closed_without_independent_replay(tmp_path):
    result = active_receipts(tmp_path, integer=True, full=True)
    (tmp_path/'rho/INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json').unlink()
    summary, errors = report.summarize_date('2025-05-17', result, tmp_path, {})
    assert errors == ['FULL_ACCEPTANCE_WITHOUT_COMPLETE_CURRENT_LEX_AND_INTEGER_CLOSURE']
    assert not summary['A1_full_domain_accepted']
    assert summary['final_classification'] == 'SCIENTIFIC_IDENTITY_FAIL'


def test_integer_closure_flag_without_independent_certificate_is_rejected(tmp_path):
    result = active_receipts(tmp_path, integer=True, full=True)
    closure = report.read(tmp_path/'DOMAIN_CLOSURE_RESULT.json')
    closure['integer_domain_certificate'] = None
    write(tmp_path/'DOMAIN_CLOSURE_RESULT.json', closure)
    summary, errors = report.summarize_date('2025-05-17', result, tmp_path, {})
    assert not summary['integer_domain_closure_proven']
    assert not summary['A1_full_domain_accepted']
    assert any('INVALID_INTEGER_DOMAIN_CLOSURE_CERTIFICATE' in error for error in errors)
    assert summary['final_classification'] == 'SCIENTIFIC_IDENTITY_FAIL'


def test_prebuild_resource_failure_and_global_stop_have_honest_required_artifacts(tmp_path):
    out = tmp_path/'docs/stress'; authority = tmp_path/'docs/authority'
    write(out/'STRESS4_RESULTS.json', [
        dict(day='2025-05-17', classification='UNRESOLVED', passes=[], error='MEMORY_BEFORE_BUILD',
             computational_resource_failure=True, global_scientific_stop=False),
        dict(day='2025-05-19', classification='SCIENTIFIC_IDENTITY_FAIL', passes=[],
             error='INPUT_HASH_CORRUPTED', global_scientific_stop=True),
    ])
    returned = report.finalize('implementation-sha', 'https://example.org/pr/1', out=out, root=tmp_path,
                               authority_docs=authority, production=tmp_path/'production',
                               external_static=tmp_path/'external', check_git=False)
    assert returned['manifest_byte_verification_PASS']
    assert returned['overall_classification'] == 'A_STAGE_V2_REJECTED'
    summary = report.rows(out/'STRESS4_SUMMARY.csv')
    assert len(summary) == 4
    assert summary[0]['rho_value'] == ''
    assert summary[0]['computational_resource_failure'] == 'True'
    assert summary[2]['final_classification'] == 'NOT_ATTEMPTED_GLOBAL_SCIENTIFIC_STOP'
    assert summary[3]['final_classification'] == 'NOT_ATTEMPTED_GLOBAL_SCIENTIFIC_STOP'
    for day in report.DAYS:
        folder = out/('MAY'+day[-2:])
        assert all((folder/name).exists() for name in (*report.REQUIRED_JSON, *report.REQUIRED_CSV))
        assert report.read(folder/'INPUT_IDENTITY.json')['PASS'] is None
        assert report.rows(folder/'MODEL_CENSUS_BY_LEX_STAGE.csv')[0]['rows'] == ''
    review = (out/'FINAL_REVIEW_KO.md').read_text(encoding='utf8')
    assert '38. **Draft PR URL은?**' in review
    assert len([line for line in review.splitlines() if '. **' in line]) == 38
    assert '자기 참조가 불가능' in review


def test_may10_comparison_uses_exact_old_native_stage_not_original_replay_geometry(tmp_path):
    historical = tmp_path/'production/stages/2025-05-10/A1/1/output'
    write(historical/'A1_SOLVE_RESULT.json', dict(passes=[dict(component='shift_magnitude', status=9,
          native_runtime=3286.917, valid_LB=0, valid_UB=12)]))
    (historical/'A1_SOLVE.log').write_text('Optimize a model with 349197 rows, 189794 columns and 4652353 nonzeros (Min)\n'
          'Variable types: 146112 continuous, 43682 integer (38354 binary)\n'
          'Root relaxation: objective 0.000000e+00, 78667 iterations, 54.24 seconds (99.58 work units)\n', encoding='utf8')
    output = tmp_path/'out'; output.mkdir()
    result = dict(passes=[dict(component='shift_magnitude', objective=4, active_domain_global_bound=2,
                 native_seconds=5, active_domain_objective_proven=False,
                 model_census=dict(rows=100, cols=50, binaries=5, integer_counts=6, nnz=150))])
    report.may10_before_after(output, result, tmp_path/'production')
    values = {row['metric']:row for row in report.rows(output/'SHIFT_STAGE_BEFORE_AFTER.csv')}
    assert values['rows']['historical_value'] == '349197'
    assert values['integer_count_variables']['historical_value'] == '5328'
    assert values['nnz']['historical_value'] == '4652353'
    assert values['root_relaxation_seconds']['historical_value'] == '54.24'
    assert values['root_relaxation_seconds']['new_actual_value'] == ''
    assert values['exact_proof_seconds']['historical_value'] == ''
    assert values['exact_proof_seconds']['new_actual_value'] == ''


def test_external_byte_receipt_detects_corruption_and_unattested_files(tmp_path):
    out = tmp_path/'docs'; source = tmp_path.parent/(tmp_path.name+'_external_input.pkl')
    source.write_bytes(b'frozen')
    try:
        expected = report.record(source, tmp_path)
        write(out/'INPUT.json', {'input':expected})
        assert report.verify_external_artifacts(out, tmp_path, tmp_path/'static')['PASS']
        source.write_bytes(b'corrupt')
        verification = report.verify_external_artifacts(out, tmp_path, tmp_path/'static')
        assert not verification['PASS']
        assert verification['files'][0]['status'] == 'HASH_MISMATCH'
    finally:
        source.unlink(missing_ok=True)


def test_full_pass_needs_actual_pipeline_receipts(tmp_path):
    result = active_receipts(tmp_path, integer=True, full=True)
    result.update(Planning_freeze=True, Actual=True, Fresh_OpenDSS=True, physical_PASS=True)
    summary, errors = report.summarize_date('2025-05-17', result, tmp_path, {})
    assert 'FULL_PHYSICAL_PASS_WITHOUT_COMPLETE_PIPELINE_RECEIPTS' in errors
    assert summary['final_classification'] == 'SCIENTIFIC_IDENTITY_FAIL'
    for name in report.PIPELINE: write(tmp_path/name, {'PASS':True})
    summary, errors = report.summarize_date('2025-05-17', result, tmp_path, {})
    assert not errors
    assert summary['final_classification'] == 'STRESS_DATE_FULL_PASS'
    assert report.overall_classification([summary]*4) == 'A_STAGE_V2_STRESS4_PASS'


def test_report_rechecks_distinct_gates_and_frozen_source_bytes(tmp_path):
    out = tmp_path/'docs'; sources = {}; gates = {}
    for name in report.REQUIRED_RUN_SOURCE_NAMES:
        source = tmp_path/'v42_a_stage_domain_v2'/name
        source.parent.mkdir(exist_ok=True)
        source.write_text('# frozen source\n', encoding='utf8')
        sources[str(source.resolve())] = report.record(source)['sha256']
    for name in report.REQUIRED_STRESS_GATES:
        path = out/(name+'.json'); write(path, {'PASS':True})
        gates[name] = report.record(path, tmp_path)
    write(out/'PERMIT.json', dict(schema='A_STAGE_V2_STRESS4_VERIFIED_PERMIT_V1',
          run_order=list(report.DAYS), other_27_dates_authorized=False,
          actual_reoptimization_authorized=False, execution_sources=sources, gate_receipts=gates))
    first = report.verify_execution_freeze(out, tmp_path)
    assert first['PASS'] and len(first['gate_checks']) == 12
    source.write_text('# drift\n', encoding='utf8')
    second = report.verify_execution_freeze(out, tmp_path)
    assert not second['PASS']
    assert any('FROZEN_EXECUTION_SOURCE_DRIFT' in error for error in second['failures'])


def test_selected_freedoms_are_measured_against_exact_scientific_class_references():
    census = {'candidate_counts_by_class':[{'class_id':'c','members':['1','2','3']}],
              'no_flex_anchor_inclusion':{'records':[{'class_id':'c','reference_start':5,'reference_site':'A'}]}}
    schedule = {'selected_jobs':{
        '1':{'start':3,'initial_site':'A','checkpoint':-1},
        '2':{'start':5,'initial_site':'B','checkpoint':-1},
        '3':{'start':6,'initial_site':'B','checkpoint':8},
    }}
    audit = report.scheduling_freedom_audit(schedule, census)
    assert audit['PASS'] and audit['total_shift_slots'] == 3
    assert audit['earlier_than_reference_jobs'] == 1
    assert audit['choices_by_freedom_combination'] == {
        'TIMESHIFT':1, 'PRESTART_RELOCATION':1, 'TIMESHIFT+PRESTART_RELOCATION+MIGRATION':1}
    assert not audit['counterfactual_causality_proven']


def test_actual_model_changes_keep_legacy_full_and_reduced_axes_separate(tmp_path):
    out = tmp_path/'stress'; authority = tmp_path/'authority'
    write(authority/'MAY17_STATIC_DOMAIN_CENSUS.json', dict(
        old_native_F2_CRA_exact_census=dict(columns=80, constraints=90, binaries=3, integers=5, continuous=72, nonzeros=300),
        old_reduced_S0_exact_census=dict(columns=60, rows=70, binaries=2, integers=4, continuous=54, nnz=200)))
    report.table(out/'MAY17/MODEL_CENSUS_BY_LEX_STAGE.csv', [dict(
        stage='rho', cols=100, rows=120, binaries=6, integer_counts=8, continuous=86, nnz=400)])
    changes = report.model_size_changes(out, authority)
    may17 = {r['metric']:r for r in changes if r['date'] == '2025-05-17'}
    assert may17['columns']['new_actual_V2_rho'] == 100
    assert may17['columns']['delta_vs_historical_full_F2_CRA'] == 20
    assert may17['columns']['delta_vs_historical_reduced_A2SC'] == 40
    assert may17['rows']['delta_vs_historical_full_F2_CRA'] == 30
    assert all(r['new_actual_V2_rho'] is None for r in changes if r['date'] == '2025-05-19')
    sentence = report._model_change_sentence(changes)
    assert '변수 100' in sentence and 'delta 20' in sentence
    assert 'May19 native 모델 수는 관측 불가' in sentence


def test_failed_physical_replay_is_reported_even_before_pass_result_exists(tmp_path):
    write(tmp_path/'MAY19/rho/INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json', dict(
        PASS=False, base_original_rows=dict(PASS=False, original_authority_tolerance=1e-5,
              violations_over_authority=3, max_row_violation=0.01, worst_row_family='CC4'),
        physical=dict(PASS=False, failed=['CC4_CONTRACT'], CC4_max_violation=0.01,
              Runtime_max_violation=0, physical_capacity_max_violation=0)))
    observation = report.physical_observations(tmp_path, [dict(date='2025-05-19', physical_PASS=False)])
    replay = observation[0]['planning_point_replays'][0]
    assert replay['replay_PASS'] is False
    assert replay['original_rows_violations_over_authority'] == 3
    assert replay['failed'] == ['CC4_CONTRACT']
    assert observation[0]['fresh_physical_validation'] is None
    sentence = report._physical_sentence(observation)
    assert 'authority 초과 행=3' in sentence and 'CC4_CONTRACT' in sentence


def test_operational_progress_is_reported_without_full_domain_promotion(tmp_path):
    summaries = [dict(date=day, A1_active_domain_feasible=day[-2:] in ('17','19'),
        rho_active_optimum_proven=day.endswith('12'), shift_magnitude_active_optimum_proven=day.endswith('10'),
        shift_magnitude_value=4, prestart_relocation_active_optimum_proven=False, physical_PASS=False)
        for day in report.DAYS]
    write(tmp_path/'MAY12/rho/NATIVE_TELEMETRY.json', dict(root_relaxation=dict(seconds=12, iterations=100, objective=0.5)))
    sentence = report._problem_resolution(summaries, tmp_path)
    assert '인공 도메인 infeasibility: 새 독립 replay를 통과한 활성 feasible point로 해소' in sentence
    assert 'root 완료를 관측했습니다' in sentence
    assert '새 활성 shift exact optimum=4 증명' in sentence
    assert '전체 생산 및 Fresh 물리 PASS 날짜: 없음' in sentence


def test_unproven_zero_incumbent_does_not_become_zero_or_nonzero_optimum():
    uncertain = report._migration_zero_sentence(dict(migration_count_value=0, migration_count_active_optimum_proven=False))
    assert '미확인' in uncertain and '아니오' not in uncertain
    unknown = report._migration_zero_sentence(dict(migration_count_value=None, migration_count_active_optimum_proven=False))
    assert '미확인' in unknown and '관측 불가' in unknown
    assert '예.' in report._migration_zero_sentence(dict(migration_count_value=0, migration_count_active_optimum_proven=True))
    assert 'optimum=5' in report._migration_zero_sentence(dict(migration_count_value=5, migration_count_active_optimum_proven=True))
