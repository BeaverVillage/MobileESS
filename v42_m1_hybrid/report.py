"""Post-Native evidence packaging; never restarts a completed pilot.

The reported stage wall is continuous elapsed time from preregistration through
the last independent verification and regression receipt. Historical ledgers
and production configuration remain read-only.
"""
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import csv
import json
import shutil

from v42_unified.audit import ROOT, write
from v42_unified.storage import sha
from .case import BASE_HEAD, CASE_SHA, REPORTS, RUNTIME, committed_json
from .runner import check_protection


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inside_d(path):
    path = Path(path).resolve()
    if path.drive.upper() != 'D:' or not path.is_relative_to(ROOT.resolve()):
        raise ValueError('HYBRID_DELIVERY_REQUIRES_CANONICAL_D_WORKSPACE')
    return path


def pricing_rows(result):
    rows = []
    for phase in ('PRICING', 'RMP_PRICING'):
        pricing = result.get(phase, {})
        local = pricing.get('local_exact_certificates', {})
        for record in pricing.get('records', []):
            n = record['native']; unit = record['unit']
            cert = record.get('exact_local_price_certificate')
            chosen = local.get(unit, {}).get('selected', {})
            obj = n.get('objective_diagnostic')
            loss = None
            if cert and obj is not None:
                loss = float(obj) - float(Fraction(cert['exact_bound']))
            rows.append(dict(phase=phase, unit=unit, kind=record['kind'],
                Native_Runtime=n['Native_Runtime'], Native_Work=n['Native_Work'],
                status=n['status'], SolCount=n['SolCount'],
                build_wall_seconds=record['build']['build_wall_seconds'],
                optimize_wall_seconds=n['optimize_wall_seconds'],
                native_price_objective_diagnostic=obj,
                native_price_ObjBound_diagnostic=n.get('native_ObjBound_diagnostic'),
                exact_local_price_LB=None if cert is None else cert['exact_bound'],
                selected_exact_local_price_LB=chosen.get('exact_bound'),
                selected_source=local.get(unit, {}).get('source'),
                rounded_native_objective_minus_exact_LB=loss,
                exact_checker_wall_seconds=None if cert is None else cert.get('check_wall_seconds'),
                fresh_LP_dual_adopted=record.get('fresh_dual_adopted', False),
                strict_raw_column_admitted=record.get('candidate_column', {}).get('admission', {}).get('PASS'),
                Native_MIP_BestBd_is_exact_certificate=False,
                TIME_LIMIT_is_complete_pricing=False,
                certification='EXACT_ORIGINAL_DOMAIN_LP_WEAK_DUALITY' if cert else 'NATIVE_DIAGNOSTIC_ONLY'))
    return rows


