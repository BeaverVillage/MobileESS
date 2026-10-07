"""Assemble completed forensic receipts. Never builds a native model or solves."""
import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
UB = 0.6694159238756877
KNOWN_LB = 0.5687116003498334
BASE = '1d922c91eb27056a5ccc79c92ef18146707099ab'


def js(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def table(name):
    with (OUT/name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False)+'\n', encoding='utf-8')


def write_table(name, records):
    fields = list(dict.fromkeys(k for r in records for k in r))
    with (OUT/name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pr-url', default='')
    args = p.parse_args()
    summary = js('LP_STRENGTHENING_SUMMARY.json')
    selective = table('SELECTIVE_INTEGRALITY_RESULTS.csv')
    assert len(selective) == 2 and {r['family'] for r in selective} == {'node_activity', 'charge_mode'}
    assert summary['rounds'] <= 10 and summary['MILP_calls_during_loop'] == 0
    assert not summary['materially_strengthened'], 'Material gain requires a separate causal/root review.'
    assert not (OUT/'C3S_ROOT_ONCE.json').exists()
    classification = 'ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS'
    trace = table('LP_STRENGTHENING_TRACE.csv')
    raw_trace = OUT/'LP_STRENGTHENING_TRACE_SOLVER_CAPTURE.csv'
    if not raw_trace.exists():
        raw_trace.write_bytes((OUT/'LP_STRENGTHENING_TRACE.csv').read_bytes())
    # The baseline log contains the original capture failure and authorized recovery.
    # Both have the same presolved dimensions; use the final solve's last record.
    presolved = re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',
                          (OUT/'PURE_LP.log').read_text(encoding='utf-8'))
    assert presolved
    ps0 = tuple(map(int, presolved[-1]))
    for r in trace:
        if int(float(r['round'])) == 0:
            r.update(presolved_rows=ps0[0], presolved_cols=ps0[1], presolved_nnz=ps0[2])
        for k, initial in zip(('presolved_rows', 'presolved_cols', 'presolved_nnz'), ps0):
            r[k+'_increase'] = int(float(r[k]))-initial if r.get(k) else ''
    write_table('LP_STRENGTHENING_TRACE.csv', trace)
    last = trace[-1]
    rounds = trace[1:]
    selected_cuts = js('SELECTED_CUTS.json')
    family_counts = dict(Counter(q['family'] for q in selected_cuts))
    candidates = table('CANDIDATE_VALID_INEQUALITIES.csv')
    violations = Counter(r['family'] for r in candidates if r['baseline_violated'] == 'True')
    proof = js('INEQUALITY_INDEPENDENT_VERIFICATION.json')
    folded = js('FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json')
    separation = js('LOCAL_HULL_SEPARATION_WITNESS.json')
    assert separation['PASS'] and separation['no_optimize_calls']
    abort = js('USER_AUTHORIZED_ABORT.json')
    pure = js('PURE_LP_RESULT.json')
    numerical = js('NUMERICAL_LP_BOUND_AUDIT.json')
    core = js('FRACTIONAL_CORE.json')
    target = .995*UB
    best_lb = max(float(r['valid_global_LB']) for r in trace)
    gain = best_lb-KNOWN_LB
    assert gain < .001 and abs(summary['best_valid_global_LB']-best_lb) < 1e-15
    assert abs(summary['absolute_improvement']-gain) < 1e-15
    assert summary['rounds'] == len(rounds) and summary['cuts'] == len(selected_cuts)
    assert int(float(last['total_cuts'])) == len(selected_cuts)
    assert len(list(OUT.glob('LP_ROUND_*_ONCE.json'))) == len(rounds)
    for r in rounds:
        n = int(float(r['round']))
        assert int(float(r['Status'])) == 2
        assert js(f'LP_ROUND_{n:02d}_ONCE.json')['optimize_calls'] == 1
        assert js(f'LP_ROUND_{n:02d}_RESULT.json')['Status'] == 2
    # Exact start checks are already independent proof receipts, never a new point repair.
    start_worst = max(float(r['validated_start_signed_violation']) for r in candidates)
    records = []
    start_audit = []
    for r in selective:
        s = js('SELECTIVE_'+r['family']+'_RESULT.json')
        assert int(float(r['Status'])) in (2, 9)
        assert math.isfinite(float(r['native_LB'])) and float(r['native_LB']) <= UB+1e-8
        assert js('SELECTIVE_'+r['family']+'_ONCE.json')['optimize_calls'] == 1
        log=(OUT/('SELECTIVE_'+r['family']+'.log')).read_text(encoding='utf-8')
        raw_types=re.search(r'Variable types: (\d+) continuous, (\d+) integer \((\d+) binary\)',log)
        assert raw_types and int(raw_types[2])==int(r['integer_columns'])
        assert int(raw_types[1])+int(raw_types[2])==306040
        accepted='Loaded user MIP start with objective 0.669416' in log
        assert accepted and s['LP_loop_completed_before_test']
        start_audit.append(dict(family=r['family'], original_binary_columns_restored=int(r['integer_columns']),
            raw_native_continuous=int(raw_types[1]),raw_native_binaries=int(raw_types[3]),
            start_supplied=True,start_accepted_in_native_log=accepted,
            source_start_SHA256='be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5',
            point_not_changed=True,TimeLimit=s['TimeLimit'],Runtime=s['Runtime'],
            native_finish_overrun_seconds=max(0.,s['Runtime']-s['TimeLimit']),
            strict_Runtime_within_300_seconds=s['Runtime']<=300,
            LP_loop_completed_before_test=True,started_UTC=s['started_UTC'],finished_UTC=s['finished_UTC']))
        records.append(dict(family=r['family'], status=int(float(r['Status'])),
                            native_LB=float(r['native_LB']),
                            conservative_native_LB=float(r['conservative_native_LB']),
                            valid_global_LB=max(KNOWN_LB, float(r['conservative_native_LB'])),
                            runtime=float(r['Runtime']), work=float(r['Work']),
                            selected_integrality_residual=s['point_replay']['restored_integrality_max_residual']
                            if s.get('point_replay') else None,
                            raw_matrix_replay_PASS=s['point_replay']['PASS'] if s.get('point_replay') else None,
                            diagnostic_only=True))
    save('SELECTIVE_START_AND_SCOPE_AUDIT.json',dict(PASS=True,no_optimize_calls=True,
        start_accepted_for_both_tests=True,actual_raw_native_types_match_semantic_family_map=True,
        presolve_may_infer_or_eliminate_types_without_changing_the_supplied_partial_integer_set=True,
        tests=start_audit))
    post = js('CUT_POINT_DIAGNOSTIC.json') if (OUT/'CUT_POINT_DIAGNOSTIC.json').exists() else None
    post_text = ''
    if post is not None:
        assert post['workflow_integrity_PASS'] and post['completed_cut_rounds']==len(rounds)
        assert post['selected_cuts']==len(selected_cuts) and post['optimize_calls']==0
        final_point = post['rounds'][-1]
        post_text = (f" 마지막 저장 cut LP 점의 원래 discrete 중 {final_point['discrete_total']['fractional_count']:,}개가 여전히 분수다. "
                     f"시험 후보 중 {final_point['remaining_candidate_violations_total']['unselected_violated_count']:,}개는 아직 미선택 위반으로 남았다. "
                     '이 값은 남은 후보의 효과나 gap 원인 증명이 아닌 point census다.')
    selective_gains = [r['valid_global_LB']-KNOWN_LB for r in records]
    if max(selective_gains) < .001:
        attribution = '두 제한 시험에서 지배적인 gap 기여 계열을 확정할 만큼의 전역 하한 상승을 얻지 못했다. TimeLimit 결과는 해당 계열의 무관함을 증명하지 않는다.'
    else:
        largest = max(records, key=lambda r:r['valid_global_LB'])
        attribution = (f"제한 시험에서 {largest['family']}의 전역 하한 상승이 가장 컸다 "
                       f"({largest['valid_global_LB']:.12f}). 이는 partial-integrality 진단이며 "
                       '전체 gap의 분해나 그 계열의 완전한 원인 증명은 아니다.')
    conclusion = dict(classification=classification,
        scope='Tested one-slot connected-power/mode/PCS hull cuts only; no global-hull impossibility claim.',
        production_selected_formulation='C3A',
        tested_strengthening_selected_for_production=False,
        base_PR=162, exact_base=BASE, reference_incumbent=UB, integer_optimum_known=False,
        gap_is_to_known_incumbent_not_proven_true_integrality_gap=True,
        pure_LP_objective_proxy=pure['objective'], pure_LP_raw_replay_PASS=False,
        baseline_valid_global_LB=KNOWN_LB, best_strengthened_valid_global_LB=best_lb,
        absolute_global_LB_improvement=gain, material_threshold=.001,
        material_strengthening_demonstrated=False,
        required_LB_for_point5percent_gap=target, required_LB_increase=target-KNOWN_LB,
        required_LB_increase_fraction_recovered=gain/(target-KNOWN_LB),
        final_LP_objective_proxy=float(last['rho']), final_LP_objective_proxy_gain=float(last['rho'])-pure['objective'],
        cut_LP_raw_feasibility_PASS_rounds=[int(float(r['round'])) for r in rounds if r['raw_matrix_replay_PASS']=='True' and float(r['max_added_cut_violation'])<=1e-8],
        cut_LP_raw_feasibility_FAIL_rounds=[int(float(r['round'])) for r in rounds if r['raw_matrix_replay_PASS']!='True' or float(r['max_added_cut_violation'])>1e-8],
        rounds=len(rounds), added_rows=len(selected_cuts), added_nnz=summary['added_nnz'],
        selected_cut_families=family_counts, baseline_violated_counts=dict(violations),
        original_rows_deleted=0, original_columns_added=0,
        final_matrix_rows=int(float(last['rows'])), final_matrix_columns=int(float(last['columns'])),
        final_matrix_nnz=int(float(last['nnz'])),
        final_LP_runtime=float(last['LP_Runtime']), final_LP_work=float(last['Work']),
        runtime_increase_vs_recovery_LP=float(last['LP_Runtime'])-pure['Runtime'],
        total_cut_LP_runtime=sum(float(r['LP_Runtime']) for r in rounds),
        total_cut_LP_work=sum(float(r['Work']) for r in rounds),
        baseline_presolved=dict(rows=ps0[0], columns=ps0[1], nnz=ps0[2]),
        final_presolved=dict(rows=int(float(last['presolved_rows'])), columns=int(float(last['presolved_cols'])), nnz=int(float(last['presolved_nnz']))),
        all_candidate_start_max_signed_cut_violation=start_worst,
        integer_feasible_set_preserved=proof['PASS'] and folded['PASS'],
        saved_projection_exact_local_hull_separation_witnesses=separation['witnesses'],
        original_P1_P2_preserved=True, tolerance_unchanged=1e-8,
        selective_integrality_results=records, selective_family_attribution=attribution,
        selective_bounds_are_native_MIP_attributes_with_minus_1e8_convention=True,
        selective_bounds_are_not_exact_rational_certificates=True,
        numerical_bound_certification_unresolved_if_proxy_gain_material=(float(last['rho'])-pure['objective'] >= .001),
        root_only_executed=False, root_only_skip_reason='No material independently validated LP bound gain.',
        native_barrier_ObjBound_used_as_certificate=False,
        scientific_point_repairs=0, new_full_MILP_calls=0,
        recommended_next_experiment=dict(experiments=1, executed=False,
            scope='MESS04, zero-based 4-slot window 69-72: exact joint route/stay/transit, charge-mode, P/Q and SOC transition hull, mapped to fixed critical grid rows line.sw1::A and line.l10::A.',
            rationale='Include observed fractional departures at 69, movement energy, connection at 71 and the critical row at 72. One-slot facets leave cross-time SOC/mobility and simultaneous critical-grid coupling unresolved.',
            boundary_SOC_not_fixed_to_observed_LP_values=True,
            preserve_original_physics=True, no_global_schedule_enumeration=True,
            separate_future_authorization_required=True),
        workflow_integrity_and_strict_numeric_feasibility_reported_separately=True)
    if post is not None:
        conclusion['final_cut_point_discrete_fractionality']=post['rounds'][-1]['discrete_by_family']
        conclusion['final_cut_point_remaining_candidate_violations']=post['rounds'][-1]['remaining_candidate_violations_by_family']
    save('ROOT_GAP_CONCLUSION.json', conclusion)
    selective_text = '\n'.join(
        f"| {r['family']} | {r['status']} | {r['runtime']:.3f} | {r['native_LB']:.12f} | {r['valid_global_LB']:.12f} |"
        for r in records)
    cut_text = ', '.join(f'{k} {v}개' for k,v in family_counts.items())
    pr = f'[Draft PR #{args.pr_url.rsplit("/",1)[-1]}]({args.pr_url})' if args.pr_url else 'Draft PR 생성 전: 이 문서가 포함된 commit으로 생성한 후 URL을 보완한다.'
    answers = [
        '예. 사용자 지시에 따라 정확한 대상 프로세스만 종료했고 재시작하지 않았다.',
        'PID 72696, Python311/python.exe, `run_one.py --run`, cwd `C:/v42_m1_c3_native_1h_20261007`. 프로세스 생성 UTC 06:56:49.758725, solver 시작 06:56:57.606972, 종료 07:37:07.492493(16:37:07 KST). Graceful IPC가 없어 identity 확인 뒤 해당 PID만 terminate했다.',
        '종료 시점의 native Runtime/Work는 얻지 못했다. 마지막 callback의 Runtime 346.781000137 s, Work 573.650794736는 종료보다 2,062.960724 s 오래된 관측이다. Wall 경과 2,409.744539 s를 native Runtime으로 바꾸어 쓰지 않았다.',
        '마지막 실제 callback UB=0.6694159238756877, LB=0.5687116103498335, native gap=15.0436089%, NodeCount=0, SolCount=1이다. 종료 시점의 bound/vector는 알 수 없다. 보존한 마지막 accepted incumbent은 원래 검증 start와 같은 SHA다.',
        '예. 완료 1시간 benchmark, TIME_LIMIT 결과, solver failure로 분류하지 않았다. `USER_AUTHORIZED_ABORT_FOR_ROOT_GAP_DIAGNOSIS` provenance로 분리했다. Post-root의 세부 작업 종류도 로그 없이 추정하지 않았다.',
        f"보존된 pure LP ObjVal={pure['objective']:.15f}, native OPTIMAL(2), Runtime {pure['Runtime']:.3f} s, Work {pure['Work']:.6f}, barrier 112회다. 첫 solve는 점 저장 전에 검증 assert로 capture를 잃었고, 사용자가 허용한 동일 설정 1회 추가 solve로 모든 X/Pi/RC/Slack을 저장했다. 총 순수 LP optimize는 2회다. RAW 행 위반 {pure['independent_relaxed_matrix_replay']['max_row_violation']:.12g}>1e-8이므로 엄격 feasible point 인증은 FAIL이다.",
        '9,322개. node_activity 8,938개, charge_mode 384개. Route flow는 continuous이며 단일 DAG path/node integrality로 연결된다. 별도 route/transit/connection/PCS binary는 없다. Terminal t=96의 node도 포함했다.',
        '7,454개, 79.9613817%. node 7,070개(79.1004699%), mode 384개(100%). 판정은 1e-8<x<1−1e-8이며 전체 Σmin(x,1−x)=472.381350188이다.',
        'Fractional 비율 및 평균 min(x,1−x)는 charge_mode가 가장 크다(100%, 0.482885820). 총 분수량은 node_activity가 더 크다(286.953195285 대 185.428154903). 최대 개별 변수는 charge_mode[MESS04,69]=0.499905056385다.',
        'MESS02의 총 분수량 118.435848441이 가장 크다. 다른 유닛도 약 117.93~118.02로 비슷하므로 특정 한 유닛에 집중된 현상은 아니다.',
        '최대 한 슬롯 block은 MESS04/69, 최대 4슬롯 window는 MESS02/73~76(분수량 5.996711602). 분수량의 80%에 3,504개, 90%에 5,271개 변수가 필요하다.',
        '예. 384개 유닛/슬롯 중 377개에서 둘 이상의 connected stay site에 질량이 있었다. t72 MESS02는 약 1의 stay 질량을 여덟 사이트에 분산했다.',
        '예. 복수 출발 MOVE route는 292개 슬롯, 같은 source/time의 arc 분기는 316개였다. 서로 다른 site stay만 있는 경우를 MOVE route split로 세지 않았다.',
        '예. 출발 MOVE/STAY 혼합 316개, 진행 중 transit을 포함한 connection/transit 혼합 352개다. node_activity를 transit 중 모든 시점의 실제 location binary로 해석하지 않았다.',
        '예. mode는 384개 모두 분수이고 C,D>1e-8도 384개에 있다. 최대 min(C,D)=78.960959357 kW. 그러나 peak의 일부 충전은 약 1e-7 kW이고, mode≈0.5 자체만으로 gap 기여를 증명하지 않는다. PCS-mode local hull 위반은 별도 검증했다.',
        '저장된 점의 active thermal face는 95개, 슬롯 66~95다. line.sw1::A(48), line.l3::A(1), line.l10::A(23), line.sw2::A(9), line.l116::A(12), line.l58::A(2). 대표 t72 line.sw1::A/C3 row 465244 및 t79 line.l10::A/row 497237를 원래 FULL row 축으로 복원했다.',
        't72 대표 행에서 baseline required rho 0.667834891220에 LP Pdis −0.100563786618, Q +0.001440838255, Pch 약 1.3e−10이 더해져 rho≈0.568711942988이다. Reference는 Pdis=0, Q +0.001581032656으로 rho≈0.669415923876이다. 분산 P/Q가 두 점 사이 차이를 만든다는 affine 증거는 있다. 모든 분수 배치가 정수 hull 밖이거나 이 차이 전체가 진짜 integrality gap이라는 증명은 없다.',
        attribution+' 아래 표의 LB는 diagnostic partial-MILP bound이며 해당 시험의 incumbent를 원래 all-integer 생산 UB로 쓰지 않았다.',
        'Aggregate charge-mode/discharge-mode caps, aggregate/local connected C+D perspective, 정확한 stored PCS16 charge/discharge half-polygons union에서 나온 네 folded PCS connected facets를 검토했다. 실제 cut 선택은 위반 크기, nnz, 고정 ID 순의 작은 32개 batch였다.',
        f"후보 {proof['total_candidate_count']:,}개 모두 독립 검증 PASS다. 기본 {proof['candidate_count']:,}개는 원래 DAG/물리 제약을 별도로 재구성하고, 4개 block의 정수 상태 13,964개·연속 꼭짓점 30,616개를 rational 계산했다. Folded 35,768개는 각 site의 원래 PCS vertices 및 보수적인 coefficient rounding을 검증했다. 변조 14건은 모두 거부됐다. 저장된 점의 최대 aggregate/local/folded 위반 19.1820303704/6.9897626252/16.7177797095도 dyadic 유리수로 정확히 재현했다(LOCAL_HULL_SEPARATION_WITNESS.json). 따라서 그 투영 좌표는 해당 유효 facet 밖이다. 원래 raw C3A feasible point 인증이나 모든 LP optimum의 위반 증명, 전역 96슬롯 hull의 완성 증명은 아니다.",
        f"Baseline 큰/작은 signed violation 판정 1e−8 기준: aggregate connected {violations['AGGREGATE_CONNECTED_POWER']}개, local connected {violations['LOCAL_CONNECTED_POWER']}개, folded {violations['FOLDED_PCS_CONNECTED_POWER']}개. Aggregate mode 두 계열은 0개다. Basic connected 위반은 모두 t66 이전이고 folded는 critical t66~95에 29개가 있다. RAW 점 인증 실패를 숨기지 않았으며 큰 구조적 위반과 작은 수치 위반을 구분했다.",
        f"기존 PR162 유효 conservative global LB={KNOWN_LB:.15f}. Pure LP primal proxy={pure['objective']:.15f}; 실제 native LP ObjBound={pure['native_global_LP_LB']:.12f}; 독립 exact bounded-Lagrangian LB={numerical['independently_valid_exact_certificate']['lower_bound']:.15f}. 세 값을 섞지 않았다.",
        f"추가 제약이 정수 집합을 보존하므로 이전 global LB를 운반하고 새 exact dual certificate와 max를 취했다. 최고 유효 strengthened global LB={best_lb:.15f}. 마지막 approximate ObjVal={float(last['rho']):.15f}는 하한 증명으로 사용하지 않았다. R1은 dual 저장이 없어 새 certificate를 만들지 않았다.",
        f"유효 global ΔLB={gain:.15f}. 마지막 primal proxy 변화={float(last['rho'])-pure['objective']:.12g}이며 이를 certified bound 상승으로 부르지 않는다.",
        f"0.5% 기준에 필요한 LB={target:.15f}, 기존 LB부터 필요한 상승={target-KNOWN_LB:.15f}. 검증된 상승으로 회수한 비율은 {100*gain/(target-KNOWN_LB):.6f}%다.",
        f"{len(selected_cuts)}행({cut_text}), 원래 행 삭제 0. Baseline 582,808행 → 실험 LP {int(float(last['rows'])):,}행; 열은 306,040개 그대로다. Production C3S로 채택하지 않았다.",
        f"추가 nnz {summary['added_nnz']:,}, 최종 {int(float(last['nnz'])):,}. ΔLB/1,000행 및 ΔLB/100,000nnz는 모두 {gain:.12g} 기준으로 계산했고 trace에 기록했다.",
        f"마지막 LP Runtime {float(last['LP_Runtime']):.3f} s, Work {float(last['Work']):.6f}; recovery baseline 대비 Runtime 증분 {float(last['LP_Runtime'])-pure['Runtime']:+.3f} s. 전체 {len(rounds)} cut LP Runtime 합 {sum(float(r['LP_Runtime']) for r in rounds):.3f} s. Baseline presolved {ps0[0]:,}/{ps0[1]:,}/{ps0[2]:,}(rows/cols/nnz)이며 각 회차 presolved 증분도 trace에 있다. Root-only는 수행하지 않았다.",
        f"예. 원래 start SHA be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5를 유지했다. 원래 C3A row 최대 위반 1.382773e−9, bound/integrality 위반 0 및 물리 replay PASS를 보존했다. 모든 후보 추가 행에 대한 최대 signed residual={start_worst:.12g}≤1e−8이다. Start를 수정하거나 feasibility 기준을 완화하지 않았다.",
        '예. 증명된 후보와 선택 제약은 모든 원래 integer-feasible 점에 유효하므로 원래 정수 feasible set과 각 점의 P1/P2 값을 보존한다. N4/H96, 원래 route·SOC·효율·이동 에너지·P/Q·PCS16·grid·A1 authority를 바꾸지 않았다. 이 증명과 수치 LP point의 RAW FAIL은 별개다.',
        f"아니오. 사전 material 기준 global ΔLB≥0.001을 만족하지 못했다. {len(rounds)}회/{len(selected_cuts)} cut까지의 제한 결과이며, 남은 후보나 전역 다기간 hull의 효과가 없다는 증명은 아니다."+post_text,
        '해당 없음. 독립 검증된 material LB gain이 없어 조건부 C3S native root-only solve를 실행하지 않았다. 결과를 만들어 쓰지 않았고 full B&B도 재개하지 않았다.',
        '검증된 한 슬롯 PCS/connection 누락은 존재하지만 그것을 제한된 batch로 강화해도 목표 gap을 설명하는 하한 상승은 입증하지 못했다. 이전 native root는 완료됐으므로 root 미완료가 이번 문제는 아니다. 모델 크기의 영향 및 post-root 작업 종류는 이 실험으로 확정하지 않았다. 시간 간 SOC/mobility와 여러 critical grid rows의 공동 결합이 남고, barrier 수치 인증 한계도 별도로 남는다.',
        '다음 실험은 정확히 하나만 권고한다: MESS04의 0-based 69~72 네 슬롯에서 원래 route/stay/transit·mode·P/Q·SOC transition을 공동으로 갖는 작은 exact hull을 만들고, 고정 line.sw1::A/line.l10::A 임계 행에 연결한 유효 cut의 위반과 LP bound 효과를 검사한다. 69 출발→71 연결의 분수 이동 세 개와 이동 에너지, 71의 C/D 혼합, 72의 최대 critical-face 차이를 한 창에 포함한다. 경계 SOC를 관측 LP 값으로 고정하지 않는다. 전역 96슬롯 schedule 열거, 물리 변경, full B&B 없이 별도 요청 후 진행한다. 이번에는 실행하지 않았다.',
        f"Base Draft PR #162 exact head `{BASE}`. Branch `codex/v42-m1-root-gap-attribution-20261007`. Draft PR: {pr}\n\n최종 commit은 이 검토 문서를 포함한 Draft PR의 최종 HEAD로 식별한다. 파일에 자기 자신의 commit SHA를 넣을 수 없으므로 실제 SHA는 PR body와 최종 응답에 기록하고 Git HEAD와 대조한다.",
    ]
    assert len(answers) == 35
    headings = ['기존 1시간 solve 중단','정확한 종료 프로세스','종료 Runtime/Work','종료 UB/LB/gap',
        '중단 실험의 benchmark 제외','순수 LP objective','원래 discrete 개수','분수 개수와 비율',
        '가장 분수인 계열','가장 분수인 MESS','가장 분수인 시간 window','Location split',
        'Route split','Move/stay 혼합','PCS/mode 혼합','rho 임계 line/time','rho 이점의 경로',
        '계열별 gap 기여','시험한 유효 부등식','독립 유효성 증명','Baseline 위반',
        'Baseline LB','최고 strengthened LB','절대 LB 변화','0.5% 목표 회수율','추가 행',
        '추가 nnz','LP/root 비용','기존 start feasibility','정수 집합 보존','Material 강화 여부',
        '최종 root-only bound','문제 분류와 미해결 결합','다음 과학 실험 하나','최종 commit / Draft PR']
    body = ('# M1 C3A root gap 진단 최종 검토\n\n'
            f'최종 분류: **{classification}**. 알려진 정수 incumbent와의 약 15.04% 차이는 '
            '진짜 정수 최적 gap의 증명이 아니다. 시험한 한 슬롯 hull에서 material한 검증 하한 상승은 얻지 못했다.\n\n'
            '순수 LP와 일부 강화 barrier 점의 RAW numerical FAIL을 유지하고 PASS 회차도 구분한다. 워크플로·해시·정수 유효성 검증과 '
            '엄격 수치 feasibility 검증을 분리해 `VERIFICATION.json`에 기록한다.\n\n')
    body += '\n\n'.join(f'## {i}. {h}\n\n{a}' for i,(h,a) in enumerate(zip(headings,answers),1))
    body += ('\n\n## 선택적 정수화 실제 결과\n\n'
             '| 계열 | native Status | Runtime(s) | native LB | 기존 LB와 max한 global LB |\n'
             '|---|---:|---:|---:|---:|\n'+selective_text+'\n\n'
             'Status 9는 TIME_LIMIT 진단이다. 각 TimeLimit=300, Threads=1이며 다른 원래 discrete 계열은 continuous다. '
             '`native LB` 열은 실제 partial-MILP ObjBound이다. 마지막 global LB 열에만 '
             '`max(기존 LB, nextafter(native LB−1e−8, −∞))` convention을 적용했고, exact rational dual certificate로 부르지 않는다. '
             'TimeLimit 설정 300초와 실제 Runtime을 분리했다. Gurobi는 종료에 필요한 속성 계산으로 Runtime이 설정 시간을 넘을 수 있다고 명시한다 '
             '([공식 TimeLimit 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#timelimit)). '
             '세부 row/bound 및 복원한 integrality 오차는 개별 RESULT JSON에 남겼다.\n')
    if float(last['rho'])-pure['objective'] >= .001:
        body += ('\nPrimal proxy의 변화는 material 수준이지만 독립 bound 인증은 따라오지 못했다. '
                 '`NUMERICAL_BOUND_CERTIFICATION_UNRESOLVED` 한계 때문에 cut이 효과 없다는 수학적 결론을 내리지 않는다.\n')
    (OUT/'FINAL_REVIEW_KO.md').write_text(body, encoding='utf-8')
    causal = OUT/'ROOT_GAP_CAUSAL_TRACE.md'
    text = causal.read_text(encoding='utf-8')
    marker = '\n## 완료 실험 결론\n'
    text = text.split(marker)[0]
    text += (marker+'\n'
        f"{len(rounds)}회 작은 batch LP 강화에서 총 {len(selected_cuts)}행, {summary['added_nnz']:,} nnz를 추가했다. "
        f"최고 유효 global LB는 {best_lb:.15f}, ΔLB={gain:.12g}이며 마지막 approximate primal rho는 {float(last['rho']):.15f}다. "
        'Primal proxy·native barrier ObjBound·exact bounded-Lagrangian certificate를 분리했다. '
        '이 실험은 한 슬롯 connection/mode/PCS hull의 제한적 강화로 gap을 설명하는 material 하한 상승을 입증하지 못했다.\n\n'
        +attribution+post_text+'\n\n'
        f"최종 분류는 `{classification}`이다. 조건부 native root-only는 실행하지 않았다. "
        '다음 미해결 결합은 시간 간 SOC/route/mode와 다수 critical grid rows이다. 권고한 하나의 후속 4슬롯 joint hull 실험도 실행하지 않았다.\n')
    causal.write_text(text, encoding='utf-8')
    save('WORK_STATE.json', dict(task='C3A root-gap attribution and exact strengthening',
        stage='EXPERIMENTS_COMPLETE_REPORTS_PREPARED',active_exec_session=None,
        completed_cut_rounds=len(rounds),selective_tests_completed=2,root_only_executed=False,
        original_one_hour_run_aborted_not_restarted=True,pure_LP_calls=2,
        extra_pure_LP_explicitly_authorized=True,scientific_changes=0,
        final_classification=classification,exact_base=BASE,
        pending=['final read-only verification','SHA256 manifest','commit/push Draft PR','publish final HEAD SHA']))
    print(json.dumps(dict(classification=classification,rounds=len(rounds),cuts=len(selected_cuts),
        best_valid_global_LB=best_lb,delta_LB=gain,strict_pure_LP_raw_PASS=False,
        no_optimize_calls=True), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
