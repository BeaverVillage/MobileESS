"""Read-only four-arm evidence reader; writes new tables/reviews, never solves.

Unknown and unexecuted quantities remain empty/NOT_RUN. Native runtime is read
once from canonical ledgers; nested solver/build/Actual phase times are never
added to the inclusive arm wall clock. R2 is preserved on HOLD.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARMS = ('B0', 'B1', 'B2', 'B3')
STAGES = {'B0': (), 'B1': ('A1',), 'B2': ('M1',), 'B3': ('A1', 'M1', 'A2', 'M2')}
DEFAULT = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01'


def read(path, default=None):
    path = Path(path)
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def record(path):
    path = Path(path).resolve()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return dict(path=str(path), sha256=h.hexdigest(), bytes=path.stat().st_size)


def checked_json(descriptor):
    if record(descriptor['path']) != descriptor:
        raise ValueError('REPORT_RAW_SOURCE_BYTES_DRIFT')
    return read(descriptor['path'])


def unwrap(value):
    return value.get('result', value) if isinstance(value, dict) else {}


def attempt_folder(source, arm):
    base = (Path(source)/arm).resolve()
    pointer = read(base/'LATEST_ATTEMPT.json')
    if not pointer:
        return base, None
    target, name = Path(pointer.get('path','')).resolve(), pointer.get('name','')
    if (not name.startswith('ATTEMPT') or not name.replace('_','').isalnum()
            or target != base/name or pointer.get('prior_attempts_preserved') is not True
            or pointer.get('Native_budget_reset') is not False):
        raise ValueError('SOURCE_CONFINED_APPEND_ATTEMPT_POINTER_REQUIRED')
    return target, pointer


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def first(*values):
    return next((v for v in values if v is not None), None)


def csv_write(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(',', ':'))
                             if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})


def stage_native(calls, arm, stage=None, *, ledger_present=True):
    selected = [row for row in calls if row.get('stage_context', {}).get('arm') == arm
        and (stage is None or row.get('stage_context', {}).get('stage') == stage)]
    native = [r for r in selected if r.get('solver', '').startswith('GUROBI')]
    known = ledger_present and all(finite(r.get('Native_Runtime')) for r in native)
    return dict(Native_calls=len(native) if ledger_present else None, Native_seconds=sum(r['Native_Runtime'] for r in native) if known else None,
        Native_runtime_known=known,
        Native_optimize_wall_seconds=sum(r['wall_seconds'] for r in native if finite(r.get('wall_seconds'))) if ledger_present else None,
        HiGHS_wall_seconds=sum(r['measured_seconds'] for r in selected if r.get('solver') == 'HIGHS'
                              and finite(r.get('measured_seconds'))),
        logged_build_wall_seconds=sum(r['measured_seconds'] for r in selected if r.get('solver') == 'BUILD'
                                     and finite(r.get('measured_seconds'))))


def planning_actions(result, reference, policy):
    selected, baseline = result.get('selected_jobs', {}), reference.get('selected_jobs', {})
    if not selected:
        return dict(action_status='NOT_RECORDED')
    comparable = sorted(set(selected) & set(baseline))
    shifted, minutes, signed, placed, migrated = 0, 0., 0., 0, 0
    for uid in comparable:
        chosen, ref = selected[uid], baseline[uid]
        if finite(chosen.get('start')) and finite(ref.get('start')):
            delta = (chosen['start']-ref['start'])*15.
            shifted += int(delta > 0); minutes += max(0., delta); signed += delta
        placed += int(chosen.get('initial_site') != ref.get('initial_site'))
        migrated += int(chosen.get('migration_count', 0) > 0 or len(chosen.get('segments', ())) > 1)
    mask = policy.get('domain_mask', [])
    return dict(action_status='RECORDED_SELECTED_VS_SAME_CAUSAL_REFERENCE',
        selected_UIDs=len(selected), reference_comparable_UIDs=len(comparable),
        timeshift_UIDs=shifted, timeshift_total_minutes=minutes, signed_start_change_minutes=signed,
        planning_prestart_site_changes=placed, planning_migrated_UIDs=migrated,
        source_domain_mask_UIDs=len(mask) if isinstance(mask, list) else None,
        source_timeshift_eligible_UIDs=sum(len(r.get('allowed_native_starts', ())) > 1 for r in mask) if isinstance(mask, list) else None,
        source_migration_eligible_UIDs=sum(r.get('checkpoint_authorized') is True for r in mask) if isinstance(mask, list) else None,
        planning_action_is_Actual_action=False)


def mess_operation(plan):
    """Net-P diagnostics; do not claim an independently saved Pch/Pdis array."""
    soc = [v for row in plan.get('SOC', {}).values() for v in row if finite(v)]
    p = [v for row in plan.get('P_kW', {}).values() for v in row if finite(v)]
    q = [v for row in plan.get('Q_kvar', {}).values() for v in row if finite(v)]
    return dict(SOC_min_kWh=min(soc) if soc else None, SOC_max_kWh=max(soc) if soc else None,
        unit_netP_positive_energy_kWh=sum(max(v, 0.) for v in p)/4 if p else None,
        unit_netP_negative_energy_kWh=sum(max(-v, 0.) for v in p)/4 if p else None,
        maximum_abs_unit_Q_kvar=max(map(abs, q)) if q else None,
        Pch_Pdis_separate_raw_arrays_in_report=False,
        netP_diagnostic_does_not_replace_original_FULL_SOC_and_Mode_validation=True)


def fresh_metrics(wrapped):
    """Re-read recorded source rows and rerun the original settled validator."""
    fresh = unwrap(wrapped)
    if not fresh:
        return dict(status='NOT_RUN', verified_official_Full96=False)
    cert = fresh.get('official_certificate', {})
    result = dict(status=fresh.get('status', 'NOT_CERTIFIED'), verified_official_Full96=False,
        official_certificate_reported_status=cert.get('status'), executed_slots=fresh.get('executed_slots'),
        maximum_phase_line_loading=cert.get('maximum_phase_line_loading'),
        voltage_min_pu=cert.get('voltage_min_pu'), voltage_max_pu=cert.get('voltage_max_pu'),
        failing_slots=cert.get('failing_slots'), official_contract=fresh.get('official_contract'))
    try:
        raw = checked_json(fresh['raw_receipt'])
        rows = checked_json(fresh['raw_slot_rows'])
        from v42_integration.release_ac_contract import validate_settled_fresh
        replay = validate_settled_fresh(raw, rows, day=cert['day'], case_sha=cert['case_sha'],
            initial_state_sha=cert['initial_state_sha'], mess_plan_sha=cert['MESS_plan_sha'],
            trace_record=cert['actual_trace'], slots=96)
        if replay != cert:
            raise ValueError('REPORT_SETTLED_CERTIFICATE_DIFFERS_FROM_RAW_REPLAY')
        result['verified_official_Full96'] = True
        result['settled_raw_replay_status'] = replay['status']
        for field in ('voltage_violation_cells','line_current_violation_cells',
                      'transformer_current_violation_cells','transformer_kVA_violation_cells','AC_wall_seconds'):
            result[field] = raw.get(field)
    except (KeyError, ValueError, OSError, TypeError) as error:
        result.update(status='NOT_CERTIFIED', raw_replay_error=str(error))
    return result


def report(source=DEFAULT, *, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise FileExistsError('NEW_REPORT_DIRECTORY_REQUIRED_RAW_OUTPUTS_MUST_NOT_BE_OVERWRITTEN')
    output.mkdir(parents=True)
    contract = read(source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json')
    common = read(source/'MAY01_COMMON_INITIAL_STATE_CERTIFICATE.json')
    policy = read(source/'MAY01_FLEXIBILITY_POLICY_FREEZE.json')
    reference = read(source/'REFERENCE_RESULT.json')
    calls = read(source/'PLANNING_NATIVE_LEDGER.json').get('calls', []) + read(source/'K48_NATIVE_LEDGER.json').get('calls', [])
    main_present = (source/'PLANNING_NATIVE_LEDGER.json').is_file()
    both_present = main_present and (source/'K48_NATIVE_LEDGER.json').is_file()
    execution, planning, actual_rows, fresh_rows, funnel, mess_rows, resources = [], [], [], [], [], [], []
    raw_inputs, arm_data = [], {}
    for arm in ARMS:
        folder, pointer = attempt_folder(source, arm)
        if pointer:
            raw_inputs.append(record(source/arm/'LATEST_ATTEMPT.json'))
            if (source/arm/'ARM_OUTCOME.json').is_file():raw_inputs.append(record(source/arm/'ARM_OUTCOME.json'))
        outcome = read(folder/'ARM_OUTCOME.json')
        stage_results = read(folder/'PLANNING_STAGE_RESULTS.json')
        actual_wrapped = read(folder/'ACTUAL_RESULT.json')
        fresh_wrapped = read(folder/'FRESH_AC_RESULT.json')
        actual, actual_receipt = unwrap(actual_wrapped), unwrap(actual_wrapped).get('receipt', {})
        fresh = fresh_metrics(fresh_wrapped)
        arm_data[arm] = dict(outcome=outcome, actual=actual, fresh=fresh,
                            attempt=pointer['name'] if pointer else 'ORIGINAL')
        for name in ('ARM_OUTCOME.json','PLANNING_STAGE_RESULTS.json','ACTUAL_RESULT.json','FRESH_AC_RESULT.json','WALL_RAM_RESOURCE_REPORT.json'):
            if (folder/name).is_file(): raw_inputs.append(record(folder/name))
        for stage in (*STAGES[arm], 'ACTUAL96', 'FRESH_AC96'):
            entry = stage_results.get(stage, {})
            result, accepted = entry.get('result', {}), entry.get('acceptance', {}) or {}
            if stage == 'ACTUAL96': status = actual_wrapped.get('status', 'NOT_RUN')
            elif stage == 'FRESH_AC96': status = fresh['status']
            else: status = accepted.get('status', result.get('status', 'NOT_RUN'))
            if status == 'NOT_RUN' and outcome.get('failed_stage') == stage:
                status = 'EXECUTION_FAILED'
            execution.append(dict(arm=arm, stage=stage, status=status,
                attempt=pointer['name'] if pointer else 'ORIGINAL',
                arm_outcome=outcome.get('status', 'NOT_RUN'),
                failure_reason=outcome.get('error') if outcome.get('failed_stage') == stage else None,
                source_sha=contract.get('source_sha'), case_sha=contract.get('source_identity', {}).get('case_sha'),
                P2_calls=outcome.get('P2_calls') if outcome else None, **stage_native(calls, arm, stage, ledger_present=main_present)))
            if stage in STAGES[arm]:
                planning.append(dict(arm=arm, stage=stage, status=status,
                    FULL_feasible=first(result.get('FULL_feasible'), result.get('FULL_validated')),
                    stage_case_sha=first(result.get('case_sha'), accepted.get('stage_case_sha')),
                    AIDC_anchor=accepted.get('AIDC_anchor'), MESS_anchor=accepted.get('MESS_anchor'),
                    objective=first(result.get('objective'), result.get('BEST_GLOBAL_UB')),
                    bound=result.get('bound'), numeric_A_gap=result.get('gap'),
                    optimality_status=accepted.get('optimality_status', accepted.get('global_optimality_status')),
                    P2_calls=result.get('P2_calls'), **stage_native(calls, arm, stage, ledger_present=main_present)))
                if stage.startswith('A'):
                    funnel.append(dict(arm=arm, stage=stage, scope='PLANNING', **planning_actions(result, reference, policy)))
                else:
                    k = entry.get('K48', {}) or {}
                    plan = result.get('mess', {}) or {}
                    mess_rows.append(dict(arm=arm, stage=stage, status=status,
                        FULL_UB=result.get('BEST_GLOBAL_UB'), K48_status=k.get('status', 'NOT_RUN'),
                        K_reached=k.get('K_reached'), current_case_Global_LB=k.get('Global_LB'),
                        global_gap=k.get('relative_global_gap'), global_gap_certified=k.get('global_gap_certified'),
                        restricted_joint_pool_bound_is_global=False,
                        missed_K48_gap_blocks_FULL_feasible_Actual=False,
                        STAY_MOVE_complete_routes=plan.get('route_paths'), MOVE_count=len(plan['moves']) if 'moves' in plan else None,
                        injection_site_count=len(plan.get('P_by_site', {})) if plan else None,
                        SOC_unit_count=len(plan.get('SOC', {})) if plan else None,
                        raw_K48_error=k.get('error'), **mess_operation(plan)))
        actual_rows.append(dict(arm=arm, status=actual_wrapped.get('status', 'NOT_RUN'),
            executed_actual_slots=actual.get('executed_actual_slots'), Actual_stage_PASS=actual.get('Actual_stage_PASS'),
            evaluation_case_sha=actual.get('evaluation_case_sha'), MESS_plan_sha=actual.get('MESS_plan_sha'),
            actual_compute_GPUh=actual_receipt.get('actual_compute_GPUh'), actual_occupation_GPUh=actual_receipt.get('actual_occupation_GPUh'),
            completed_jobs=actual_receipt.get('completed_jobs'), carryout_jobs=actual_receipt.get('carryout_jobs'),
            capacity_violations=actual_receipt.get('capacity_violations'), dropped_jobs=actual_receipt.get('dropped_jobs'),
            actual_global_reoptimization=actual_receipt.get('actual_global_reoptimization'),
            future_duration_controller_reads=actual_receipt.get('future_duration_controller_reads'),
            P2_calls=outcome.get('P2_calls') if outcome else None))
        actual_funnel = actual.get('action_funnel', actual.get('flexibility_action_funnel', {}))
        funnel.append(dict(arm=arm, stage='ACTUAL96', scope='ACTUAL',
            action_status='RECORDED' if actual_funnel else 'NOT_RECORDED' if actual else 'NOT_RUN', **actual_funnel))
        fresh_rows.append(dict(arm=arm, **fresh))
        resource = read(folder/'WALL_RAM_RESOURCE_REPORT.json')
        resources.append(dict(arm=arm, inclusive_arm_wall_seconds=first(resource.get('wall_seconds'), outcome.get('wall_seconds')),
            peak_RSS_bytes=resource.get('peak_RSS_bytes'), peak_private_bytes=resource.get('peak_private_bytes'),
            inclusive_wall_contains_build_solve_Actual_AC=True, nested_times_must_not_be_added=True,
            **stage_native(calls, arm, ledger_present=both_present)))
    tables = {
        'MAY01_FOUR_ARM_EXECUTION_LEDGER.csv': execution,
        'MAY01_FOUR_ARM_PLANNING_RESULTS.csv': planning,
        'MAY01_FOUR_ARM_ACTUAL_RESULTS.csv': actual_rows,
        'MAY01_FOUR_ARM_FRESH_AC_RESULTS.csv': fresh_rows,
        'MAY01_AIDC_FLEXIBILITY_ACTION_FUNNEL.csv': funnel,
        'MAY01_MESS_UB_K48_GAP.csv': mess_rows,
        'MAY01_NATIVE_WALL_RAM_REPORT.csv': resources}
    for name, rows in tables.items(): csv_write(output/name, rows)
    statuses = {a: arm_data[a]['outcome'].get('status', 'NOT_RUN') for a in ARMS}
    pass_count = sum(statuses[a] == 'FULL_PASS' and arm_data[a]['fresh'].get('verified_official_Full96')
                     and arm_data[a]['fresh'].get('settled_raw_replay_status') == 'PASS' for a in ARMS)
    lines = ['# May01 Table V 비교', '', '| Arm | Computing | MESS | 실행 결과 | Raw Fresh96 재검산 |', '|---|---|---|---|---|']
    for a in ARMS:
        lines.append(f"| {a} | {'Reference' if a in ('B0','B2') else 'Full E1/FLEX30/R1'} | {'OFF' if a in ('B0','B1') else 'ON'} | {statuses[a]} | {arm_data[a]['fresh'].get('settled_raw_replay_status','NOT_RUN')} |")
    lines += ['', f'실제 Arm 결과와 raw settled Fresh96가 모두 PASS인 비교군은 {pass_count}/4개입니다.',
        '미실행·미기록 수치는 0으로 대체하지 않았습니다. Planning action은 Actual 실행 횟수로 전이하지 않았습니다.',
        '', 'A1/A2는 Arm·Stage마다 누적 Gurobi Native 5400초, M1/M2는 1800초이며 합산 총량 제한은 없습니다. K48은 별도 단계 원장입니다. Build·HiGHS·Actual·AC wall은 Native timeout에서 제외됩니다.',
        '표의 Arm wall은 중첩 시간을 포함한 실제 전체 wall입니다. Native/Presolve/Root/Build와 다시 더하지 않습니다.',
        '공식 물리 판정은 15분×96의 원래 settle_slot→measure_full_network입니다. Substep 진단은 별도로 보존하며 공식 판정을 대신하지 않습니다. 연속시간 안전 인증은 주장하지 않습니다.',
        '과거 Basic A1의 0.64211779208034와 과거 MESS UB/LB는 현재 Full E1 케이스에 전이하지 않았습니다. R2는 HOLD입니다.', '', '효과 비교는 최대 선로부하율과 실제 Compute GPUh를 함께 읽어야 합니다. 처리량 감소만으로 선로부하율이 낮아진 결과를 제어 개선으로 단정하지 않습니다.', '']
    by_arm = {r['arm']: r for r in actual_rows}
    for baseline, treatment, label in [('B0','B1','MESS OFF AIDC flexibility'),('B0','B2','Reference MESS'),('B1','B3','Flexible MESS'),('B2','B3','MESS ON AIDC flexibility')]:
        f0, f1 = arm_data[baseline]['fresh'], arm_data[treatment]['fresh']
        l0, l1 = f0.get('maximum_phase_line_loading'), f1.get('maximum_phase_line_loading')
        g0, g1 = by_arm[baseline]['actual_compute_GPUh'], by_arm[treatment]['actual_compute_GPUh']
        valid = f0.get('verified_official_Full96') and f1.get('verified_official_Full96')
        delta_l = l1-l0 if valid and finite(l0) and finite(l1) else 'NOT_CERTIFIED'
        delta_g = g1-g0 if finite(g0) and finite(g1) else 'NOT_RECORDED'
        lines.append(f'- {baseline}→{treatment} ({label}): 최대 선로부하율 차이 {delta_l}, 실제 Compute GPUh 차이 {delta_g}.')
    (output/'MAY01_TABLE_V_COMPARISON_KO.md').write_text('\n'.join(lines)+'\n', encoding='utf8')
    review = ['# May01 Release 후보 검토', '', f'현재 raw 검산 기준 FULL_PASS: {pass_count}/4.',
        '네 Arm 전체 PASS 전에는 May01 통합 ReleaseFreeze나 다른 날짜의 실행 성공을 선언하지 않습니다.',
        '원본 Adaptive Beam→4-MESS Joint→Original FULL→Incumbent registry와 K48만 실행 대상입니다. Joint 제한 후보풀의 ObjBound는 Global LB로 사용하지 않습니다.',
        '현재 단계의 FULL-feasible 해는 K48 목표 Gap 미달과 별도로 Actual 물리 평가에 전달할 수 있습니다.', '']
    for a in ARMS:
        outcome = arm_data[a]['outcome']
        review.append(f"- {a}: {statuses[a]}; 실패 단계={outcome.get('failed_stage','해당 없음/미기록')}; 사유={outcome.get('error','미기록')}.")
    review += ['', '다른 5월 날짜: 이번 실행 권한과 결과는 May01 전용입니다. 날짜별 현재 Case/초기 상태/정책/단계 FULL 부모 및 실제 Actual96·Fresh96 검증이 추가로 필요합니다.',
        'CSV는 raw에 실제 존재하는 항목만 기록합니다. 미기록 행동 수·QoS 세부값은 별도 raw funnel/queue/QoS 원장을 연결하기 전까지 미인증입니다.', '']
    (output/'MAY01_RELEASE_CANDIDATE_REVIEW_KO.md').write_text('\n'.join(review),encoding='utf8')
    for name in ('MAY01_TABLE_V_FOUR_ARM_CONTRACT.json','MAY01_COMMON_INITIAL_STATE_CERTIFICATE.json','MAY01_FLEXIBILITY_POLICY_FREEZE.json'):
        path = source/name
        if path.is_file():
            (output/name).write_bytes(path.read_bytes()); raw_inputs.append(record(path))
    for name in ('PLANNING_NATIVE_LEDGER.json','K48_NATIVE_LEDGER.json','REFERENCE_RESULT.json','REFERENCE_ACCEPTANCE.json','EXECUTION_SOURCE_FREEZE.json'):
        if (source/name).is_file():raw_inputs.append(record(source/name))
    manifest = dict(schema='MAY01_TABLE_V_REPORT_READ_ONLY_MANIFEST_V1', source=str(source),
        report_source=record(__file__), raw_inputs=raw_inputs, arm_statuses=statuses,
        independently_replayed_Full96_PASS_arms=pass_count, Native_optimize_calls=0, model_builds=0,
        unknowns_not_imputed_as_zero=True, total_native_cap=None, total_native_cap_enabled=False,
        R2='HOLD', raw_files_overwritten=False, generated_files=[record(p) for p in sorted(output.iterdir()) if p.is_file()])
    (output/'REPORT_GENERATION_RECEIPT.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = report(args.source, output=args.output)
    print(json.dumps(dict(arm_statuses=result['arm_statuses'], Full96_PASS=result['independently_replayed_Full96_PASS_arms'],
                         Native_optimize_calls=0, output=str(args.output)), ensure_ascii=False))