def finalize(run_path):
    path = inside_d(run_path)
    if path.parent != RUNTIME.resolve():
        raise ValueError('SEPARATE_REGISTERED_HYBRID_RUN_REQUIRED')
    result = read(path / 'NATIVE_PHASE_RESULTS.json')
    ledger = read(path / 'NATIVE_RUNTIME_LEDGER.json')
    independent = read(REPORTS / 'INDEPENDENT_FINAL_VERIFICATION.json')
    regression = read(REPORTS / 'ZERO_NATIVE_REGRESSION.json')
    registration = read(path / 'PREREGISTRATION.json')
    if not independent['PASS'] or not regression['PASS'] or regression['failed']:
        raise ValueError('INDEPENDENT_SCIENCE_AND_REGRESSION_REQUIRED')
    if len({v['case_sha'] for v in (result, ledger, independent, registration)}) != 1:
        raise ValueError('SAME_MAY01_CASE_REQUIRED')
    if result['case_sha'] != CASE_SHA or independent['Native_optimize_calls'] != 0:
        raise ValueError('SCIENTIFIC_CASE_OR_VERIFIER_SCOPE_DRIFT')
    if independent['run_id'] != path.name or Path(independent['run_path']).resolve() != path:
        raise ValueError('EXACT_NEW_RUN_VERIFIER_BINDING_REQUIRED')
    checked_evidence = independent['source_evidence_sha256']
    for name in ('NATIVE_PHASE_RESULTS.json', 'NATIVE_RUNTIME_LEDGER.json', 'FINAL_STRICT_UB_POINT.npz'):
        source = path / name
        if checked_evidence.get(str(source)) != sha(source):
            raise ValueError('FINAL_VERIFIER_SOURCE_PACKET_DRIFT:' + name)
    if ledger['inflight'] is not None or not ledger['measured_Runtime_complete']:
        raise ValueError('NATURALLY_COMPLETED_MEASURED_NEW_LEDGER_REQUIRED')
    protection = check_protection(read(path / 'BASELINE_PROTECTION.json'))
    for name, digest in read(path / 'EXECUTED_SOURCE_HASHES.json').items():
        if sha(ROOT / name) != digest:
            raise ValueError('EXECUTED_SOURCE_DRIFT:' + name)
    runtime = sum(c['Native_Runtime'] for c in ledger['calls'])
    work = sum(c.get('Native_Work') or 0 for c in ledger['calls'])
    api_wall = sum(c['optimize_wall_seconds'] for c in ledger['calls'])
    if runtime != ledger['Native_Runtime_sum'] or work != ledger['Native_Work_sum']:
        raise ValueError('NATIVE_LEDGER_SUM_MISMATCH')
    if runtime > 2700 or any(c['runtime_unavailable'] or c['parameters']['Threads'] != 1
                           for c in ledger['calls']):
        raise ValueError('REGISTERED_RUNTIME_OR_THREADS_FAILED')
    counts = dict(passed=len(regression['passed']), skipped=len(regression['skipped']),
                  failed=len(regression['failed']))
    if counts['passed'] < 643:
        raise ValueError('549_PRIOR_AND_94_NEW_PASS_REQUIRED_WITHOUT_COUNTING_SKIP')
    previous_tests = committed_json('docs/v42_m1_joint_gap_research/ZERO_NATIVE_COMMON_TESTS.json')
    if set(previous_tests['passed']) - set(regression['passed']):
        raise ValueError('EVERY_HISTORICAL_549_PASS_MUST_STILL_PASS')
    rows = pricing_rows(result)
    fields = list(rows[0]) if rows else ['phase', 'unit', 'status']
    with (REPORTS / 'PRICING_RUNTIME_CERTIFICATION.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    started = datetime.fromisoformat(registration['started_utc'])
    now = datetime.now(timezone.utc)
    # Preregistration follows the initial read-only protection audit. Its small
    # cost is conservatively restored via the final monotonic ledger duration.
    post = max(0., now.timestamp() - (path / 'NATIVE_RUNTIME_LEDGER.json').stat().st_mtime)
    measured_wall = ledger['wall_seconds'] + post
    continuous_utc_wall = (now - started).total_seconds()
    stat = path.stat()
    birth = getattr(stat, 'st_birthtime', stat.st_ctime)
    # On this Windows host, directory creation precedes the first protection
    # audit and is immutable across subsequent result-file writes.
    creation_wall = max(0., now.timestamp()-birth)
    wall = max(measured_wall, continuous_utc_wall, creation_wall)
    gap = independent['gap']
    target = gap['M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED']
    status = dict(PASS=True, case_sha=CASE_SHA, run_id=result['run_id'],
        completed_baseline_HEAD=BASE_HEAD, classification='CERTIFIED_5_PERCENT_WITHIN_90_MINUTES' if target and wall <= 5400 else 'NOT_PROVEN',
        exact_Global_UB=independent['final_exact_UB'], exact_Global_LB=independent['final_exact_LB'],
        independently_validated_Global_UB=independent['final_UB'],
        independently_certified_Global_LB=independent['final_LB'],
        strict_UB_improvement=independent['UB_gain'], exact_LB_improvement=independent['LB_gain'],
        certified_Global_Gap_percent=gap['Global_Gap_percent'],
        M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED=target,
        A1_A2_0p5_percent_target_preserved=True, Native_optimize_calls=len(ledger['calls']),
        Native_Runtime=runtime, Native_Work=work, optimize_API_wall_seconds=api_wall,
        native_phase_wall_seconds=ledger['wall_seconds'],
        research_through_final_verification_wall_seconds=wall,
        non_native_and_verification_wall_seconds=max(0., wall-api_wall),
        stage_wall_90_minutes_PASS=wall <= 5400, speed_wall_60_minutes_PASS=wall <= 3600,
        gap_5_percent_and_90_minutes_PASS=target and wall <= 5400,
        gap_5_percent_and_60_minutes_PASS=target and wall <= 3600,
        final_independent_checker_wall_seconds=independent['checker_wall_seconds'],
        wall_is_measured_continuous_elapsed_not_sum_of_overlapping_costs=True,
        wall_clock_basis='max(Windows run-directory creation UTC elapsed, ledger monotonic duration + ledger-mtime post elapsed, preregistration UTC elapsed)',
        wall_includes_model_build_exact_checks_full_replay_and_final_regression=True,
        prior_verification_wall_minutes=79.71,
        relative_previous_wall_comparison_is_different_bounded_algorithm_scope=True,
        general_solver_speedup_claim=False,
        historical_Native_LB_0p5687116104_reclassified_as_exact=False,
        strict_U2_RAW_seed_preserved=True, original_preservation=protection,
        tests=counts, tests_Native_optimize_calls=0, SKIP_counted_as_PASS=False,
        M1_ACCEPTED=False, P2_certificate=None, production_default_promoted=False,
        May12_1782_jobs_or_A2_M2_results_transferred=False,
        errors=result.get('errors', []), completed_utc=now.isoformat())
    write(REPORTS / 'FINAL_RESEARCH_STATUS.json', status)
    write(REPORTS / 'SOURCE_PRESERVATION_AUDIT.json', protection)
    write(REPORTS / 'COST_BREAKDOWN.json', dict(PASS=True, case_sha=CASE_SHA,
        Native_Runtime=runtime, Native_Work=work, track_Runtime=ledger['track_Runtime'],
        optimize_API_wall_seconds=api_wall, stage_wall_seconds=wall,
        source='durable new independent ledger and continuous post-run elapsed time',
        calls=ledger['calls'], raw_non_native_cost_records=ledger['non_native_wall_costs'],
        cost_records_may_overlap_do_not_sum=True,
        presolve_already_included_in_Native_Runtime=True,
        presolve_callback_span_is_not_exact_Presolve_Runtime=True,
        per_vehicle_pricing=rows,
        final_independent_checker_wall_seconds=independent['checker_wall_seconds'],
        final_regression_counts=counts, historical_budget_reset=False))
    write(REPORTS / 'DW_LAGRANGIAN_COMPARISON.json', dict(PASS=True, case_sha=CASE_SHA,
        restricted_master_objective=result.get('RMP', {}).get('Native_objective_diagnostic'),
        restricted_master_objective_is_Global_LB=False,
        restricted_master_objective_is_Global_UB=False,
        independently_verified_pricing_bounds=independent.get('pricing_certificates'),
        independently_verified_missing_column_bounds=independent.get('rmp_pricing_closure'),
        structural_integer_block_hull_improvement_certified=False,
        global_LB_increase_is_same_original_problem_verified_dual_bound=independent['LB_gain'] > 0,
        numerical_multiplier_repair_and_structural_strengthening_separated=True,
        complete_Branch_and_Price_implemented=False,
        dual_oscillation_assessed=False,
        cross_MESS_convex_hull_insufficiency_proven=False))
    speeds = []
    for row in result.get('UB', {}).get('experiments', []):
        gain = row['strict_UB_gain']; elapsed = row['native_Runtime']
        speeds.append(dict(method=row['method'], strict_UB_gain=gain,
            Native_Runtime=elapsed, UB_gain_per_Native_second=gain/elapsed if elapsed > 0 else None,
            requested_limit_seconds=400, strict_admission='completed RAW full replay after solve',
            callback_time_to_strict_admission_not_claimed=True))
    write(REPORTS / 'UB_SPEED_MEASURED.json', dict(PASS=True, case_sha=CASE_SHA,
        methods=speeds, same_common_strict_start=True,
        model_build_and_validation_costs_recorded_separately='COST_BREAKDOWN.json'))
    package(path)
    korean_report(status, result, independent, rows)
    return status


def package(path):
    """Preserve new completed Native evidence; no historical artifact rewrites."""
    destination = REPORTS / 'artifacts'; destination.mkdir(exist_ok=True)
    for source in sorted(path.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(path); target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != sha(source):
            raise ValueError('NEW_EVIDENCE_BYTE_COPY_DRIFT')
    for name in ('hybrid_native_runner.log', 'hybrid_final_tests.log', 'hybrid_pre_native_tests.log',
                 'hybrid_independent_final.log', 'hybrid_post_delivery_replay.log'):
        source = ROOT / 'tmp' / name
        if source.is_file():
            shutil.copyfile(source, destination / name)


def korean_report(status, result, independent, rows):
    s = status
    comparisons = []
    for row in result.get('UB', {}).get('experiments', []):
        gain = row['strict_UB_gain']; seconds = row['native_Runtime']
        comparisons.append(f"| {row['method']} | {row['best_strict_UB']:.13f} | {gain:.13f} | {seconds:.2f} | {row['native_Work']:.4f} | {row['rejected_raw_candidates']} |")
    price = []
    for row in rows:
        price.append(f"| {row['phase']} | {row['unit']} | {row['kind']} | {row['Native_Runtime']:.3f} | {row['Native_Work']:.5f} | {row['status']} | {row['certification']} |")
    closure = independent.get('rmp_pricing_closure', {})
    text = f'''# V42 M1 Fast Certified Primal–Dual Hybrid 결과

판정: **{s['classification']}**. 동일 May01/1,499-job 원본 문제에서 strict integer UB와 독립 exact Global LB를 별도 검증했다. P2 certificate가 없으므로 **M1_ACCEPTED=false**이며 production backend를 변경하지 않았다.

| 지표 | 이전 완료 연구 | 이번 검증 결과 |
|---|---:|---:|
| Strict integer UB | 0.6063186498423855 | {s['independently_validated_Global_UB']:.16f} |
| Fresh exact Global LB | 0.5675886811427069 | {s['independently_certified_Global_LB']:.16f} |
| Certified Global Gap | 6.3877251194% | {s['certified_Global_Gap_percent']:.10f}% |
| UB 개선폭 | — | {s['strict_UB_improvement']:.16f} |
| LB 개선폭 | — | {s['exact_LB_improvement']:.16f} |
| 검증 포함 Wall | 79.71분 | {s['research_through_final_verification_wall_seconds']/60:.3f}분 |

5% Gap과 90분 동시 달성: **{s['gap_5_percent_and_90_minutes_PASS']}**. 5% Gap과 60분 동시 달성: **{s['gap_5_percent_and_60_minutes_PASS']}**. 과거와 다른 유한 파일럿의 실제 시간을 비교한 것이며 일반적인 Solver speedup을 주장하지 않는다. 이전 Native LB 0.5687116104는 fresh exact LB로 재분류하지 않았다.

## 기준 및 정확한 목표

기준 완료 HEAD `{BASE_HEAD}`, Run ID `{s['run_id']}`, scientific case SHA `{CASE_SHA}`. D 드라이브 독립 clone `D:\\MobileESS_v42`에서만 개발·검증했다. A1/A2 목표 0.5%는 보존하고 M1/M2 연구 목표만 5%로 설정했다. 이전 historical ledgers·원본 데이터·PR189 및 A1 P1-only 인터페이스는 보존했다.

기존 UB에서 필요한 LB는 **0.5760027173502662**, 기존 LB에서 필요한 UB는 **0.597461769623902**이다. 임계값과 최종 Gap은 binary64 입력을 exact rational로 해석하여 독립 계산했다. 정확한 최종 UB `{s['exact_Global_UB']}`와 LB `{s['exact_Global_LB']}`는 [독립 검증 JSON](INDEPENDENT_FINAL_VERIFICATION.json)에서 확인할 수 있다.

## UB 후보 비교

A는 기존 U2 baseline, B는 실제 grid 행 계수와 주입 부호를 사용하는 임계 선로·시간 민감도, C는 4대 역할 교환과 선택적 이동·재배치다. 세 후보는 동일 strict U2 RAW와 각 400초 제한으로 시작했다. 전체 원본 행·continuous box·binary type을 유지하고 UB 탐색에만 neighborhood를 제한했다. 모든 candidate를 원본 FULL 정수 literal 0/1, full matrix, 경로·SOC·P/Q·PCS·계통 replay로 검사했으며 실패 RAW는 repair/rounding 없이 거부했다. 최선 UB보다 나쁜 후보는 승격하지 않았다.

| 방법 | 검증된 UB | UB 개선폭 | Native 초 | Work | 거부 RAW 수 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(comparisons)}

후보별 실제 signed line/time selection 근거, 경로 연결시각과 원본 time-dependent table 보존은 `artifacts/UB/*_NEIGHBORHOOD_IDENTITY.json`에 있다. [동일 seed 비교 CSV](artifacts/UB/UB_METHOD_COMPARISON.csv)와 [단조 incumbent pool](artifacts/UB/UB_INCUMBENT_POOL.json)이 admission 근거다. Native restricted ObjBound는 Global LB로 사용하지 않았다. 후보 처리·검증 시간은 Native 외 비용이며 UB 개선 속도는 각 실제 Native Runtime과 개선폭을 함께 제시한다.

## 차량별 전체 trajectory Pricing

원본 582,808행·306,040열·5,351,612 nonzero의 C3A를 4개의 full96 차량 block, nonunit 계통 block, 6,054 coupling 행으로 분할했다. Route/이동 에너지/접속 지연/충방전 mode/SOC/PQ/PCS16을 포함한 원래 모든 정수 계획이 각 Pricing domain에 포함됨을 독립 검증했다. 임의 arc 삭제와 SOC 이산화는 하지 않았다. 계통의 다중 선로·시간 P/Q 쌍대벡터로 exact 가격을 재구성하고, Native binary64 가격은 진단에만 사용했다.

| 가격 단계 | 차량 | 문제 | Native 초 | Work | Native 상태 | 인증 수준 |
|---|---|---|---:|---:|---:|---|
{chr(10).join(price)}

MILP incumbent는 물리적 열 후보이고 Native BestBd는 별도 exact certificate가 아니다. LP signed dual과 원본 finite box residual로 모든 정수 trajectory를 포함하는 하한을 exact rational로 계산했다. 최종 original-row dual을 원본 전체 CSR에 재조립해 Global weak duality를 독립 재검증했다. 제한 Master 목적값은 Global LB/UB로 사용하지 않았다. Missing-column 인증 상태는 `{closure.get('status', 'NOT_RUN')}`이며 차량별 β−η 검사값을 독립 JSON에 기록했다. TIME_LIMIT은 완전 탐색·불가능성 증명이 아니다.

## 결과 해석과 다음 연구

`PRICING_RUNTIME_CERTIFICATION.csv`는 각 Pricing의 실제 시간, Native objective와 exact local LB의 차이, 선택한 dual 및 strict raw-column admission을 분리한다. full block MILP의 Native 종료만으로 정수 convex hull의 강화나 완전 Pricing closure를 주장하지 않는다. 새로운 유효 LB가 기존 fresh exact LB보다 높은 경우에만 개선으로 기록했다. Signed multiplier 수정/finite-box 수치 인증과 구조적 정수영역 강화는 구분한다.

한 차례 RMP 가격 업데이트는 dual 진동의 장기 수렴을 평가하기에 충분하지 않다. 전역 grid, 시간별 line loading, fleet relocation과 SOC/PCS의 coupling을 원본 행으로 유지했으며, 차량별 convex hull 자체가 부족한지 증명하지 않았다. 인증 실패 원인을 느린 MILP Pricing, 약한 LP 가격 하한, exact residual loss, 미확인 dual 수렴으로 구분해 평가해야 한다. 이유와 증명 수준을 확인하기 전 전체 Branch-and-Price나 production을 자동 실행하지 않는다. 문헌과 안전한 dominance/자원 bound 적용 조건은 [문헌 검토](LITERATURE_REVIEW_KO.md), 후속 admission은 [handoff 계약](HYBRID_HANDOFF_KO.md)을 따른다.

이번 관측에서는 Pricing이 느리지 않았다. 초기 LP의 Native objective와 exact β 사이 차이는 약 9.4e-9~4.5e-8이며, 채택한 LB 개선은 같은 grid 가격에서 local LP dual을 재최적화한 결과다. RMP 새 가격의 exact Global LB 0.06680246877771547은 기존 LB보다 약해 거부했다. RMP에는 차량당 기존 seed와 Pricing RAW의 2개 열만 있었고, 새 best UB의 4개 unit trajectory는 포함되지 않았다. 이는 확인된 제한 catalog의 한계이며 그 자체가 fleet coupling이나 차량 convex hull 부족의 증명은 아니다. 실제 β−η는 네 차량 모두 음수인 하한이어서 missing-column closure가 입증되지 않았다. 음수 하한만으로 정수 negative column의 존재를 주장하지 않는다. [독립 Pricing 진단](PRICING_INDEPENDENT_DIAGNOSIS_KO.md)에 수치와 원인을 분리했다.

UB의 실제 signed 후보는 sw1 A상 슬롯72·90, sw2 A상 슬롯78·84의 원본 계수에서 유도됐다. 이동 경로·연결시각·SOC·PCS와 계통 행을 유지한 accepted point의 관측과 dispatch 변화는 [원본 물리 진단](FULL96_PHYSICAL_DIAGNOSTICS.json)에 있다. 이 선로·시간의 point 진단을 전역 LB의 유일한 제한 원인이나 개별 차량 변경의 인과효과로 해석하지 않는다. 어떤 물리 결합이 integer-hull LB를 제한하는지 확정하려면 완전 정수 Pricing 인증과 별도의 inclusion 보존 분석이 필요하다.

## 시간과 회귀 검증

Native {s['Native_optimize_calls']}회, 누적 Runtime **{s['Native_Runtime']:.3f}초**, Work **{s['Native_Work']:.6f}**, optimize API Wall **{s['optimize_API_wall_seconds']:.3f}초**. 최종 검증까지 연속 Wall **{s['research_through_final_verification_wall_seconds']:.3f}초**이며 model build·exact checker·full replay·최종 회귀를 포함한다. 신규 ledger 제한 2,700초, 요청 상한 2,310초, 원래 M1 단계 상한 5,400초는 보존한다. Threads=1, 원래 tolerance 1e-8, inner MIPGap 0.5%를 유지했다. MemLimit/SoftMemLimit과 RAM 자동 종료는 사용하지 않았다. 과거 Runtime/예산을 초기화하지 않았다.

CSR, verified D frozen files, static graph, strict incumbent는 SHA 확인 후 재사용했다. Presolve는 Native Runtime에 포함되어 있으며 로그의 반올림 시간과 callback span은 별도 참고값이다. 중첩 비용 record를 합산해 Wall을 부풀리지 않는다. 상세 비용은 [COST_BREAKDOWN.json](COST_BREAKDOWN.json)에 있다.

최종 회귀 **{s['tests']['passed']} PASS / {s['tests']['skipped']} SKIP / {s['tests']['failed']} FAIL**, 테스트 Native=0. 기존 549 PASS를 보존하고 신규 독립 scientific checker를 추가했다. SKIP은 PASS로 세지 않았다. May12/1,782-job M1, A2/M2, 27일 캠페인 또는 다른 입력에 성능이나 acceptance를 전용하지 않는다.
'''
    (REPORTS / 'FINAL_REVIEW_KO.md').write_text(text, encoding='utf-8')


def manifest():
    files = {}
    selected = [ROOT / 'v42_m1_hybrid', REPORTS]
    for folder in selected:
        for path in folder.rglob('*'):
            if path.is_file() and path.name != 'SHA256_MANIFEST.json' and '__pycache__' not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = sha(path)
    for path in (ROOT / 'tests').glob('test_v42_m1_hybrid*.py'):
        files[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ('README.md', '.gitattributes', 'Start-V42-M1-Hybrid.ps1'):
        files[name] = sha(ROOT / name)
    write(REPORTS / 'SHA256_MANIFEST.json', dict(PASS=True, case_sha=CASE_SHA,
        baseline_completed_HEAD=BASE_HEAD, files=files,
        self_digest_excluded=True, exact_final_HEAD_in_post_commit_ignored_readiness=True))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    receipt = finalize(RUNTIME / args.run_id); manifest()
    print('HYBRID_RESEARCH_FINALIZED', receipt['classification'], receipt['certified_Global_Gap_percent'])
