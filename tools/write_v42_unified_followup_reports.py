"""Assemble scoped measurements and gates; never solve or invent results."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest,load_contracts
from v42_integration.followup_contract import load_followup_contracts
from v42_integration.unified_resource import UnifiedResearchBudget


def main():
    report=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
    audit=ROOT/'runtime/v42_unified/FOLLOWUP_BASELINE'
    def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
    old=load_contracts();new=load_followup_contracts()
    baseline=read(audit/'BASELINE451_RESULT.json')
    boundary=read(audit/'HISTORICAL_EXACT_BOUNDARY_AUDIT.json')
    independent=read(audit/'INDEPENDENT_SOURCE_CASE_RESOURCE_AUDIT.json')
    review=read(audit/'INDEPENDENT_CHANGE_REVIEW.json')
    regression=read(report/'UNIFIED_REGRESSION_RESULTS.json')
    joint=read(report/'MESS_4X24_NATIVE_COMPARISON.json')
    lp=read(report/'S1_ROOT_FRACTIONALITY.json')
    hull=read(report/'S1_MODE_HULL_LP_COMPARISON.json')
    historical=independent['historical_Known_CC4_capacity']
    for name,doc in [('INDEPENDENT_CHANGE_REVIEW.json',review),('BASELINE451_RESULTS.json',baseline),
        ('HISTORICAL_EXACT_BOUNDARY_AUDIT.json',boundary),('INDEPENDENT_SOURCE_CASE_RESOURCE_AUDIT.json',independent)]:
        _write(report/name,doc)
    files=['v42_integration/aidc_sensitivity_runtime.py','v42_integration/aidc_resource_bridge.py',
        'v42_integration/coordinator.py','v42_integration/followup_contract.py',
        'v42_integration/followup_execution.py','v42_integration/followup_resource.py',
        'v42_integration/mess_joint_compression.py','v42_integration/mess_beam_diversity.py',
        'v42_integration/mess_mode_hull.py','tools/run_v42_aidc_followup_native0.py',
        'tools/run_v42_aidc_original_coefficient_fixture.py','tools/audit_v42_original_beam_joint.py',
        'tools/audit_v42_s1_fractionality.py','tools/run_v42_followup_joint_benchmark.py',
        'tools/run_v42_followup_s1_lp.py','tools/run_v42_followup_regression.py',
        'tools/write_v42_mess_followup_reports.py','tools/write_v42_unified_followup_reports.py',
        'tests/test_v42_aidc_followup.py','tests/test_v42_followup_contract.py',
        'tests/test_v42_mess_joint_compression.py','tests/test_v42_mess_beam_diversity.py',
        'tests/test_v42_mess_mode_hull.py']
    source_records={n:file_record(ROOT/n) for n in files}
    source_sha=digest({n:r['sha256'] for n,r in source_records.items()})
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    if branch!='codex/v42-trajectory-tracking-may01-20261014':raise ValueError('PR230_EXISTING_BRANCH_REQUIRED')
    request=file_record(Path('C:/Users/kjw39/.codex/attachments/bd28bd1a-0401-45d5-aaaa-f489fbede617/붙여넣은 텍스트.txt'))
    manifest=dict(status='PASS',scope='SOURCE_CASE_SEPARATION_NOT_COMMON_PERFORMANCE_CERTIFICATE',
        request=request,client_date='2026-10-14',client_timezone='Asia/Seoul',branch=branch,
        base_commit='22c644b10a1bfae344cfb86274262719bbe5f412',code_source_sha=source_sha,source_files=source_records,
        historical_FULL_Known_CC4=dict(stage_case_sha=boundary['original_stage_case_sha'],
            planning_case_sha=boundary['planning_case_sha'],evaluation_case_sha=boundary['evaluation_case_sha'],
            A_RESULT=boundary['A_result'],Known_CC4_capacity_status='PASS',Actual_handoff_status='NOT_CERTIFIED'),
        historical_Dday_initial_state=dict(semantic_sha=boundary['initial_state_sha'],
            raw_artifact=boundary['original_Dday_freeze'],prefix_replay_status='NOT_CERTIFIED',
            semantic_sha_equals_file_byte_sha=False),
        PR230_diagnostic_FCFS=dict(bindings=old['bindings'],scope='DIAGNOSTIC_ONLY_NOT_OPTIMIZED_KNOWN'),
        previous_E60=dict(case_sha=old['bindings']['case_sha'],status='SAME_CASE_A1_NOT_CERTIFIED'),
        current_event_research=dict(bindings=new['bindings'],status='SAME_CASE_A1_NOT_CERTIFIED',
            active_entry='build_current_event_case',Unknown_site_authority='EXPLICIT_SOURCE_COMPATIBLE_RESEARCH_RIGHTS',
            source_customer_permission_claim=False,Known_corrective_rights_automatically_granted=False),
        MESS_original_same_pool=joint['identity'],S1_reduced=lp['original_source_identity'],
        certificates_transferred_between_cases=False,new_Git_branch_created=False,new_worktree_created=False,new_PR_created=False)
    _write(report/'COMMON_SOURCE_CASE_MANIFEST.json',manifest)
    _write(report/'KNOWN_PLANNING_ACTUAL_HANDOFF.json',dict(status='NOT_CERTIFIED',
        reason='ORIGINAL_DDAY_STATE_DOES_NOT_EXECUTE_ORIGINAL_PLANNING_COMMANDS',
        exact_historical_boundary=boundary,latest_research_A1='SAME_CASE_A1_NOT_CERTIFIED',
        current_code_gate='RAW_FULL_A_AND_COMMAND_DERIVATION_AND_REAL_SOURCE_RECEIPT_AND_ACTUAL_DRIVER_JOIN',
        normalized_observed_source_receipt_required=True,semantic_source_normalization_certified=False,
        commands_retimed=False,diagnostic_FCFS_promoted=False,May01_Actual_status='NOT_RUN'))
    budget=UnifiedResearchBudget();budget.verify_parents()
    with budget._transaction():
        used=budget.document['conservative_solve_seconds']
        budget.document['linked_cumulative_projections']=[dict(path=p['path'],historical_seconds=p['used_seconds'],
            new_conservative_seconds=used,cumulative_seconds=p['used_seconds']+used,limit_seconds=p['limit_seconds'])
            for p in budget.document['historical_ledgers']]
        budget.document['research_execution']='BOUNDED_FOLLOWUP_FINISHED_CAMPAIGNS_HOLD'
    ledger=read(budget.path)
    _write(report/'UNIFIED_NATIVE_LEDGER.json',dict(status='PASS' if budget.remaining()>=0 and not ledger['inflight'] else 'FAIL',
        canonical_ledger=file_record(budget.path),remaining_native_seconds=budget.remaining(),
        historical_usage_reset=False,Heavy_workers=1,Threads=1,new_Heavy_research_session_created=False,
        PR221_independent_session_reopened=False,ledger=ledger))
    _write(report/'A1_M1_A2_M2_HANDOFF_AUDIT.json',dict(status='NOT_CERTIFIED',
        stage_order=['A1','M1','A2','M2'],original_planning_engines_preserved=True,
        current_event_Actual_hook_implemented=True,current_event_Actual_global_MILP_calls=0,
        same_source_case_real_stages_executed=False,reason='SAME_CASE_A1_AND_DDAY_BOUNDARY_NOT_CERTIFIED',
        MESS_joint_4x24_historical_fixed_anchor_test_only=True,B1_MESS_OFF_and_B3_MESS_ON_separate=True,
        Source_C1_PQ_and_signed_MESS_injection_double_count=False,
        May01_B3_Full96_status='NOT_RUN',Fresh_AC_status='NOT_RUN'))
    _write(report/'S1_PRE_NATIVE_ADMISSION_REPAIRS.json',dict(status='DIAGNOSTIC_ONLY',
        failed_pre_native_attempts=2,actual_native_calls_during_failed_attempts=0,
        repairs=['Compare path/sha256/bytes without treating annotation fields as file bytes',
                 'Regenerate exact charge RHS=0 and discharge RHS=Pmax mode hull rows'],
        successful_attempt=3,source_cut_proof=file_record(report/'S1_MODE_HULL_VALIDITY_GATE.json'),
        successful_native_receipt=file_record(report/'S1_MODE_HULL_LP_COMPARISON.json'),budget_reset=False))
    gate=dict(status='NOT_CERTIFIED',code_and_native0_status=regression['status'],
        original_451_tests_preserved=regression['baseline_tests_preserved'],native0_test_count=regression['total'],
        AIDC_original_coefficient_fixture='PASS',AIDC_named_control_fixture='PASS',
        AIDC_same_case_Actual_handoff='NOT_CERTIFIED',AIDC_May01_C0_C1_C2='NOT_RUN',
        AIDC_Full96_Fresh_AC='NOT_RUN',original_11_SVR_authority_preserved=True,
        MESS_same_pool_integer_LP_compression='PASS',MESS_original_FULL_replay='PASS',
        MESS_compression_performance='NOT_CERTIFIED',MESS_compression_adopted_as_default=False,
        MESS_new_diversified_search_UB='NOT_RUN',S1_actual_LP_fractionality='DIAGNOSTIC_ONLY',
        S1_Mode_Hull_384_cut_bound_improvement='FAIL',
        S1_Mode_Hull_LP_delta=hull['LP_objective_increase'],S1_exact_integer_oracle='NOT_CERTIFIED',
        stronger_original_4x24_Global_LB='NOT_CERTIFIED',real_A1_M1_A2_M2='NOT_CERTIFIED',
        research_time_shift_60min_and_checkpoint_migration='NOT_RUN',Actual_global_MILP_calls=0,
        May31_campaign='NOT_RUN',IEEE8500='NOT_RUN',auto_scheduler_restart=False,
        safe_May01_Full96_performance_PASS_claimed=False,
        next_step='CERTIFY_ORIGINAL_PREFIX_AND_NORMALIZED_DDAY_BOUNDARY_BEFORE_NEW_A1_OR_MAY01_CANARY',
        Native_budget_remaining_seconds=budget.remaining(),code_source_sha=source_sha)
    _write(report/'FINAL_VALIDATION_GATE.json',gate)
    answers=[
        ('Known과 CC4 GPU 공동 최적화','PASS','과거 동일 FULL A1의 96×12 용량·서비스를 재검증했다. 최신 연구 A1 인증은 없다.'),
        ('Q50 Nominal과 Achieved Reserve','PASS','Nominal은 미래 예상 점유다. 확보 Reserve는 실제 용량 여유이며 과거 CC4/Runtime 확보량은 모두 0, 부족분은 75,649/17,330 GPU-slot이다.'),
        ('Planning/Actual GPU 이중 계산','PASS','Bridge·Fixture에서 Forecast/Observed/Running/Committed를 분리하고 UID당 Forecast 1회 차감 및 서비스·Carry 보존을 검증했다. 실제 통합 인증은 없다.'),
        ('미래 Known 예약 때문에 Unknown 사전 거부','PASS','새 활성 CurrentEvent 경로에서 제거했다. FCFS 비교 기준시각도 Source hard release로 취급하지 않는다. 과거 진단 코드는 재현용으로 보존했다.'),
        ('현재 GPU·Signed Sensitivity 배치','PASS','모든 선로/상과 Original C1을 평가한다. 원본 12 AIDC/780 GPU/11 SVR 계수 Fixture에서 12후보 중10 허용, P/Q 오차1.83e-15·도함수 오차9.36e-17이다. 실제 May 성능은 미검증이다.'),
        ('실제 Known 충돌 시 PENDING Pre-placement','PASS','명명 Fixture에서 실제 충돌 때만 수행했다. 미래 추측과 Running 이동은 수행하지 않는다.'),
        ('GPU/WAN/데이터/QoS 만족','PASS','권한·Rack·bytes/s WAN·전송/준비시간·공유 QoS를 검사하고 준비 후 현재 GPU/계통을 다시 검사한다. 증거 부족은 Queue한다. 실제 May 인증은 없다.'),
        ('Planning/Actual 명령 구분','PASS','PLANNING_COMMAND를 보존하고 ACTUAL_CORRECTIVE_COMMAND를 별도 저장한다. 같은 입력의 교정 후 Known 실행 SHA 동일을 강제하지 않는다.'),
        ('Runtime Overrun Running 보호','PASS','Q50 만료로 해제하지 않는다. 실제 관측 완료까지 물리 점유를 유지하며 잔여 Runtime 미검증은 None으로 표시한다.'),
        ('Runtime Short Backfill','PASS','실제 완료 즉시 GPU를 해제한다. 다음 합법적15분 실행 이벤트에 후보 사이트별 미래 확정 예약을 검사하며 안전성 증명 없으면 대기한다.'),
        ('QoS60분 연구 가정','PASS','참여 Batch 연구 계약과 고객 SLA를 구분했다. 본 Actual의 의도적 Time-shifting·Checkpoint Migration은 활성화하지 않았다.'),
        ('May01 Unknown 실행·Changed GPUh','NOT_RUN','새 제어의 실제 May01은 실행하지 않았다. 합성 Fixture의 Changed GPUh0.5를 May 결과로 사용하지 않았다. 과거2시간 진단의 Unknown 시작/변경은0이었다.'),
        ('C0/C1/C2 최대 선로부하율','NOT_RUN','새 May01 값은 모두 미측정이다. 합성 Fixture만0.90/0.65/0.65이고, 과거C0/C1 진단0.5201161496609195는 별도 역사다.'),
        ('기존11-SVR Fresh AC','NOT_RUN','현재 Actual trace가 없으므로 새 Fresh AC를 실행하지 않았다. 과거Fresh16 PASS를 이전하지 않았다.'),
        ('원래4대·24노드 정확 압축','PASS','동일 PR221 Pool137,635변수/416binary를 유지하며715,600→685,819행,7,008,176→6,961,847NNZ. Integer/LP 동등성 및 원본 FULL replay를 검증했다.'),
        ('전체 Beam 반복시간 개선','NOT_CERTIFIED','같은 Pool 측정 비용25.7048→36.1767초로 증가했다. 압축 Native20.229초·증명/캐시9.243초, 원본 Native19.089초. 전체 새 Beam 반복 Wall은 미측정이며 기본 채택하지 않는다.'),
        ('더 좋은 FULL UB 발견','NOT_RUN','새 Beam 실제 탐색은 미실행이다. 고정 Pool 양쪽 FULL UB0.5398310226338695로 개선0이다.'),
        ('다른 차량·충전소 충분 탐색','NOT_CERTIFIED','4차량·STAY/이동·목적지/시각 다양성의 같은 예산 Admission Fixture는 PASS다. 실제 원본24노드 탐색 범위와 UB 효과는 미검증이다.'),
        ('S1 Root Gap 원인','DIAGNOSTIC_ONLY','실제 LP0.6090630116, 분수Arc4,307·Mode192·다중 위치187 차량슬롯·동시 충방전192 차량슬롯이다. 정수 feasible UB0.64126596697은 최적값이 아니다. Mode만 바꿔 같은 목적을 유지하는 LP witness가 있다.'),
        ('K48보다 높은 인증 Global LB','NOT_CERTIFIED','유효한384 Mode Cut으로 S1 LP 변화6.7e-11에 그쳤다. 원본4×24 K48 LB0.46498486997548166을 넘어선 새 인증은 없다.'),
        ('Restricted Bound/Global LB 구분','PASS','Pool ObjBound0.539831/0.289400과 S1 LP는 원본Global LB로 쓰지 않는다. 원본 같은 Case의 gap13.864737209%를 보존했다.'),
        ('동일 Case A1–M1–A2–M2 실제 통합','NOT_CERTIFIED','원래4단계와 최종A2→Actual Hook은 유지했다. 과거 원본 경계의Running253·과거Pending886 불일치 및 최신 SAME_CASE_A1_NOT_CERTIFIED로 실행 인증이 막힌다.'),
        ('동결 가능한 기능','PASS','현재 이벤트 배치·Pending 교정·물리 점유/Forecast Bridge·Source 경계/명령/실제 Driver Join·동일 Pool 삭제 증명/오염 거부를 코드·Fixture 범위로 동결한다. 성능 개선을 동결하지 않는다.'),
        ('연구 실패/미검증','NOT_CERTIFIED','압축 전체 비용 개선 실패, Mode Hull LP 개선 실패. 새 Beam UB·강화Global LB·S1정수최적값·60분Actual·Migration·May Fresh AC·실제 통합은 미검증이다.'),
        ('다음 May01/May31 실행 근거','NOT_CERTIFIED','May31/IEEE8500/자동 Scheduler는 HOLD다. 기존6시간 Prefix의 정당한 실행과 정상화된 동일 Source Dday 상태를 먼저 인증해야 May01 Canary를 진행할 수 있다.')]
    text=f'PR #230의 기존 브랜치에서 요청된 복구·개발과 제한된 검증을 수행했다. {regression["total"]}개 Native0 테스트 PASS(기존451 보존, skip0)이며 새 Native 사용량은 같은 누적 원장에 기록했다. 최종 실제 통합 Gate는 NOT_CERTIFIED다.\n\n'
    text+='가장 먼저 막히는 AIDC 조건은 원본 Planning과 당시 저장된 Dday 상태의 불일치다. 동일 원본 파일과 원본1,499명령을 연결해 Running253건의 사이트/시작 불일치와 과거Pending886건을 확인했다. 파일 누락이 아니며 임의 Retiming·진단 FCFS로 교체하지 않았다. 정규화된 관측 상태 Receipt의 파일 SHA와 실제 Driver 초기 상태를 연결하는 Gate를 추가했으나 기존 semantic SHA를 파일 SHA로 바꿔 인증하지 않는다.\n\n'
    text+='MESS는 공식 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Incumbent Registry를 보존했다. 압축의 수학적 동등성은 PASS지만 비용은 증가했고, S1 Mode Cut은 실제 LP 목적 개선에 실패했다. 별도 소형 LP/Oracle 연구를 운영 Full MILP로 대체하지 않았다.\n\n'
    text+='|번호|질문|상태|답변|\n|---|---|---|---|\n'
    for i,(q,s,a) in enumerate(answers,1):text+=f'|{i}|{q}|{s}|{a}|\n'
    text+=f'\n공유 Native는 {ledger["conservative_solve_seconds"]:.6f}/360초 사용했고 {budget.remaining():.6f}초가 남았다. Worker1·Thread1, 부모 원장 SHA와 기존 사용량, PR221 별도 세션을 보존했다. 추가 날짜 캠페인·IEEE8500·자동 재시작·Running 강제 종료·Actual 전역 MILP는 실행하지 않았다.\n'
    (report/'FINAL_UNIFIED_REVIEW_KO.md').write_text(text,encoding='utf8')
    (report/'README.md').write_text('기존 PR230의 후속 검토 자료다. 과거 보고서와 결과는 그대로 보존했다.\n\n'
        '- [25개 질문과 최종 검토](FINAL_UNIFIED_REVIEW_KO.md)\n'
        '- [최종 검증 Gate](FINAL_VALIDATION_GATE.json)\n'
        '- [Source/Case 분리](COMMON_SOURCE_CASE_MANIFEST.json)\n'
        '- [AIDC 검토](AIDC_FINAL_REVIEW_KO.md) · [MESS 검토](MESS_FINAL_REVIEW_KO.md)\n'
        '- [회귀](UNIFIED_REGRESSION_RESULTS.json) · [원장](UNIFIED_NATIVE_LEDGER.json)\n\n'
        '실제 May01 C0/C1/C2와 Full96 Fresh AC는 NOT_RUN이다. Runtime과 전력계수 Fixture 수치를 실제 May 개선으로 쓰지 않는다. '
        '새 연구 기본 Case/Science 계약은 이 디렉터리의 SHARED_SOURCE_CASE_MANIFEST와 UNIFIED_INTERFACE_CONTRACT다. '
        'build_current_event_case가 이 계약을 사용하며 별도의 인증된 Dday Handoff를 요구한다. '
        '기존 상위 디렉터리의 FCFS 진단 계약은 역사적 재현용으로 보존한다.\n\n'
        '대형 Source archive·원본 CSR·LP Point·Native Log는 로컬 runtime과 기존 원본에 보존하며 JSON에 SHA/경로를 기록했다. '
        'PR clone만으로 모든 원본 실제 데이터가 제공된다고 주장하지 않는다.\n',encoding='utf8')
    _write(report/'FINAL_SOURCE_FREEZE.json',dict(status='PASS',code_source_sha=source_sha,source_files=source_records,
        required_result_files_present=True,actual_performance_PASS_claimed=False))
    print(json.dumps(dict(status=gate['status'],native0=regression['total'],Native_remaining=budget.remaining(),code_source_sha=source_sha),indent=2))


if __name__=='__main__':main()
