"""Supervisor closure from independent receipts, with unchanged Native ledger."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.partial_canary import resource_snapshot
from v42_integration.unified_contract import digest
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
BASE='89b4ee6b63ca7847dd6f2cbd2720052f66949d39'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    target=OUT/'FINAL_C0_C1_REVIEW_KO.md'
    if target.exists():raise FileExistsError('FINAL_REVIEW_MUST_NOT_OVERWRITE')
    baseline=read(OUT/'BASELINE_SOURCE_AND_CASE_AUDIT.json')
    prior=read(OUT/'PRIOR_ARTIFACT_BYTE_SNAPSHOT.json')
    for r in prior['files']:
        current=subprocess.check_output(['git','hash-object','--no-filters',r['path']],cwd=ROOT,text=True).strip()
        assert current==r['git_blob'],r['path']
    ledger=OUT.parent/'UNIFIED_NATIVE_RUNTIME_LEDGER.json';after=file_record(ledger)
    assert after==baseline['native_before']
    budget=read(ledger);before=read(OUT/'NATIVE_LEDGER_BEFORE.json');assert budget==before
    source13=read(OUT/'D0_A1_NATIVE0_REGENERATION_PROOF.json')['exact_source13_preservation']
    assert all(file_record(r['path'])==r for r in source13)
    executed=read(OUT/'ISOLATED_EXECUTED_CODE_SOURCE.json')
    assert all(file_record(r['path'])==r for r in executed['files'])
    certificate=read(OUT/'C0_C1_COMMON_INPUT_CERTIFICATE.json');assert certificate['status']=='PASS'
    measured=read(OUT/'INDEPENDENT_MEASURED_COMPARISON.json')
    fresh=read(OUT/'C0_C1_FRESH_AC_STATUS.json');regression=read(OUT/'REGRESSION_FINAL/REGRESSION_RESULTS.json')
    assert not fresh['blocked_native_attempts']
    assert not read(OUT/'COMPARISON_COMPLETE.json')['blocked_native_attempts']
    assert regression['status']=='PASS' and regression['baseline_IDs_preserved']==624
    assert regression['Gurobi_Native_calls']==0 and not regression['blocked_attempts']
    resource_before=read(OUT/'RESOURCE_BEFORE.json');resource_after=resource_snapshot()
    _write(OUT/'RESOURCE_AFTER.json',resource_after)
    old_worker=next(r for r in resource_before['workers'] if r['ProcessId']==35740)
    new_worker=next(r for r in resource_after['workers'] if r['ProcessId']==35740)
    assert old_worker==new_worker
    native=dict(status='PASS',canonical_ledger_byte_identical=True,canonical_ledger_before=baseline['native_before'],
        canonical_ledger_after=after,used_seconds=budget['conservative_solve_seconds'],limit_seconds=budget['limit_seconds'],
        remaining_seconds=budget['limit_seconds']-budget['conservative_solve_seconds'],return_reserve_seconds=30.,
        usable_after_reserve_seconds=budget['limit_seconds']-budget['conservative_solve_seconds']-30.,
        new_Gurobi_optimize_calls=0,new_Gurobi_presolve_calls=0,new_Gurobi_IIS_calls=0,
        Actual_global_MILP_calls=0,canonical_call_count=len(budget['calls']),
        AC_wall_seconds={k:v.get('AC_wall_seconds') for k,v in fresh['variants'].items()},
        Fresh_wall_separate_from_Gurobi=True,baseline_native0_tests=624,total_tests=regression['total'],
        resource_before=file_record(OUT/'RESOURCE_BEFORE.json'),resource_after=file_record(OUT/'RESOURCE_AFTER.json'),
        external_worker_preserved=new_worker,external_worker_stopped_or_signaled=False,
        original_Source13_byte_identical=True,prior_research_reports_byte_identical=len(prior['files']),
        other_session_budgets_used=False,May31_or_IEEE8500_executed=False,additional_solver_budget_approved=False)
    native['ledger_sha']=digest(native);_write(OUT/'NATIVE_AND_RESOURCE_LEDGER.json',native)
    c0=measured['variants']['C0'];c1=measured['variants']['C1'];f0=c0['Fresh'];f1=c1['Fresh']
    affine=read(OUT/'AFFINE_FRESH_AUTHORITY_AND_DIFFERENCE_AUDIT.json')
    unknown_reject=c0['Unknown_rejection_UIDs_by_reason']
    peak=lambda f:f"{100*f['max_phase_line_loading']:.6f}%"
    latency=lambda c:f"{c['controller_P50_seconds']:.6f}/{c['controller_P95_seconds']:.6f}/{c['controller_max_seconds']:.6f}초"
    gate=dict(Gate1='PASS',Gate2='PASS',Gate3='PASS_MEASURED_RESULTS_AND_VIOLATIONS_REPORTED',Gate4='PASS_PREPARATION_AND_HOLD',
        Fresh_physical_status={k:v['Fresh']['status'] for k,v in measured['variants'].items()},
        actual_Unknown_ranking_performance='NOT_DEMONSTRATED',Native_calls=0,
        online_affine_admission_oracle_realized_accuracy='NOT_CERTIFIED_LARGE_VOLTAGE_DISCREPANCY',
        Full96='NOT_RUN',new_D0_joint_optimization='NOT_RUN',same_case_full_global_optimality='NOT_CERTIFIED')
    _write(OUT/'FINAL_DIAGNOSTIC_GATES.json',gate)
    text=f'''# PR223 고정 M2 조건의 May01 16슬롯 Unknown C0/C1 독립 검증

00:00–04:00(FIXED AEST UTC+10, 900초×16) 실제 Replay와 새 Fresh AC 평가를 완료했다. Unknown {c0['Unknown_submitted']} UID가 도착했고, 제어 시각에 도달한 {c0['Unknown_unique_start_eligible_UIDs']} UID 중 실행은 양군 {c0['Unknown_started']}건이다. 목적지 차이 {measured['changed_site_UIDs']}건, Changed GPUh {measured['changed_compute_GPUh']}, C1의 실제 성능 개선은 **NOT_DEMONSTRATED**다. 합법 후보가 없어 실제 데이터에서 Ranking 선택 효과를 식별하지 못했다.

Gate1/2는 PASS다. Gate3는 결과 계산·동일 물리 Authority·위반 공개를 완료했다는 판정이며, 전기적 무위반 여부는 Fresh의 별도 판정 **C0 {f0['status']} / C1 {f1['status']}**를 따른다. Frozen affine 전압 검사와 Fresh 사이의 최대 0.354931 pu 차이 때문에 **온라인 전기적 입장 판정의 realized 정확성은 NOT_CERTIFIED**다. 초기 상태를 재배치하거나 제약을 완화하지 않았다. C_REF의 과거 성공 수치를 C0/C1에 이전하지 않았다.

| 실측 지표 | C0 | C1 | C1−C0 |
|---|---:|---:|---:|
| 도착 Unknown UID | {c0['Unknown_submitted']} | {c1['Unknown_submitted']} | 0 |
| Start Eligibility UID | {c0['Unknown_unique_start_eligible_UIDs']} | {c1['Unknown_unique_start_eligible_UIDs']} | 0 |
| 실행 Unknown UID | {c0['Unknown_started']} | {c1['Unknown_started']} | 0 |
| 초기 Running 외 추가 Known 시작 UID | {c0['additional_Known_started']} | {c1['additional_Known_started']} | 0 |
| 완료 UID / Carry UID | {c0['completed_jobs']} / {c0['carryout_jobs']} | {c1['completed_jobs']} / {c1['carryout_jobs']} | 0 / 0 |
| 전체 창 내 Compute GPUh | {c0['compute_GPUh']:.9f} | {c1['compute_GPUh']:.9f} | {measured['C1_minus_C0']['compute_GPUh']:.9f} |
| 창 내 완료 Job의 창 내 Compute GPUh | {c0['completed_jobs_in_window_compute_GPUh']:.9f} | {c1['completed_jobs_in_window_compute_GPUh']:.9f} | 0 |
| PCC P 에너지 kWh | {c0['PCC_kWh']:.9f} | {c1['PCC_kWh']:.9f} | 0 |
| PCC Q 에너지 kvarh | {c0['PCC_kvarh']:.9f} | {c1['PCC_kvarh']:.9f} | 0 |
| Fresh 최대 선로·상 부하율 | {peak(f0)} | {peak(f1)} | {measured['C1_minus_C0']['Fresh_max_phase_line_loading']:.9f} pu |
| Fresh 16슬롯별 최대 부하율의 시간평균 | {100*f0['time_mean_of_16_slot_max_phase_line_loading']:.6f}% | {100*f1['time_mean_of_16_slot_max_phase_line_loading']:.6f}% | 0 |
| Fresh 전압 최저/최고 pu | {f0['voltage_min_pu']:.9f} / {f0['voltage_max_pu']:.9f} | {f1['voltage_min_pu']:.9f} / {f1['voltage_max_pu']:.9f} | 0 / 0 |
| 전체 Controller Tick P50/P95/Max | {latency(c0)} | {latency(c1)} | 실행시간 차이는 성능 인과 효과로 해석하지 않음 |

## 최종 20개 질문에 대한 답

1. **초기 상태:** 원본 byte SHA `{baseline['initial_record']['sha256']}`, semantic SHA `{baseline['initial_semantic_sha']}`를 확인했다. 324 Running/472 GPU/1,300 Pending, 12 AIDC/780 GPU, 원래 사이트·Elapsed를 보존했다. 이전 완료 44 UID를 활성 집합으로 복귀시키지 않았다. 이 배치는 승인된 모델 초기 상태이며 Kestrel에서 관측한 실제 사이트라는 주장은 하지 않는다.

2. **Known 실행 구분:** byte 고정 PR223 원본 `_known_decision`/`_reference_decision`의 Reference Queue/Fallback을 사용했다. 과거 6시간 최적 명령의 정확한 실행이나 새 D0 명령을 사용했다고 주장하지 않는다. Planning 원본과 Actual 교정 원장은 분리했다.

3. **동일 최초 입력:** PASS. 초기 공개 Known 1,624 UID(기존 계보 Unknown 78 재분류 포함), May01 미래 Unknown 696 UID, 전체 활성 모집단 2,320 UID다. 이 구간 실제 도착은 217 UID이며 나머지 479 UID는 아직 제출 시각이 오지 않았다. CC4/Runtime/실제 사건·완료 Source/C1/GPU·Rack·WAN/QoS/Known 규칙/24사이트 M2/계통·날씨·수요·PV·900초 시계가 같다. 상세 SHA는 `C0_C1_COMMON_INPUT_CERTIFICATE.json`에 있다.

4. **후보와 Ranking:** 동일 public 상태의 {certificate['same_state_equal_candidate_events']}개 후보 평가에서 후보 SHA가 일치했다. 양군은 같은 후보 함수와 현재 hard guard를 쓰며, C0는 Reference/사이트 순서, C1은 공개 Q50 서비스가 겹치는 모든 관련 슬롯·선로·상의 signed 최대 부하율을 최소화한다. 미래 예측은 동결 forecast와 공개 nominal remaining의 soft projection이며 미래 Known 예약 veto를 추가하지 않았다. Q50 초과·96슬롯 밖 tail은 보장하지 않는다. 여러 슬롯 반례 테스트는 C0 A/C1 B 선택을 확인했지만 실제 Source의 합법 후보는 0이다.

5. **Unknown 도착:** 각 군 {c0['Unknown_submitted']} UID. 최초 UID 8714697 제출은 00:16:06, 최초 합법 제어는 00:30이다. 강제 00:00 Unknown은 없다. {c0['Unknown_unique_start_eligible_UIDs']} UID가 04시 이전 제어 tick에 도달했고 마지막 슬롯의 20 UID는 다음 tick이 평가 구간 밖이다.

6. **실행 Job:** Unknown {c0['Unknown_started']} UID. 초기 Running 324 외 Known {c0['additional_Known_started']} UID가 시작했다. 전체 {c0['all_started_including_initial']} UID가 실행 이력이 있으며 {c0['completed_jobs']} 완료/{c0['Known_running']} Running/{c0['Known_pending']} Known Pending/217 Unknown Pending이다. 전체 창 내 Compute {c0['compute_GPUh']:.9f} GPUh와 완료 Job의 창 내 Compute {c0['completed_jobs_in_window_compute_GPUh']:.9f} GPUh를 구분한다.

7. **C1 목적지 변경:** C0 대비 {measured['changed_site_UIDs']} UID다. Queue의 `None` 목적지를 가상 배치로 세지 않았다.

8. **Changed GPUh:** {measured['changed_compute_GPUh']} GPUh. 실제 시작/완료 구간 기준이며 계획 GPUh를 복사하지 않았다.

9. **Known 실제 충돌과 교정:** {c0['Known_actual_GPU_conflict_UIDs']} UID에서 {c0['Known_conflict_event_attempts']}회 현재 GPU 충돌 검사·교정 시도가 기록됐다. 합법 준비 근거 부족 등으로 교정 명령 {c0['Known_corrective_commands']}건/교정 후 실제 시작 {c0['Known_corrective_actual_starts']}건이다. 전송·준비 시간과 추가 계통 영향은 실행 0건이므로 N/A/0이며, 모든 UID·시각·원사이트·후보 거부는 `KNOWN_CORRECTIVE_EVENTS.csv`에 있다. Reference latest-start 초과는 전체 {c0['QoS_latest_start_excess_UIDs']} UID, 최대 {c0['QoS_max_latest_start_excess_seconds']:.0f}초다. 이는 기존 대기와 Reference 비교 위험이며 Source에서 확인된 고객 SLA 위반 판정으로 바꾸지 않는다. Running 강제 중단은 없다.

10. **Queue 원인:** Unknown 거부 UID 수는 `{json.dumps(unknown_reject,ensure_ascii=False,sort_keys=True)}`다. 같은 UID가 여러 후보·시각에서 거부되므로 합산하지 않는다. Raw 호환 사이트와 권한·현재 GPU·전기를 모두 통과한 합법 사이트를 구분한다. 원사이트의 frozen affine 전압 검사와 대체 사이트의 Source/데이터/WAN 권한 부족, 일부 용량 부족이 함께 작용했다. Known 교정 거부 후보 횟수는 `{json.dumps(c0['Known_corrective_rejection_candidate_evaluations'],sort_keys=True)}`다. Known Pending {c0['Known_pending']}와 Unknown Queue {c0['Unknown_queued']}는 삭제하지 않고 Carry했다.

11. **물리 제약:** GPU 위반/Job 삭제/Global MILP 모두 0이며 Actual GPU로 Original C1을 독립 재계산해 P/Q 배열 일치를 확인했다. Frozen affine에서는 {c0['affine']['affine_violations']}개 슬롯별 위반 종류 기록이 있어 전체 affine 무위반을 주장하지 않는다. 실제 Fresh 위반은 전압 {f0['voltage_violation_cells']}, 선로 전류 {f0['line_current_violation_cells']}, 변압기 전류 {f0['transformer_current_violation_cells']}, 변압기 kVA {f0['transformer_kVA_violation_cells']} cell이며 C1도 동일하다. Fresh를 사용해 이미 거부된 Job을 소급 입장시키지 않았다.

12. **미래 정보 차단:** Simulator의 private Environment만 실제 Runtime/Completion을 읽는다. Controller future duration/completion read는 양군 0이고, Source 필드 주입 차단 테스트가 있다. 현재 관측 날씨만 current C1 callback에 전달하고 미래 ranking은 동결 forecast를 쓴다. Forecast는 실제 도착 Unknown UID당 한 번, 초기 Known에는 0회 차감했다.

13. **16슬롯 최대 부하율:** Fresh C0 {peak(f0)}, C1 {peak(f1)}다. 별도 frozen affine 값은 양군 {100*c0['affine']['affine_actual_max_phase_line_loading']:.6f}%다. 서로 다른 상태의 평가를 같은 실측값으로 표시하지 않는다.

14. **Critical Line/Phase/Slot:** Fresh는 양군 `{f0['critical_line']}`, phase {f0['critical_phase']}, terminal {f0['critical_terminal']}, 0-based slot {f0['critical_slot']}, `{f0['critical_interval_start_fixed_AEST']}`–`{f0['critical_interval_end_fixed_AEST']}`다. Affine는 `{c0['affine']['affine_critical_line']}`/phase `{c0['affine']['affine_critical_phase']}`/slot {c0['affine']['affine_critical_slot']}다.

15. **실제 개선:** 입증되지 않았다. Δ사이트/Compute GPUh/PCC P/Q/선로 부하율은 0이다. 모든 Unknown이 공통 후보 guard에서 거절되어 Ranking 경쟁이 발생하지 않았다. Fixture에서 작동한 점을 실제 성능 개선으로 이전하지 않는다.

16. **11-SVR Fresh AC:** 양군 새 16슬롯 평가 {f0['status']}/{f1['status']}. 원본 7 RegControl, 11 SVR, LDC, 자동 TIME 시계와 모든 전기적 경계를 유지했다. Fresh wall은 C0 {f0['AC_wall_seconds']:.6f}초/C1 {f1['AC_wall_seconds']:.6f}초로 Gurobi Native와 별도다. Affine는 Actual AIDC P/Q와 고정 M2를 넣었지만 배경·LDC secant는 원래 forecast 상태다. Certificate는 local/unsaturated 유효범위이며 Actual 입력을 읽지 않았다. 최악 지점은 slot12 `idc_idc11_pcc.1`: affine 0.645841133 pu/Fresh 1.000771905 pu, 최대 정렬 전압 차이 0.354930772 pu다. 최대 control−anchor 차이는 392.314112이며 단위는 각 control의 kW/kvar다. 실제 forecast−realized 수요·PV 차이와 슬롯별 SVR/clock SHA를 `AFFINE_FRESH_AUTHORITY_AND_DIFFERENCE_AUDIT.json`에 남겼다. 비선형 오차·배경 차이·tap 동작의 개별 인과 기여는 분리 인증하지 않았다. 이 큰 차이는 미해결 검증 문제이며 현재 입장 판정이 realized 물리에 정확하다고 인증하지 않는다.

17. **D0 A1 결함 판정:** 아직 판단 불가다. 동일 Source/Case/Matrix/Domain/Objective가 재생성됐다. 정적 box 필요조건에서 직접 모순은 없었지만 feasibility 증명은 아니다. 25초 요청/26.238초 실측 Pilot는 presolve 12.97초 후 Root barrier 도중 TIME_LIMIT/SolCount0이므로 INFEASIBLE이나 단순 시간 부족 확정으로 해석하지 않는다.

18. **다음 Native 예산:** 모델 변경 없는 P1 120초와 반환 30초를 위한 최소 총 한도 468.681초, overshoot buffer를 고려한 권고 총 한도 480초(현행보다 +120초)다. 정수해 성공 보장이 아니며 P2/M1/A2/M2 예산은 별도다. 현재 Native `{budget['conservative_solve_seconds']:.3f}/{budget['limit_seconds']:.0f}`, 잔여 41.319초/반환 여유 30초를 보존했고 추가 실행은 HOLD다.

19. **MESS 보존:** Adaptive Beam→4-MESS Joint MILP→Original FULL→Incumbent Registry와 K48 코어를 변경하지 않았다. 고정 PR223 M2의 경로·P/Q·SOC와 96개 실행 명령을 확인했으며, IDC의 MESS P/Q가 0이어도 비영 STA 주입을 포함한 24사이트 전체를 유지했다. S1 5.0218%와 별도 4×24 Case 13.8647%를 혼합하지 않았다.

20. **Full96 잔여 조건:** 이 진단의 Full96는 NOT_RUN이다. 합법 Source·데이터·WAN 준비 근거와 실제 대체 후보가 생기는지, affine forecast guard와 realized AC 차이를 원본 Authority 안에서 어떻게 다룰지 먼저 검토해야 한다. 96슬롯 전체 사건·Carry·QoS·GPU/PQ와 새 Fresh96 평가가 필요하다. 새 D0 공동 최적화는 추가 예산 승인 후 P1 수용→P2→M1/A2/M2의 같은 Case 최종 결과가 별도로 있어야 한다. May31/IEEE8500는 실행하지 않았다.

## 보존·검증·전달

기존 {len(prior['files'])}개 연구 산출물과 D0 Source13개를 byte 동일하게 재확인했다. 기존 Source/Raw/624개 테스트의 기대값은 변경하지 않았다. 최종 회귀 **{regression['total']} PASS(624 기존+{regression['new_tests']} 신규)**, failures/skips/신규 Native 호출 0이다. 외부 Worker PID35740은 같은 명령으로 실행 중이며 종료·신호를 보내지 않았다.

초기 준비 오류 두 건과 계측 전 Replay, 현재 슬롯만 평가하던 Replay를 별도 폴더에 Source bytes와 함께 보존했다. 최종 증거는 현재 C0/C1 폴더와 `ISOLATED_EXECUTED_CODE_SOURCE.json`을 따른다. 큰 새 Raw 원장은 원본을 로컬에 그대로 두고 deterministic gzip으로 전달하며 `LOSSLESS_EVIDENCE_DELIVERY.json`의 원본/압축 SHA로 byte 복원을 검증한다. 과거 Raw를 재작성하지 않았다.

필수 비교 CSV 중 `C0_C1_GRID_LOADING_COMPARISON.csv`는 frozen affine 평가이고, 새 실제 AC 값은 `C0_C1_FRESH_GRID_LOADING_COMPARISON.csv`다. `INDEPENDENT_MEASURED_COMPARISON.json`은 단위·UID/후보 수·QoS 위험·C1−C0를 구분한 통합 수치다. QoS Source의 미확인 속성이나 Queue 지연을 SLA 보장으로 바꾸지 않았다.
'''
    target.write_text(text,encoding='utf8')
    print(json.dumps(dict(status='COMPLETE_DIAGNOSTIC',gates=gate,tests=regression['total'],native=native['used_seconds'],
        prior_reports_byte_identical=len(prior['files']),report=str(target)),indent=2))


if __name__=='__main__':main()
