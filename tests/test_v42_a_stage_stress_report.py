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
        expected = report.record(source)
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
        gates[name] = report.record(path)
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
