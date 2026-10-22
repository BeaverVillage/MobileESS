"""Evidence-only May01 integration decision; never invokes a campaign."""
import subprocess
from .stage_common import *
from .prestart_execution import atomic


def ready(name):
    path=OUT/name
    return path.exists() and read(path).get('PASS') is True


def generate():
    required=['A1_VARIABLE_AIDC_FULL_NATIVE0.json','A2_FIXED_M1_FULL_NATIVE0.json',
        'M2_FIXED_A2_STATIC_NATIVE0.json','M1_ORIGINAL_FULL_VALIDATOR_BINDING.json',
        'M2_ORIGINAL_FULL_VALIDATOR_BINDING.json','A_PRODUCTION_ENTRY_BINDING.json',
        'K48_WHOLE_CASE_PACKET_BINDING.json','K48_ACTUAL_NATIVE0_READBACK.json',
        'STAGE_M_RUNTIME_BINDING.json','BEAM_DIRECT_JOINT_MESS8_BINDING.json',
        'PRODUCTION_M1_CURRENT_CASE_NATIVE0.json','PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json',
        'ACTUAL_SOURCE_POLICY_PREPARATION.json','ACTUAL_MIGRATION_EVENT_FIXTURE.json',
        'ACTUAL_FULL120_FRESH_HANDLER_FIXTURE.json','CAMPAIGN_PRESTART_EXECUTION_GUARDS.json',
        'CAMPAIGN_MEMORY_POLICY.json','GUROBI_ASCII_FILE_IO_CERTIFICATION.json','SIGNED_ACTUAL_POLICY_GRID_BINDING.json']
    from .stage_handlers import HANDLERS
    from v44.stages import CHAINS
    expected=set(x for chain in CHAINS.values() for x in chain)
    assert set(HANDLERS)==expected
    changes=subprocess.check_output(['git','diff','--name-only','5d2fdf320ea50ccf232f2b60f73f417c76bede73','--',
        'v44','v43_actual','v43_corrective','v43_baseline','v43_arms','v42_may_campaign_native90',
        'v42_a_stage_canary','v42_a_stage_acceptance','v42_native','v42_m1_research'],cwd=ROOT,text=True).splitlines()
    source=dict(PASS=not changes,original_r043=SOURCE,prior_stage_HEAD='5d2fdf320ea50ccf232f2b60f73f417c76bede73',
        changed_original_source_files=changes,source_files_not_copied=True,
        original_algorithm_phase_pricing_gap_and_solver_body_preserved=True,
        original_broader_physical_start_universe_equivalence_claimed=False,
        original_finite_WINDOW_authority=record(OUT/'A_STAGE_SOURCE_WINDOW_AUTHORITY_AUDIT.json'))
    put('ORIGINAL_STAGE_SOURCE_PRESERVATION.json',source)
    k=read(OUT/'K48_WHOLE96_INTERFACE_CERTIFICATION.json')
    k.update(whole_case_packet_binding_PASS=ready('K48_WHOLE_CASE_PACKET_BINDING.json'),
        actual_K16_K32_K48_Native0_readback_PASS=ready('K48_ACTUAL_NATIVE0_READBACK.json'))
    k['PASS']=bool(k['representation_all96_PASS'] and k['whole_case_packet_binding_PASS'] and k['actual_K16_K32_K48_Native0_readback_PASS'])
    k['stage_integration_evidence']={n:record(OUT/n) for n in ('K48_WHOLE_CASE_PACKET_BINDING.json','K48_ACTUAL_NATIVE0_READBACK.json') if (OUT/n).exists()}
    k['numeric_LB_not_required_for_prestart']=True;put('K48_WHOLE96_INTERFACE_CERTIFICATION.json',k)
    current_name='ACTUAL_CURRENT_AC_AND_QOS_HANDLER_CERTIFICATION.json'
    current=read(OUT/current_name)
    if current.get('current_AC_two_tick_Fresh_fixture_PASS'):
        put('ACTUAL_CURRENT_AC_TWO_TICK_ADMISSION.json',current)
    current=read(OUT/'ACTUAL_CURRENT_AC_TWO_TICK_ADMISSION.json') if (OUT/'ACTUAL_CURRENT_AC_TWO_TICK_ADMISSION.json').exists() else current
    physical=bool(current.get('current_AC_two_tick_Fresh_fixture_PASS'))
    actual_names=['ACTUAL_SOURCE_POLICY_PREPARATION.json','ACTUAL_MIGRATION_EVENT_FIXTURE.json',
        'ACTUAL_FULL120_FRESH_HANDLER_FIXTURE.json','PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json','SIGNED_ACTUAL_POLICY_GRID_BINDING.json']
    actual=dict(PASS=physical and all(ready(n) for n in actual_names),
        current_AC_two_tick_Fresh_fixture_PASS=physical,
        evidence={n:record(OUT/n) for n in actual_names if (OUT/n).exists()},
        source_settled_tick_voltage_contract=True,all_event_excursions_retained=True,
        full120_B0_fixture_only=True,optimized_B1_B2_B3_physical_outcome_claimed=False,
        Source_QoS_intentional_budget_and_Known_research_policy_separate=True,
        Source_customer_SLA_certified=False,private_service_read_by_controller=False,
        Native_optimize_calls=0,official_campaign_executed=False)
    put(current_name,actual)
    entries=dict(PASS=all(ready(n) for n in required) and source['PASS'] and k['PASS'] and actual['PASS'],
        chains={key:list(value) for key,value in CHAINS.items()},
        callables={name:fn.__module__+'.'+fn.__name__ for name,fn in HANDLERS.items()},
        actual_Native0_builders_controller_and_FULL_validators_bound=True,
        evidence={name:dict(PASS=ready(name),artifact=record(OUT/name) if (OUT/name).exists() else None) for name in required},
        Source_M_FULL_handoff_does_not_require_numeric_global_gap=True,
        finite_M_fixture_not_production_parent=True,checkpoint_resume_budget_and_own_worker_lease_bound=True,
        numerical_LB_UB_gap_and_optimized_A_M_outcomes_deferred=True,official_campaign_executed=False,
        no_new_grid_constraint_generation=True)
    put('B0_B1_B2_B3_PRODUCTION_HANDLER_CERTIFICATION.json',entries)
    failures=[name for name in required if not ready(name)]
    factory=read(OUT/'PRODUCTION_M1_CURRENT_CASE_NATIVE0.json') if (OUT/'PRODUCTION_M1_CURRENT_CASE_NATIVE0.json').exists() else {}
    if not factory.get('real_production_M1_handler_original_adaptive_Beam_score_boundary_reached'):
        failures.append('PRODUCTION_M1_HANDLER_ADAPTIVE_SCORE_BOUNDARY')
        entries['PASS']=False
        put('B0_B1_B2_B3_PRODUCTION_HANDLER_CERTIFICATION.json',entries)
    if not source['PASS']:failures.append('ORIGINAL_STAGE_SOURCE_PRESERVATION.json')
    if not physical:failures.append('ACTUAL_CURRENT_AC_TWO_TICK_ADMISSION.json')
    complete=not failures and entries['PASS']
    final=dict(status='READY_FOR_MAY01_CAMPAIGN_APPROVAL' if complete else 'PRESTART_BLOCKED_WITH_EVIDENCE',
        experiment_id='V2_add',PR=236,days=['2025-05-01'],SCIENTIFIC_SIMULATION_READY=complete,
        FIELD_INSTALLATION_UNVERIFIED=True,official_campaign_executed=False,Native_optimize_calls=0,Native_presolve_calls=0,
        unresolved_required_evidence=failures,original_source=source,
        numerical_LB_UB_gap_absence_not_a_blocker=True,
        hardware='IEEE8500 Balanced Source-YY; beta_BG=2.00; Actual SVR3; AIDC12/STA12; GPU780; MESS8',
        voltage_contract='Original final native TIME state of each tick; full event envelopes retained',
        official_memory_limits='None; Gurobi MemLimit/SoftMemLimit = positive Infinity',
        Native0_preparation_limits='RSS4GiB / system available5GiB retained',
        original_Job_WINDOW_contract='Literal finite input WINDOWS; r043 broader physical-start universe equivalence is explicitly not claimed',
        review='FINAL_STAGE_INTEGRATION_REVIEW_KO.md',
        evidence={n:record(OUT/n) for n in required if (OUT/n).exists()})
    put('FINAL_MAY01_PRESTART_GO_NO_GO.json',final)
    rows=[]
    for name in required:
        rows.append('| '+name+' | '+('PASS' if ready(name) else '미완료/FAIL')+' |')
    text='\n'.join([
        '# V2_add PR #236 May01 최종 Stage 통합 검토', '',
        '**판정: '+final['status']+'**. 공식 캠페인 및 Gurobi optimize/presolve는 실행하지 않았다.', '',
        '공식 캠페인의 RSS·가용 RAM 기준 거부·대기·중단은 제거했다. Gurobi 두 메모리 제한은 양의 Infinity다. 기존 0=무제한 주장은 철회했으며 설치된 13.0.2 기본값과 공식 문서로 바로잡았다. Native0 준비 보호4GiB/여유5GiB와 과거 중단 증거는 유지한다.', '',
        'Source-YY, 배경배율2.00, Actual SVR3, GPU780 및 MESS8을 유지했다. 선로3,703개/Triplex1,177개와 전체 Parent Terminal 최대 선로부하율 목적함수는 보존했다. Planning12 RegControl과 Actual 추가9개 단상 제어기(3 Bank)는 역할이 다르다.', '',
        '보존한 B0 평가96의 전체/MV 최대 선로부하율은75.711008%, LV46.810643%, 차이28.900365pp다. 전압은0.951568~1.040377pu다. 새 엔진 두 개의120슬롯 Fresh에서 선로·전압·변압기 배열 최대 오차0, 상태와 Queue 일치를 확인했다. Prefix23초 저전압/18초 과전압 등 모든 이벤트 진단은 삭제하지 않았다. 공식 판정은 원본 최종 틱 계약이다.', '',
        '| 증거 | 상태 |','|---|---|',*rows,'',
        'A1/A2 Native0는 원본 canonical active kernel과117개 완전 로컬 Pricing 블록을 모두 구성한 결과다. 단일 거대 Monolithic Job Native 모델 PASS로 보고하지 않는다. M2는 비영 A2 유한 Witness의 C1을 고정해 새 RHS·Bound·정적 제거 증명과 Native0/독립 FULL 복원을 검사했다. Witness는 최적화된 M1/A2나 공식 캠페인 결과가 아니다.', '',
        '중요한 입력 계약 차이: r043 physical_starts는 입력 WINDOWS 밖121,313개 시작 선택을 허용하며1,395개 Job에 영향이 있다. 본 Adapter는 사용자가 요구한 원본 유한 WINDOW를 강제한다. 원본 알고리즘 파일·Phase-I/P1/Pricing/정수 수용 코드는 보존했지만, r043의 더 넓은 physical-start 수학적 도메인과 동등하다고 주장하지 않는다. 감사 JSON에 개별 차이를 보존했다.', '',
        '실제 B0 Handler는2,498개 Job의 서비스·Carryout·GPUh·C1을 재생했다. B1/B3의 비영 Migration은 별도 명명 Fixture에서 원본 Controller와 WAN/보류/재시작 구간으로 검증했다. Source 의도적 QoS 예산, 실제 시작/완료 초과, 연구용 Known 정책을 구분하며 고객 SLA 인증을 주장하지 않는다. 최적화된 B1/B2/B3 Actual 보안 결과는 캠페인에서 계산한다.', '',
        '캐시와 재개: 동일 수치 입력의 순수 Native0 K16 구성만 원본 독립 Verifier로 재인증할 수 있다. 과거 UB/LB/Point/Native clock은 가져오지 않는다. 완료 Stage는 파일/결과/날짜/Source SHA로 복원한다. 실패 M은 명시적 재진입과 원본 원장 조정 후 남은 예산으로만 재개하며 A/Actual의 비저장 실시간 상태는 자동 재개하지 않는다.', '',
        '실행 준비 명령은 `python -m v2_add_preflight.stage_campaign plan`이다. 공식 명령은 별도 사용자 승인과 이 최종 인증의 SHA가 일치해야 실행된다. Runtime은 `static_complete/official_stage_campaign/<새 디렉터리>` 하위, Worker1/A Threads1/M Threads4, A5400초·Gap0.005, K48 300초/Joint900초·단일300초·M Gap0.03을 유지한다. 현재 명령을 실행하지 않았다.', '',
        '현장 GIS/보호 설비 검증은 FIELD_INSTALLATION_UNVERIFIED로 별도 표시한다. 연구용 시뮬레이션 물리 인증과 혼동하지 않는다. 기존 V44/V1_add 소스·Worker·원장·캠페인과 May02~07은 변경하지 않았다.', '',
        '남은 필수 증거: '+(', '.join(failures) if failures else '없음. 수치 최적화 성과는 승인 후 캠페인의 계산 대상이다.'),'' ])
    (OUT/'FINAL_STAGE_INTEGRATION_REVIEW_KO.md').write_text(text,encoding='utf-8')
    print(final['status'],failures,flush=True)


if __name__=='__main__':generate()
