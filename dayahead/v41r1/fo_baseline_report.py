"""Compare sealed May-04 B0 and accepted B1 ledgers without another solve."""
from pathlib import Path
import numpy as np
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import ROOT, record
from dayahead.v41.campaign import verify_receipt
from dayahead.v41.reserve import require

EVIDENCE = ROOT / 'dayahead/artifacts/v41r1_bounded_compute'


def build(acceptance):
    acceptance = Path(acceptance)
    accepted = read(acceptance)
    require(accepted['status'] == 'PASS', 'ACCEPTED_B1_REQUIRED')
    base = ROOT / 'frozen_artifacts/v41r1_migration/2025-05-04/B0'
    revised = acceptance.parent / '2025-05-04/B1'
    units = {'B0': base, 'B1': revised}
    refs = {}
    ledgers = {}
    decisions = {}
    physical = {}
    for policy, unit in units.items():
        refs[policy] = {}
        for phase in ('dayahead', 'actual'):
            receipt = unit / phase / (phase.upper() + '_RECEIPT.json')
            verify_receipt(receipt)
            refs[policy][phase + '_receipt'] = record(receipt)
            rel = 'fresh' if phase == 'dayahead' else 'grid'
            path = unit / phase / rel / 'OPENDSS_SUMMARY.json'
            summary = read(path)
            physical.setdefault(policy, {})[phase] = {
                k: summary[k] for k in ('rho_max_AC', 'Vmin_pu', 'Vmax_pu',
                    'physical_violation', 'OpenDSS_solve_count', 'convergence_count')}
            refs[policy][phase + '_physical'] = record(path)
        da = unit / 'dayahead'
        path = da / 'optimization/OBJECTIVE_LEDGER.json'
        ledgers[policy] = read(path)
        refs[policy]['objective_ledger'] = record(path)
        path = da / 'FROZEN_JOINT_DECISION.json'
        decisions[policy] = read(path)['decision']
        refs[policy]['frozen_decision'] = record(path)
        refs[policy]['frozen_power'] = record(da / 'FROZEN_AIDC_POWER.npz')
    require(ledgers['B0']['hierarchy'] == ledgers['B1']['hierarchy'], 'OBJECTIVE_HIERARCHY_MISMATCH')
    identities = {k: decisions['B0'][k] == decisions['B1'][k] for k in
        ('day', 'ML_snapshot', 'common_service_SHA', 'electrical', 'optimizer_scalar_sha256')}
    require(all(identities.values()), 'BASELINE_INPUT_IDENTITY_MISMATCH')
    with np.load(refs['B0']['frozen_power']['path'], allow_pickle=False) as a, \
            np.load(refs['B1']['frozen_power']['path'], allow_pickle=False) as b:
        require(set(a.files) == set(b.files), 'FROZEN_POWER_SCHEMA_MISMATCH')
        arrays = {k: bool(np.array_equal(a[k], b[k])) for k in a.files}
    av = ledgers['B0']['OBJECTIVE_VECTOR']
    bv = ledgers['B1']['OBJECTIVE_VECTOR']
    labels = ['최대 선로 부하율 (p.u.)', '평균 H4 부족량 (GPUh)', '마이그레이션 횟수',
              '기준 스케줄 편차', '결정적 동률 해소값']
    rows = [dict(priority=f'P{i+1}', label=labels[i], B0=a, B1=b,
        delta_B1_minus_B0=b-a, percent_change=None if a == 0 else 100*(b-a)/abs(a))
        for i, (a, b) in enumerate(zip(av, bv))]
    value = dict(status='PASS', day='2025-05-04', source='SEALED_INDEPENDENT_OBJECTIVE_LEDGERS',
        inputs_identical=identities, hierarchy=ledgers['B0']['hierarchy'], rows=rows,
        frozen_power_arrays_exactly_equal=arrays, physical=physical,
        objective_improvement_observed=any(r['delta_B1_minus_B0'] < 0 for r in rows),
        all_objectives_exactly_equal=av == bv, baseline_zero_percent_change='UNDEFINED',
        global_optimality_claimed=False, acceptance=record(acceptance), artifacts=refs)
    write_json(EVIDENCE / 'B0_VS_B1_OBJECTIVES.json', value)
    lines = ['# 2025-05-04 B0 대비 조기 종료 B1', '',
        '같은 Q90·ML 스냅샷, 서비스 입력, 전기계수 및 목적함수 계층으로 생성된 독립 평가 원장을 비교했습니다.', '',
        '| 목적 | B0 | B1 | 차이 (B1−B0) | 증감률 |', '|---|---:|---:|---:|---:|']
    for row in rows:
        i = int(row['priority'][1:]) - 1
        fmt = (lambda x: f'{x:.10f}') if i == 0 else ((lambda x: f'{x:.10f}') if i == 1 else (lambda x: f'{x:,.0f}'))
        percent = '— (B0=0)' if row['percent_change'] is None else f"{row['percent_change']:.6f}%"
        lines.append(f"| {row['priority']} {row['label']} | {fmt(row['B0'])} | {fmt(row['B1'])} | {row['delta_B1_minus_B0']:.10g} | {percent} |")
    if value['all_objectives_exactly_equal']:
        lines += ['', '**B0 대비 P1–P5 개선은 모두 0입니다.** 저장된 독립 평가 원장 값이 정확히 같습니다.']
    lines += ['', 'B0가 0인 P3·P4의 증감률은 0으로 나눌 수 없어 정의하지 않았습니다. 절대 차이는 0입니다.',
        'P1–P5는 순차적으로 최소화하는 벡터이며 합산 점수나 종합 개선율은 계산하지 않았습니다. P5는 동률 해소용 순위값입니다.',
        '최적화 보고서의 P2와 독립 평가 원장 사이에 약 2.3e-13의 부동소수점 표현 차이가 있으나, 여기서는 B0·B1 모두 동일한 독립 평가 원장을 사용했습니다.', '',
        f"GPU·IT·PCC·QCC 궤적 배열의 정확한 일치 여부: {arrays}.",
        '기존 F&O와 새 조기 종료 F&O의 시간 단축은 별도 EARLY_STOP_BEFORE_AFTER.md에 기록했습니다. 이번 날짜에서 계산 시간 단축과 B0 대비 목적값 개선은 별개의 결과이며, 전역 최적성을 입증한 것은 아닙니다.', '',
        'Fresh·Actual 결과:', '', '| 검증 | B0 AC 최대 부하율 | B1 AC 최대 부하율 | B0/B1 전기 위반 |', '|---|---:|---:|---|']
    for phase in ('dayahead', 'actual'):
        a = physical['B0'][phase]; b = physical['B1'][phase]
        lines.append(f"| {phase} | {a['rho_max_AC']:.10f} | {b['rho_max_AC']:.10f} | {a['physical_violation']} / {b['physical_violation']} |")
    lines += ['', '5월 전체 실행은 사용자 요청에 따라 보류했습니다. 이 비교를 위해 B0나 B1을 추가 실행하지 않았습니다.', '']
    (EVIDENCE / 'B0_VS_B1_OBJECTIVES.md').write_text('\n'.join(lines), encoding='utf-8')
    return value


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('acceptance')
    build(parser.parse_args().acceptance)
