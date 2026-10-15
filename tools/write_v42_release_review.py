"""Close RC01 with measured gates and a candidate SHA, never a release PASS."""
from pathlib import Path
import csv
import json
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
ACT=OUT/'AIDC/REPLAY02'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def main():
    target=OUT/'FINAL_REVIEW_KO.md'
    if target.exists():raise FileExistsError('RELEASE_REVIEW_MUST_NOT_OVERWRITE')
    audit=read(ACT/'INDEPENDENT_ACTUAL_CERTIFICATE.json');assert audit['status']=='PASS'
    fresh=read(ACT/'OFFLINE_FRESH_16_STATUS.json')
    current_crosscheck=read(ACT/'CURRENT_SAME_INPUT_AC_CROSSCHECK.json')
    assert current_crosscheck['status']=='PASS_SAME_CURRENT_INPUT_ORIGINAL_AC'
    trajectory=read(ACT/'PHYSICAL_GATE_AND_REJECTION_SUMMARY.json')
    regression=read(OUT/'REGRESSION/RESULTS.json');assert regression['status']=='PASS'
    p1=read(OUT/'A1_P1_120/INDEPENDENT_P1_ACCEPTANCE.json')
    exact=read(OUT/'A1_P1_120/PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json')
    common=read(ACT/'COMMON_RUN_INPUTS.json')
    preservation=read(OUT/'MESS/FINAL/MESS_OFFICIAL_ALGORITHM_PRESERVATION.json')
    byteproof=read(OUT/'MESS/FINAL/FROZEN_SOURCE_BYTE_PROOF.json')
    assert all(x['status']=='PASS' for x in byteproof['after']['files'])
    for x in byteproof['after']['files']:
        r=x['current']
        if r['exists']:
            now=file_record(r['path']);assert all(now[k]==r[k] for k in ('sha256','bytes'))
    original_solver=read(OUT/'A1_P1_120/A1_P1_RESULT.json')['solver_policy']
    code=sorted({str(p) for pattern in ('v42_integration/release_*.py','v42_integration/current_ac_admission.py',
        'tools/*v42_release*.py','tests/test_v42_release*.py') for p in ROOT.glob(pattern)})
    core=[x['current'] for x in byteproof['after']['files'] if x['current']['exists']]
    science=dict(schema='RC01_BASIC_INITIAL_STAY_OPTIONAL_PENDING_PRESITE_SCIENCE_V1',
        method='UNCHANGED_WORKLOAD_SCHEDULING_BASIC_REFERENCE_SITE_THEN_OPTIONAL_AUTHORIZED_PENDING_PRESITE',
        difference='OPTIONAL_PENDING_PRESITE_ONLY',current_safety='CAUSAL_ORIGINAL_11SVR_7REGCONTROL_CANDIDATE_AC',
        ranking='PUBLIC_Q50_CURRENT_EXOGENOUS_HOLD_COUNTERFACTUAL_AC_ALL_PHASE_LINES',
        real_future_access=False,additional_intentional_delay_seconds=0,migration='HOLD',
        source_files=common['code_files'])
    science['science_sha']=digest(science)
    _write(OUT/'NEW_SCIENCE_CASE_CERTIFICATE.json',dict(science=science,
        Actual_diagnostic_case_sha=common['release_case_sha'],Actual_case_inputs=file_record(ACT/'COMMON_RUN_INPUTS.json'),
        shared_Raw_inputs=audit['shared_raw_inputs'],private_Runtime_source=audit['private_Runtime_source'],
        historical_source_bindings_are_not_new_science_identity=True,
        D0_P1_science_sha=exact['identity']['science_sha'],D0_P1_case_sha=exact['identity']['case_sha'],
        D0_P1_stage_case_sha=exact['stage_case_sha'],D0_P1_not_used_as_diagnostic_Known_schedule=True))
    freeze=dict(schema='RC01_REVIEWABLE_SOURCE_CANDIDATE_V1',state='FREEZE_CANDIDATE_PENDING_INTEGRATED_VALIDATION',
        final_Release_Freeze=False,base_git='490ff3ef7821705fc82c3823242d79093eb480b9',
        files=[file_record(p) for p in code],preserved_original_core=core,
        Actual_science_sha=science['science_sha'],Actual_diagnostic_case_sha=common['release_case_sha'],
        policies={c:read(ACT/c/'FROZEN_POLICY.json')['policy_sha'] for c in ('C0','C1')},
        D0_identity=exact['identity'],D0_stage_case_sha=exact['stage_case_sha'],D0_Source13=exact['Source13'],
        original_solver_policy=original_solver,
        cannot_promote_before='ASOF_ALL_SUBSTEP_PHYSICAL_PASS_AND_NEW_SAME_CASE_A1_P2_M1_A2_M2_ACTUAL96_FRESH_AND_REPRESENTATIVE_GATES')
    freeze['candidate_sha']=digest(freeze);_write(OUT/'SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json',freeze)
    stats={}
    for c in ('C0','C1'):
        rows=read(ACT/c/'OFFLINE_FRESH_16/FRESH_PHYSICAL_SLOTS.json')
        worst=max((dict(r,slot=row['slot']) for row in rows for r in row['physical']['currents']
            if r['element'].lower().startswith('line.')),key=lambda r:r['loading_pu'])
        stats[c]=dict(max_phase_line_loading=worst['loading_pu'],worst_line=worst,
            min_voltage_pu=min(r['physical']['voltage_min_pu'] for r in rows),
            max_voltage_pu=max(r['physical']['voltage_max_pu'] for r in rows),
            physical_PASS=fresh['variants'][c]['status']=='PASS',**audit['variants'][c])
        stats[c].update(ASOF_substep_max_phase_line_loading=trajectory['asof_max_phase_line_loading'],
            ASOF_substep_min_voltage_pu=trajectory['asof_voltage_min_pu'],ASOF_substep_max_voltage_pu=trajectory['asof_voltage_max_pu'],
            ASOF_violating_substeps=trajectory['asof_violating_substeps'])
    improvement=stats['C0']['max_phase_line_loading']-stats['C1']['max_phase_line_loading']
    canary_pass=fresh['status']=='PASS' and all(r['controller_900_seconds_PASS'] and r['current_candidate_resource_not_certified']==0
        and r['observed_prefix_physical_fail_receipts']==0 for r in stats.values())
    blockers=['A1_ORIGINAL_P2_M1_A2_M2_K48_NOT_RUN_AND_NOT_AUTHORIZED',
        'NEW_D0_SAME_CASE_ACTUAL_FULL96_AND_FRESH96_NOT_RUN',
        'MAY02_MAY10_MAY12_APPROVED_D0_0000_INITIAL_AUTHORITIES_NOT_FOUND_IN_AUDITED_TREES',
        'DATE_GENERALIZATION_AND_PRODUCTION_STAGE_BUDGET_ADAPTERS_NOT_CERTIFIED',
        'MAY31_FULL_CAMPAIGN_BUDGET_AND_LAUNCH_APPROVAL_NOT_GRANTED']
    if not canary_pass:blockers.insert(0,'ASOF_FIRST16_PHYSICAL_VOLTAGE_FAIL_32_OF_145_NATIVE_SUBSTEPS')
    gates=dict(status='CAMPAIGN_BLOCKED_WITH_EXACT_REASONS',Worker=1,Threads=1,automatic_start=False,
        Gate1_code_rights='PASS_NATIVE0_REGRESSION_AND_INDEPENDENT_FIRST16_AUDIT',
        Gate2_first_event_first16='PASS_DIAGNOSTIC_ONLY' if canary_pass else 'FAIL_PHYSICAL_ASOF_SUBSTEP_TRAJECTORY',
        Gate3_D0_A1_P1='PASS_P1_ONLY_P2_NOT_RUN',Gate4_integrated_May01='NOT_RUN_NOT_AUTHORIZED',
        Gate5_final_Release_Freeze='HOLD',representative_dates={d:'NOT_RUN_D0_INITIAL_AUTHORITY_MISSING' for d in ('2025-05-02','2025-05-10','2025-05-12')},
        final_release_sha=None,candidate_sha=freeze['candidate_sha'],blockers=blockers,
        offline_Fresh_scope=fresh['scope'],comparison=stats,
        same_current_input_crosscheck=file_record(ACT/'CURRENT_SAME_INPUT_AC_CROSSCHECK.json'),
        ASOF_all_native_substep_physical=file_record(ACT/'PHYSICAL_GATE_AND_REJECTION_SUMMARY.json'),
        weather_availability_scope=common['weather_availability'],
        provider_historical_selection_limit='SEE_MESS_FINAL_REPRESENTATIVE_DATE_SOURCE_INVENTORY',
        C0_minus_C1_max_phase_line_loading=improvement,
        C0_minus_C1_loading_percentage_points=improvement*100.,new_D0_joint_global_gap=None,
        unchanged_MESS_and_physics=preservation['byte_preservation_PASS'])
    _write(OUT/'RELEASE_GATES.json',gates)
    budget=read(OUT/'FINAL_PREPARATION/FOLLOWUP_NATIVE_BUDGET_PROPOSAL.json')
    _write(OUT/'SOLVER_CONTROLLER_RUNTIME_LEDGER.json',dict(old_canonical_used_seconds=p1['canonical_used_seconds'],
        old_canonical_byte_unchanged=True,new_separate_limit_seconds=180.,new_separate_used_seconds=p1['Native_seconds'],
        new_separate_unused_seconds=p1['new_ledger_remaining_seconds'],two_ledgers_used_seconds=p1['two_ledgers_total_used_seconds'],
        permission_calls_used=1,permission_calls_maximum=1,unused_balance_authorizes_followups=False,
        P1_wall_seconds=p1['build_solve_audit_wall_seconds'],P1_peak=p1['resource_peak'],
        AIDC={c:read(ACT/c/'ACTUAL_RESULT.json') for c in ('C0','C1')},
        AIDC_runner_resource_receipt=file_record(ACT/'RUNNER_RESOURCE_RECEIPT.json') if (ACT/'RUNNER_RESOURCE_RECEIPT.json').exists() else None,
        Actual_wall_scope='RUN_ACTUAL_AND_SOURCE_CONTEXT;EXPORT_SERIALIZATION_RECORDED_ONLY_IN_WHOLE_RUNNER_WALL',
        offline_Fresh=fresh,followup_budget=budget))
    with (OUT/'C0_C1_COMPARISON.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['variant','Unknown_arrived_UIDs','Unknown_initial_placed_UIDs','Unknown_started_UIDs','Unknown_STAY_started_UIDs',
            'Unknown_unstarted_UIDs','PreSite_candidate_UIDs','authorized_ready_alternative_UIDs','PreSite_changed_UIDs','changed_GPUh',
            'max_phase_line_loading','min_voltage_pu','max_voltage_pu','controller_P50_seconds','controller_P95_seconds','controller_max_seconds',
            'ASOF_substep_max_phase_line_loading','ASOF_substep_min_voltage_pu','ASOF_substep_max_voltage_pu','ASOF_violating_substeps',
            'Known_corrective_command_UIDs','QoS_intentional_budget_violations','QoS_latest_start_excess_UIDs']
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader()
        for c in ('C0','C1'):w.writerow(dict(variant=c,**{k:stats[c][k] for k in fields if k!='variant'}))
    a=stats['C1'];b=stats['C0']
    text=f'''판정: **CAMPAIGN_BLOCKED_WITH_EXACT_REASONS**. 기본 사이트 지정/권한 분리 및 현재 후보 AC 판정을 복구했다. 실제 first16에서는 ASOF 물리 제어 substep 145개 중32개 전압 위반이 확인돼 Canary 물리 Gate는 FAIL이다. 새 D0 통합·Full96·최종 Release Freeze는 미완료다. 기존 Draft PR230의 변경만 사용한다.

1. **최초 배치 복원:** 기존 byte-pinned Workload Scheduling/Reference 기본 사이트를 사용한다. 최초 지정에 민감도와 Pre-site 권한을 요구하지 않는다. C0/C1 기본 지정 원장이 동일하다. 새 D0 Scheduling 전체 실행은 P1까지만 완료됐다.
2. **권한 분리:** 최초 지정의 승인된 연구 계약과 다른 사이트로 이동할 때의 원본 Pre-placement 권한을 분리했다. Source release/호환성·GPU/Rack·데이터/WAN·공유 QoS·Hard window를 유지한다. 연구 권한을 고객 동의나 SLA로 표현하지 않는다.
3. **실제 배치/실행:** C0 도착 {b['Unknown_arrived_UIDs']}, 지정 {b['Unknown_initial_placed_UIDs']}, 시작 {b['Unknown_started_UIDs']}, 미시작 {b['Unknown_unstarted_UIDs']} UID. C1은 각각 {a['Unknown_arrived_UIDs']}/{a['Unknown_initial_placed_UIDs']}/{a['Unknown_started_UIDs']}/{a['Unknown_unstarted_UIDs']} UID. C1에서 제어 평가를 받은 UID는 {a['Unknown_control_evaluated_UIDs']}, 구간 끝까지 첫 제어 Tick이 오지 않은 UID는 {a['Unknown_not_yet_control_evaluated_UIDs']}다. 마지막 STAY Queue 사유는 {a['unstarted_latest_evaluated_STAY_reasons']}다. 첫 이벤트 UID 8714697의 실제 지정/Queue를 포함한다. 강제 실행하지 않았다. UID별 원인은 AIDC/REPLAY02 원장과 독립 감사에 있다.
4. **민감도 범위:** Unknown의 최초 사이트를 바꾸지 않는다. C1의 실행 전 PENDING 대체 사이트만 공개 Q50 전 구간·전체 선로/상 조건부 AC로 비교한다. 유효하지 않은 Frozen Affine는 안전 검사와 순위 모두에서 배제했다. 검증된 국소 근사 대신 동일 물리계통의 후보 AC를 사용한다. Running Migration과 추가 의도적 지연은 HOLD/0초다.
5. **실제 Pre-site:** C1 변경 {a['PreSite_changed_UIDs']} UID, {a['changed_GPUh']:.9f} GPUh. 원본 Pre-site 변경 권한 UID는 {a['PreSite_source_permission_UIDs']}, 승인·준비된 대안 {a['authorized_ready_alternative_UIDs']} UID. 기본 사이트 STAY 시작 {a['Unknown_STAY_started_UIDs']} UID. 0건이면 실데이터의 Pre-site 개선 효과는 식별하지 못한 것으로 해석한다. 합성 권한 fixture의 변경 성공은 실데이터 개선량이 아니다.
6. **Affine/Fresh:** Frozen Affine의 전역 판정 오용은 수정했지만 전체 전압 안전성은 아직 해결되지 않았다. 과거 0.645841133 대 1.000771905의 원인은 Forecast 기준 국소 AUTO Secant의 유효범위 밖 사용이다. 문제 노드는 LDC 투영 대상이 아니며 lower/upper 두 행이 같은 중앙 Secant다. FROZEN_AFFINE_ROOT_CAUSE_FINAL.json이 예비 해석을 대체한다. 현재 입장은 관측/공개 시각 ≤ now의 입력, 관측된 과거 Original C1 prefix, 현재 후보 P/Q, 원본 11-SVR/7 RegControl로 검사하며, 현재 Tick 이후 Tap은 실행하지 않는다. 기준 AC PASS로 추가 후보를 인증하지 않는다. 실제 시작 3점의 직렬 GPU/P/Q 독립 재구성 및 전체 현재 물리/SVR SHA가 일치했다. 실제 모든 START의 현재 후보 PASS도 대조했다. 그 후 과거 전체 자동제어 경로의145개 substep을 원본 엔진으로 재생하니32개에서 전압 한계를 벗어났다. 구간별 마지막 solve와 오프라인 실현 구간말 Fresh는 PASS지만 과도 위반을 대체할 수 없다.
7. **계통 효과:** 오프라인 first16 max phase-line C0={b['max_phase_line_loading']:.12f}, C1={a['max_phase_line_loading']:.12f}, 개선 C0−C1={improvement:.12f} pu ({improvement*100:.9f} percentage point). 실제 ASOF 전체 substep 최대 선로부하율은 양군 {trajectory['asof_max_phase_line_loading']:.12f}, 개선0이다. GPU/PCC P/Q/실제 시작 시각도 동일하다. 오프라인 C1 전압 {a['min_voltage_pu']:.9f}–{a['max_voltage_pu']:.9f} pu/Fresh={fresh['status']}와 별도로, ASOF 전체 경로는 {trajectory['asof_voltage_min_pu']:.9f}–{trajectory['asof_voltage_max_pu']:.9f} pu,32/145 substep·100 voltage cells FAIL이다. 선로·변압기 위반은0이다. 첫 위반은 Unknown 도착 전 native23초 mess_sta08_pcc.1=1.051492516 pu로 원본 queued AUTO event 도중 발생했다. 원본 전압밴드/Delay/Tap/SVR/MESS P/Q를 바꾸지 않았다. GPU·의도적 QoS 예산·미래 실제 Runtime/Completion 읽기 위반은0, 기존 backlog latest-start 초과는 {a['QoS_latest_start_excess_UIDs']} UID로 별도 보고한다. C1 max Tick {a['controller_max_seconds']:.6f}초, P95 {a['controller_P95_seconds']:.6f}초.
8. **새 A1→M1→A2→M2:** A1 P1만 완료. 120초 상한 한 번, SolCount={p1['SolCount']}, Objective=Bound={p1['objective']:.14f}, Gap=0, Original FULL 최대 잔차 {p1['Original_FULL_residual']:.3e}. P2/M1/A2/M2/K48는 미실행이다. A1의 Bound는 고정 MESS의 해당 A행렬 범위이며 통합 Global LB가 아니다. Actual first16은 PR223 고정 M2/Reference 진단으로 새 D0 통합 결과를 대신하지 않는다.
9. **MESS 보존:** Adaptive Beam→4-MESS Joint MILP→Original FULL→Registry, K48, 4대·24노드·96슬롯·P/Q/SOC·STAY/MOVE를 보존했다. Runtime/CC4·물리 코어 포함 103개 원본 파일 byte proof PASS. 기존 M1/M2/K48 값은 새 Case에 이전하지 않았다.
10. **May01 Full96/Fresh:** 미실행. first16은 코드/입장/GPU/PQ/시간 검사와 오프라인 구간말 Fresh가 PASS지만 ASOF 전체 물리 경로가 FAIL이다. 대표일과 May31도 미실행이다. 회귀 {regression['tests']}개 PASS, 기존640개 ID 전부 보존, Native0. 미완료/성능 프로파일과 named fixture는 실제 실행과 구분해 보존했다.
11. **동결 SHA:** 최종 Release Freeze 없음. 검토 후보 SHA `{freeze['candidate_sha']}`. 진단 Science `{science['science_sha']}`, 진단 Case `{common['release_case_sha']}`. D0 Science/Case는 NEW_SCIENCE_CASE_CERTIFICATE.json에 별도로 기록했다. 통합 Gate 전 후보를 최종 동결로 승격하지 않는다.
12. **Blocker/예산:** 원장은 기존 {p1['canonical_used_seconds']:.9f}초 + 신규 {p1['Native_seconds']:.9f}초 = {p1['two_ledgers_total_used_seconds']:.9f}초. 신규180초 잔액 {p1['new_ledger_remaining_seconds']:.9f}초는 추가 호출 권한이 아니다. 후속 A1 P2 90, M1 UB 180, M1 후 K48 180, A2 P1 120/P2 90, M2 UB 180, M2 후 K48 180 Native초의 단계별 상한안이다. 합계1020 + 반환30 + 오버슈트60 = **별도1110초 제안**, 미승인·성공 보장 없음. M1/M2 Joint 단일140초 원래 상한과 단계 누적 상한을 모두 유지한다. 실제 A1 build/solve/audit Wall {p1['build_solve_audit_wall_seconds']:.3f}초, Native {p1['Native_seconds']:.3f}초; 과거 M1/M2 Wall 약146/148초는 과거 warm Case 자료일 뿐 새 D0 예측은 미인증이다. 대표 May02/10/12 공인 D0 00:00 초기 상태가 조사 범위에서 미확인이고, 날짜별 production adapter·단계 예산 연결은 미인증이다. May01 상태 복사/Carry 혼합 없이 31일 NOT_RUN 원장을 준비했다. 추가 통합 검증, 날짜별 초기 권위, production adapter 검증과 별도31일 계산·시작 승인이 필요하다.

관측 범위: AEMO 관측 시각과 LASTCHANGED를 모두 현재 시각 이하로 제한했다. NOAA는 관측 timestamp에 따른 공개 모델이며 과거 실제 ingestion 시각을 인증한 것은 아니다. 대표일 Provider의 회고적 모델 선택/fit ingestion 미인증 한계는 MESS/FINAL 원본 감사에 유지했다.

원본 run_actual receipt의 physical_ac_status=NOT_EXECUTED는 기존 posthoc hook 상태를 유지한 것이다. 현재 후보 검사는 CURRENT_CANDIDATE_AC_LEDGER, 종료 후 Fresh는 OFFLINE_FRESH_16_STATUS와 RELEASE_GATES로 별도 결합하며 이전 receipt를 덮어쓰지 않았다.

추가 핵심 Blocker: ASOF 물리 경로의32개 전압 위반 해소·재검증이 필요하다. STA01 고정 M2 Q의 ±392.314 kvar 반전과 원본 AUTO 제어의 관계는 별도 증거에 기록했으며 단독 인과나 해결을 확정하지 않는다. 원본 물리·전압·제어 제약을 유지하므로 추가 Native 예산만으로 PASS를 보장하지 않는다.

권위 자료: RELEASE_GATES.json, SOURCE_POLICY_SCIENCE_CANDIDATE_FREEZE.json, AIDC/REPLAY02/INDEPENDENT_ACTUAL_CERTIFICATE.json, AIDC/REPLAY02/PHYSICAL_GATE_AND_REJECTION_SUMMARY.json, AIDC/REPLAY02/ASOF_SUBSTEP_PHYSICAL_DIAGNOSIS.json, AIDC/REPLAY02/OFFLINE_FRESH_16_STATUS.json, A1_P1_120/INDEPENDENT_P1_ACCEPTANCE.json, MESS/FINAL/, FINAL_PREPARATION/. 대용량 Raw의 lossless gzip 위치와 SHA/복구 검증은 COMPRESSED_EVIDENCE_MANIFEST.json에 기록한다. 기존 Raw·결과·원장은 덮어쓰거나 삭제하지 않았다.
'''
    target.write_text(text,encoding='utf8');print(json.dumps(dict(status=gates['status'],candidate_sha=freeze['candidate_sha'],canary=canary_pass),indent=2))

if __name__=='__main__':main()
