"""Emit honest non-execution/calibration receipts after April reprocessing."""
from .audit import ROOT, read, write, table, record
from .builder import B0_FLAGS, MODEL


def main():
    out = ROOT/'docs/v42_april_port_from_may_pipeline'
    summary = read(out/'APRIL/APRIL_GPU_AUTHORITY_SUMMARY.json')
    manifest = read(out/'APRIL/APRIL_INPUT_MANIFEST.json')
    if summary['complete_days'] or manifest['science_executed_days']:
        raise ValueError('THIS_REPORT_REQUIRES_GATED_NONEXECUTION; PRODUCE_MEASURED_RESULTS_INSTEAD')
    write(out, 'MAY_HOLDOUT_GUARD.json', dict(MAY_USED_AS_IMPLEMENTATION_BLUEPRINT=True,
        MAY_PIPELINE_USED_AS_BLUEPRINT=True, MAY_USED_FOR_MARGIN_CALIBRATION=False,
        MAY_SCIENTIFIC_OUTCOMES_USED_FOR_APRIL=False, May_job_values_as_donor=False,
        May_scientific_outcome_files_read=[], May_request_payload_members_read=[],
        May_optimizer_calls=0, May_OpenDSS_calls=0,
        permitted='code, schema, source/construction provenance, hash/footer/input-metadata structure',
        reproduction='small synthetic unit fixtures use the same generic builder; no heavy May scientific run',
        May_numeric_grid_coefficients_copied=False, May_population_or_reference_copied=False,
        guard_scope='May forensic and April construction/calibration data paths; inherited regression fixture reads disclosed separately',
        inherited_regression_fixture_reads=dict(
            present=True, example_test='tests/v42_certificate/test_native_evidence.py',
            scope='preserved sealed native matrix/solution/validation fixtures, read-only fidelity/contract checks',
            example_solution='docs/v42_m1_integrality_gap_root_cause/P_FIXED_ROUTE_SOLUTION.npz',
            example_validation='docs/v42_m1_late_window_certificate_mipstart/MIP_START_GRID_VALIDATION.json',
            April_input_or_margin_donor=False, new_May_scientific_rerun=False,
            blanket_all_tests_May_artifact_unread_claim=False)))
    flags = dict(B0_FLAGS, MAY_USED_AS_IMPLEMENTATION_BLUEPRINT=True, MAY_PIPELINE_USED_AS_BLUEPRINT=True,
        MAY_USED_FOR_MARGIN_CALIBRATION=False, MAY_SCIENTIFIC_OUTCOMES_USED_FOR_APRIL=False,
        CURRENT_RUNTIME_INFERENCE_USED=True, SCIENTIFIC_EXECUTED_DAYS=0,
        COMMON_REFERENCE_GENERATED_DAYS=0, APRIL_INPUT_BUNDLE_COMPLETE_DAYS=0,
        AIDC_physical_presence_verified=False, current_runtime_authority=MODEL)
    write(out, 'FINAL_FLAGS.json', flags)
    verdict = dict(status='BLOCKED_AFTER_FULL_MAY_FORENSIC_AND_APRIL_REPROCESSING',
        scientific_calibration_complete=False, May_GPU_rule_restored=True,
        May_missing_GPU_exact_derivation_exists=False, reusable_day_builder_created=True,
        April_population_retained=True, rows_dropped=0, GPU_imputed=False,
        initial_known_missing=summary['initial_known_missing'], initial_Actual_missing=summary['initial_Actual_missing'],
        expanded_missing_observations=summary['expanded_missing_observations'], expanded_unique_jobs=summary['expanded_unique_jobs'],
        recovered=summary['recovered'], unresolved=summary['unresolved'],
        complete_days=summary['complete_days'], target_days=30, common_reference_generated=False,
        B0_executed_days=0, DDay_physical_pass_days=None, physical_pass_evaluated_days=0,
        served_jobs=None, served_GPUh=None, AIDC_IT_energy_kWh=None, AIDC_PCC_energy_kWh=None, active_AIDC_slots=None,
        V_PLAN_generated=False, V_DA_AC_generated=False, V_DDAY_AC_generated=False,
        Q95_upper=None, Q95_down=None, Q99_upper=None, Q99_down=None,
        current_005_coverage=None, candidate_band=None, FINAL_MARGIN_ACCEPTED=False,
        May_scientific_outcomes_used=False, B1_B2_B3='NOT_RUN', M1_A2_M2_production='NOT_RUN',
        STOP_condition='Unresolved physical GPU demand remains after completed May source/code authority forensic and same exact April canonicalization; historical upstream exclusion conflicts with current no-drop contract.',
        additional_unbound_prerequisites=['Original submission request-version causality evidence',
            'April current CC4 date binding', 'April numerical planning anchor/coefficients and concrete independent Actual electrical backend'],
        input_inventory_is_executable_bundle=False, user_requested_scientific_execution_completed=False,
        preregistration=record(out/'PREREGISTRATION.json'))
    write(out, 'FINAL_VERDICT.json', verdict)
    residual_cols = ['day', 'node', 'phase', 'slot', 'V_PLAN', 'V_DA_AC', 'V_DDAY_AC',
                     'e_model', 'e_forecast', 'e_total', 'r_up', 'r_down']
    table(out, 'CALIBRATION/APRIL_B0_RESIDUALS.csv', [], residual_cols)
    cols = ['aggregation', 'q', 'n', 'delta_up', 'delta_down', 'lower_candidate', 'upper_candidate', 'nonempty_band', 'FINAL_MARGIN_ACCEPTED']
    for name, aggregation in [('POINTWISE_QUANTILES.csv', 'pointwise'), ('DAY_WORST_QUANTILES.csv', 'day-worst')]:
        rows = [dict(aggregation=aggregation, q=q, n=0, delta_up=None, delta_down=None,
                     lower_candidate=None, upper_candidate=None, nonempty_band=None, FINAL_MARGIN_ACCEPTED=False)
                for q in (.9, .95, .975, .99)]
        table(out, 'CALIBRATION/'+name, rows, cols)
    write(out, 'CALIBRATION/CURRENT_005_COVERAGE.json', dict(status='NOT_MEASURED_INPUT_GATE_FAIL',
        margin_up=.005, margin_down=.005, n=0, evaluated_days=0,
        pointwise_empirical_coverage=None, day_coverage=None, exceedance_days=None,
        worst_exceedance=None, worst_node_phase_slot=None))
    write(out, 'CALIBRATION/CANDIDATE_BANDS.json', dict(status='NOT_MEASURED_INPUT_GATE_FAIL', n=0,
        primary_voltage_pu=[.95, 1.05], candidates=[], lower_formula='.95+delta_down(q)',
        upper_formula='1.05-delta_up(q)', FINAL_MARGIN_ACCEPTED=False))
    (out/'NEXT_MODIFICATIONS.md').write_text(
        '# Remaining prerequisites\n\n'
        'The complete May forensic found direct raw GPU inheritance and historical resource exclusions, not a GPU recovery rule. '
        'All April rows remain. A source-backed requested GPU attribute for each unresolved exact submission is required before physical simulation; '
        'a unique scheduler request relation may be integrated with path/SHA/field/parser/identity receipts. Nodes, allocations, May jobs, defaults and dropping rows cannot supply it.\n\n'
        'Original request-version/ingestion history remains unverified separately from exact identity and submission-cutoff checks. '
        'Complete current April CC4 date binding and the concrete date-bound planning/independent Actual power/OpenDSS adapter are also required. '
        'The static topology, 780-GPU compatibility and frozen power equation lineage are restored. May numerical coefficients and historical dispatcher start repair remain prohibited.\n\n'
        'After all input gates pass, invoke the preserved PR121 common reference, then current B0 Planning at .95–1.05, freeze, offline forecast FreshAC, '
        'and D-Day FreshAC with zero repairs/reoptimization. Positive physical AIDC metrics and complete aligned residual axes are mandatory. '
        'Only measured April trajectories can populate quantiles, .005 coverage and asymmetric candidate bands; final margin acceptance remains false.\n',
        encoding='utf8', newline='\n')
    (out/'FINAL_REVIEW_KO.md').write_text(
        '# May blueprint → April current V42 후속 감사\n\n'
        'PR121 exact head c0783fadbbca282f2ce580c45fe82feaed71584c 위에서 기존 evidence와 983개 테스트를 보존했다. '
        'May raw→canonical→known/Actual→GPU→Runtime→site/rack/capacity→IT/PCC/Q→grid→Planning/Actual/OpenDSS chain을 17단계로 복원하고, 36개 field crosswalk와 날짜 독립 builder를 추가했다.\n\n'
        'May GPU authority는 raw `gpus_requested` → V37 ledger → frozen temporal schedule → V40d requested_GPU → V41 common reference → V42 GPU_gang 상속이다. '
        'V42 final은 current Q50 duration만 교체한다. request-version reconciliation, node 기반 exact derivation, missing GPU imputation은 발견되지 않았다. '
        'upstream `_submission_complete`/`_jobs_and_ledger`에는 missing/invalid resource exclusion이 있으나, 숫자 May 재현을 수행하지 않았으므로 '
        '특정 May 실행이 누락 row를 제거해 성공했다고 단정하지 않는다. 이 역사적 exclusion은 이번 no-drop contract에서 port하지 않았다.\n\n'
        f"April 원본 재처리: known missing {summary['initial_known_missing']:,}, initial Actual missing {summary['initial_Actual_missing']:,}, "
        f"expanded {summary['expanded_missing_observations']:,} observations / {summary['expanded_unique_jobs']:,} unique jobs. "
        f"Recovered {summary['recovered']:,}, unresolved {summary['unresolved']:,}, ambiguous {summary['ambiguous']:,}. "
        f"known {summary['known_jobs']:,}와 post-issue Actual {summary['actual_post_issue_jobs']:,} observations를 모두 유지했다. "
        '30일 input inventory를 새 builder로 생성하고 PR121 UID/GPU/Q50/service population과 대조했다. Known과 Actual completeness는 별도이며 input PASS는 0/30이다.\n\n'
        'Current frozen V10 Runtime inference를 실제 사용했으며 requested walltime은 feature only다. '
        'B0 AIDC/workload/ML flags는 true, flexibility/MESS는 off다. 그러나 input gate가 실패하여 executable common reference와 B0 Planning/AC는 생성·실행하지 않았다. '
        'AIDC energy/served workload, physical PASS, voltage, Q95/Q99, .005 coverage, candidate band는 측정되지 않았다. null과 n=0은 무측정이며 zero power 또는 physical PASS가 아니다.\n\n'
        '추가 prerequisite는 submission-version causality 증거, April current CC4 date binding, April planning coefficient/anchor 재생성과 concrete independent Actual adapter다. '
        'historical known-only Actual, requested-duration service, contention 기반 start 변경, legacy eligibility masking, May 숫자 계수는 현재 contract를 대체하지 않는다.\n\n'
        'May forensic과 April builder는 코드/schema/provenance/input metadata만 사용했다. 이 두 경로에서 May job values/outcomes/voltage/policy/calibration 결과를 읽거나 donor로 쓰지 않았다. '
        '기존 983 regression에는 sealed native matrix/solution/validation fixture를 읽는 fidelity/contract 검증이 포함된다. 이 조회는 MAY_HOLDOUT_GUARD.json에 별도 공개했으며 April input/보정 donor가 아니다. 전체 테스트가 모든 May artifact를 읽지 않았다고 주장하지 않는다. '
        'B1/B2/B3/May/M1/A2/M2 production NOT_RUN, Actual P/Q/route/schedule repair 및 full reoptimization=0. FINAL_MARGIN_ACCEPTED=false. '
        '검증 결과와 PR121 모든 base 파일 보존 여부는 VERIFICATION.json에 기록한다.\n',
        encoding='utf8', newline='\n')


if __name__ == '__main__':
    main()
