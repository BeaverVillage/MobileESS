"""Apply the two explicit V41 authority amendments without erasing prior audits."""
from pathlib import Path
import csv
import json
import shutil
from .preflight import ROOT, OUT, record, load
from .reserve import OBJECTIVE_HIERARCHY


def main():
    sources = [Path('C:/Users/kjw39/.codex/attachments/3aad41f2-039d-4276-ae58-bd0ce45feb3f/pasted-text.txt'),
               Path('C:/Users/kjw39/.codex/attachments/9607e7bf-ebdf-4786-a5fd-dbf75147b72f/pasted-text.txt')]
    archive = OUT / 'initial_authority_audit'
    archive.mkdir(exist_ok=True)
    for source, name in zip(sources, ['USER_LEXICOGRAPHIC_AMENDMENT.txt', 'USER_ACTUAL_REPLAY_AMENDMENT.txt']):
        destination = OUT / name
        if destination.exists():
            assert destination.read_bytes() == source.read_bytes()
        else:
            shutil.copyfile(source, destination)
    def update(name, value):
        path = OUT / name
        if path.exists() and not (archive / name).exists():
            shutil.copyfile(path, archive / name)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(path)
    hierarchy = list(OBJECTIVE_HIERARCHY)
    update('V41_H4_LEXICOGRAPHIC_OBJECTIVE_AUTHORITY.json', {
        'status': 'AUTHORIZED', 'authority': record(sources[0]),
        'old_hierarchy': ['MIN_RHO_MAX', 'MIN_MIGRATIONS', 'MIN_COMPLETE_REFERENCE_DEVIATION', 'STABLE_TIE'],
        'new_hierarchy': hierarchy, 'scalar_lambda': None,
        'reason': 'No semantically valid existing scalar GPUh shortage coefficient; explicit user amendment inserts sequential priority P2.',
        'mean_shortfall': 'sum(xi[k]) / 81', 'window_slots': 16,
        'stored_diagnostics': ['sum_xi_GPUh', 'mean_xi_GPUh'],
        'implementation': 'Existing sequential solve mechanism; insert P2 after P1 lock; lock P2 before existing lower priorities.',
        'P1_lock': 'Existing exact primary value lock retained; no intentional degradation allowance added.',
        'P2_lock_tolerance': {'B1_A0': 1e-9, 'A1': 1e-8},
        'tolerance_source': 'Existing model.Params.FeasibilityTol in respective inherited solvers',
        'policies': ['B0', 'B1', 'B2', 'B3'], 'objective_report': 'vector, never artificial scalar',
        'same_snapshot_A0_A1': True, 'same_snapshot_B0_B3': True,
        'M1_MF_route_PQ_unchanged': True, 'old_coefficient_gap_blocks_V41': False})
    gap = load(OUT / 'V41_RESERVE_PENALTY_AUTHORITY_AUDIT.json')
    gap.update(status='RESOLVED_BY_EXPLICIT_LEXICOGRAPHIC_AMENDMENT', coefficient=None,
               blocking=False, resolution_authority='V41_H4_LEXICOGRAPHIC_OBJECTIVE_AUTHORITY.json')
    update('V41_RESERVE_PENALTY_AUTHORITY_AUDIT.json', gap)
    contract = load(OUT / 'V41_RESERVE_INTERFACE_CONTRACT.json')
    contract.update(status='AUTHORIZED_IMPLEMENTATION_IN_PROGRESS', coefficient=None,
        coefficient_authority='NO_SCALAR_COEFFICIENT_REQUIRED_BY_AMENDMENT',
        preferred_aggregation='mean(xi)', objective_hierarchy=hierarchy, priority=2,
        reserve_constraint_implemented=True, authority='V41_H4_LEXICOGRAPHIC_OBJECTIVE_AUTHORITY.json')
    update('V41_RESERVE_INTERFACE_CONTRACT.json', contract)
    for name in ['V41_EXECUTION_AUTHORITY.json', 'V41_MAY_ACCESS_AUTHORITY.json']:
        value = load(OUT / name)
        value.update(run_gate='REQUIRES_PILOT_AND_INTEGRATION_GATES', reason='Both authority gaps explicitly resolved; execution gates remain.',
                     amendments=[record(p) for p in sources])
        update(name, value)
    value = load(OUT / 'V41_POLICY_REGISTRY_FREEZE.json')
    value.update(objective_hierarchy=hierarchy, policy_redefined=False,
        objective_amended_by_user=True, old_scalar_coefficient_gap_blocking=False)
    update('V41_POLICY_REGISTRY_FREEZE.json', value)
    transition = load(ROOT / 'dayahead/artifacts/v40m_authority72_closure/V40M_AUTHORITY_TRANSITION_MATRIX.json')
    rows = []
    for old in transition['case_transitions']:
        if old['new'] != 'AUTHORITY_MISSING':
            continue
        day, policy = old['case_id'].split('/')
        rows.append(dict(target_day=day, policy=policy,
            legacy_reason='OLD_CONTRACT_COUNTERFACTUAL_AUTHORITY_UNRESOLVED',
            V41_DA_decision_authority=f'frozen_artifacts/v41_may_campaign/{day}/{policy}/dayahead/freeze_receipt.json',
            realized_runtime_available='NOT_READ_BEFORE_DA_FREEZE', realized_workload_available='NOT_READ_BEFORE_DA_FREEZE',
            realized_grid_inputs_available='NOT_READ_BEFORE_DA_FREEZE', realized_traffic_available='NOT_READ_BEFORE_DA_FREEZE',
            V41_actual_replay_status='DEFINED_BY_COUNTERFACTUAL_REPLAY', execution_status='NOT_RUN'))
    assert len(rows) == 72
    with (OUT / 'V41_LEGACY_72_ACTUAL_REPLAY_CASES.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    update('V41_LEGACY_72_ACTUAL_REPLAY_CLOSURE.json', dict(
        legacy_total_cases=122, legacy_pre_day_complete=50, legacy_old_contract_unresolved=72,
        old_status='OLD_CONTRACT_COUNTERFACTUAL_AUTHORITY_UNRESOLVED',
        new_V41_status='DEFINED_BY_COUNTERFACTUAL_ACTUAL_REPLAY', resolution_type='SEMANTIC_AUTHORITY_CLOSURE',
        historical_observed_policy_execution_required=False, actual_reoptimization_allowed=False,
        recovered_missing_historical_data=False, V41_execution_completed=False, case_count=len(rows),
        authority=record(sources[1]), case_table=record(OUT / 'V41_LEGACY_72_ACTUAL_REPLAY_CASES.csv')))
    update('V41_COUNTERFACTUAL_ACTUAL_REPLAY_CONTRACT.json', dict(
        id='V41_COUNTERFACTUAL_ACTUAL_REPLAY_V1', authority=record(sources[1]),
        definition='REPLAY(FROZEN_DAYAHEAD_DECISION(policy,day), REALIZED_EXOGENOUS_OUTCOMES(day))',
        policy_variables=['admission/selection', 'site', 'scheduled start', 'rack where decided', 'migration'],
        pending_runtime='authoritative realized duration of the same job',
        pending_completion='frozen DA start plus realized duration; existing 900-second time discretization',
        frozen_start_reoptimization=False, frozen_site_change=False, RUNNING_authority_reopened=False,
        future_workload='score frozen reserve/headroom using realized arriving GPUh; no synthetic jobs or scheduling',
        MESS='existing realized link-entry traversal and energy contract, frozen route/commands',
        grid='existing exact OpenDSS with realized grid inputs and frozen counterfactual policy',
        ordering=['DA decision', 'decision hash', 'freeze receipt', 'open Actual inputs', 'replay', 'OpenDSS'],
        legacy_72_blocking=False, missing_realized_inputs='FAIL_CLOSED with exact missing source'))
    pilot = load(OUT / 'V41_MAY01_PILOT_DECISION.json')
    pilot.update(status='PENDING_INTEGRATION', reason='Authority amendments applied; pilot gates required')
    update('V41_MAY01_PILOT_DECISION.json', pilot)
    rationale = OUT / 'V41_OPERATIONAL_SELECTION_RATIONALE.md'
    if not (archive / rationale.name).exists():
        shutil.copyfile(rationale, archive / rationale.name)
    rationale.write_text('# V41 운영 인터페이스 선택\n\n'
        'Rolling Q90 Track-P L2와 H4 R85_B2를 사용하고 H24는 OFF로 고정한다. 기존 S5R1/R6R1 FAIL은 유지한다.\n\n'
        'GPUh 부족 벌점 계수가 없다는 최초 감사는 보존한다. 사용자의 추가 승인에 따라 rho_max 다음에 평균 H4 부족량을 최소화하고, '
        '이후 migration 수·기준 스케줄 편차·동률 해소를 기존 순서대로 수행한다. 새 lambda나 가중합을 사용하지 않는다.\n\n'
        'The primary grid-loading objective remains unchanged. Among electrically equivalent solutions, the scheduler '
        'preferentially preserves actionable four-hour GPU-service headroom for forecast future workload.\n\n'
        '과거 72개 policy-day의 문제는 V41_COUNTERFACTUAL_ACTUAL_REPLAY_V1로 의미상 해소했다. '
        '정책 변수는 동결한 Day-Ahead 결정, 정책과 무관한 실제 값은 역사적 외생 데이터가 근거다. 누락 데이터를 복구했다고 주장하지 않는다.\n\n'
        'Raw H4는 별도 보존한다. extreme raw reserve forecasts are saturated before optimization by causally historical '
        'and physically actionable capacity limits. 이는 raw 예측 정확도 개선 주장이 아니다.\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': 'AMENDMENTS_APPLIED', 'legacy_cases_defined': 72, 'scalar_lambda': None}))


if __name__ == '__main__':
    main()
